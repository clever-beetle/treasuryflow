from flask import Blueprint, render_template, request, url_for, redirect, session, g, flash, Response, jsonify
from utils import logger, get_db, login_required, format_rupiah, format_rupiah_input, CATEGORIES
from models import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets, smtplib, json, csv, os
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fpdf import FPDF

ai_bp = Blueprint('ai', __name__)

@ai_bp.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    try:
        data = request.get_json()
        message = data.get('message', '').lower()
        user_id = session['user_id']
        db = get_db()
        
        reply = "Maaf, saya tidak mengerti pertanyaan Anda. Coba tanya tentang 'saldo', 'utang', atau 'apakah saya boros?'"
        
        from datetime import datetime
        today = datetime.now()
        current_month = today.strftime('%Y-%m')
        
        # 1. Saldo Check
        if 'saldo' in message or 'uang' in message or 'sisa' in message:
            total_balance = db.execute('SELECT SUM(current_balance) FROM accounts WHERE user_id = ?', (user_id,)).fetchone()[0] or 0
            if total_balance > 0:
                reply = f"Total saldo Anda di semua akun saat ini adalah **Rp {total_balance:,.0f}**. Tetap bijak mengelolanya ya!"
            else:
                reply = "Saat ini saldo Anda tercatat Rp 0. Ayo catat pemasukan Anda terlebih dahulu."
                
        # 2. Boros / Pengeluaran Check
        elif 'boros' in message or 'pengeluaran' in message or 'habis' in message:
            expense = db.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'expense' AND category != 'Transfer' AND strftime('%Y-%m', date) = ?", (user_id, current_month)).fetchone()[0] or 0
            income = db.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'income' AND category != 'Transfer' AND strftime('%Y-%m', date) = ?", (user_id, current_month)).fetchone()[0] or 0
            
            if expense == 0:
                reply = "Hebat! Anda belum ada pengeluaran sama sekali di bulan ini."
            elif income == 0:
                reply = f"Bulan ini pengeluaran Anda sudah mencapai **Rp {expense:,.0f}**, tapi belum ada pemasukan yang dicatat. Hati-hati!"
            elif expense > income:
                reply = f"Ya, Anda cukup boros. Pengeluaran bulan ini (**Rp {expense:,.0f}**) sudah melebihi pemasukan Anda (**Rp {income:,.0f}**). Segera rem pengeluaran Anda!"
            elif expense > (income * 0.7):
                reply = f"Lumayan tinggi. Pengeluaran Anda (**Rp {expense:,.0f}**) sudah mencapai lebih dari 70% dari pemasukan (**Rp {income:,.0f}**)."
            else:
                reply = f"Kondisi Anda aman! Pengeluaran Anda (**Rp {expense:,.0f}**) masih jauh di bawah pemasukan Anda (**Rp {income:,.0f}**). Anda hebat dalam menabung!"
                
        # 3. Utang Check
        elif 'utang' in message or 'hutang' in message:
            total_debt = db.execute("SELECT SUM(remaining_amount) FROM debts_receivables WHERE user_id = ? AND type = 'utang' AND status = 'BELUM LUNAS'", (user_id,)).fetchone()[0] or 0
            total_piutang = db.execute("SELECT SUM(remaining_amount) FROM debts_receivables WHERE user_id = ? AND type = 'piutang' AND status = 'BELUM LUNAS'", (user_id,)).fetchone()[0] or 0
            
            if total_debt == 0 and total_piutang == 0:
                reply = "Bagus sekali! Anda tidak memiliki utang maupun piutang aktif."
            else:
                reply = f"Anda memiliki total utang sebesar **Rp {total_debt:,.0f}** dan total piutang sebesar **Rp {total_piutang:,.0f}**."

        # 4. Budget Check
        elif 'budget' in message or 'anggaran' in message:
            reply = "Untuk mengecek detail anggaran, silakan lihat grafik 'Anggaran Bulanan' di halaman Dashboard Anda ya!"
            
        return jsonify({'reply': reply})
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        return jsonify({'reply': 'Aduh, terjadi kesalahan pada sistem saya. Coba lagi nanti ya!'})

@ai_bp.route('/api/forecast', methods=['GET'])
@login_required
def api_forecast():
    try:
        user_id = session['user_id']
        db = get_db()
        
        # Get monthly expenses for the last 6 months
        expenses = db.execute("""
            SELECT strftime('%Y-%m', date) as month, SUM(amount) as total
            FROM transactions 
            WHERE user_id = ? AND type = 'expense'
            GROUP BY month
            ORDER BY month ASC
            LIMIT 6
        """, (user_id,)).fetchall()
        
        if len(expenses) < 2:
            return jsonify({'status': 'insufficient_data', 'message': 'Butuh minimal 2 bulan data transaksi untuk melakukan prediksi AI.'})
            
        try:
            import pandas as pd
            from sklearn.linear_model import LinearRegression
            import numpy as np
        except ImportError:
            return jsonify({'status': 'error', 'message': 'Fitur AI dinonaktifkan di versi ini karena keterbatasan ukuran server.'})
        
        df = pd.DataFrame([dict(e) for e in expenses])
        # Convert month string to sequential numbers for linear regression
        df['time_idx'] = range(1, len(df) + 1)
        
        X = df[['time_idx']]
        y = df['total']
        
        model = LinearRegression()
        model.fit(X, y)
        
        # Predict next month
        next_month_idx = np.array([[len(df) + 1]])
        prediction = model.predict(next_month_idx)[0]
        
        return jsonify({
            'status': 'success',
            'prediction': max(0, float(prediction)), # Cannot be negative
            'historical_points': len(df)
        })
    except Exception as e:
        logger.error(f"Forecast Error: {e}")
        return jsonify({'status': 'error', 'message': 'AI Engine error'})
@ai_bp.route('/api/rag_chat', methods=['POST'])
@login_required
def api_rag_chat():
    try:
        data = request.get_json()
        message = data.get('message', '').lower()
        user_id = session['user_id']
        db = get_db()
        
        # 1. RETRIEVAL: Get all transactions for context
        transactions = db.execute("SELECT date, description, category, type, amount FROM transactions WHERE user_id = ?", (user_id,)).fetchall()
        
        if not transactions:
            return jsonify({'reply': 'Maaf, Anda belum memiliki transaksi apapun untuk saya pelajari.'})
            
        try:
            import pandas as pd
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            return api_chat_fallback(message, db, user_id)

        df = pd.DataFrame([dict(tx) for tx in transactions])
        df['description'] = df['description'].fillna('')
        
        # Create corpus combining category and description
        corpus = df['category'].str.lower() + " " + df['description'].str.lower()
        
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(corpus)
        
        message_vector = vectorizer.transform([message])
        similarities = cosine_similarity(message_vector, tfidf_matrix).flatten()
        
        # 2. GENERATION: Find the top matched transaction
        top_indices = similarities.argsort()[-3:][::-1] # Top 3
        
        if similarities[top_indices[0]] == 0:
            # Fallback to old behavior
            return api_chat_fallback(message, db, user_id)
            
        total_found = 0
        details = []
        for idx in top_indices:
            if similarities[idx] > 0:
                tx = df.iloc[idx]
                total_found += tx['amount'] if tx['type'] == 'expense' else 0
                details.append(f"- Rp {tx['amount']:,.0f} pada {tx['date']} untuk {tx['category']} ({tx['description']})")
                
        reply = f"Berdasarkan teknologi Vektor AI, saya menemukan data transaksi yang berkaitan dengan '{message}'.\n\nTotal Pengeluaran: **Rp {total_found:,.0f}**.\n\nRincian:\n"
        reply += "\n".join(details)
        
        return jsonify({'reply': reply})
        
    except Exception as e:
        logger.error(f"RAG Error: {e}")
        return jsonify({'reply': 'Aduh, Vector Engine saya sedang bermasalah.'})
        
def api_chat_fallback(message, db, user_id):
    # Old logic for general questions
    from datetime import datetime
    current_month = datetime.now().strftime('%Y-%m')
    if 'saldo' in message or 'uang' in message or 'sisa' in message:
        total_balance = db.execute('SELECT SUM(current_balance) FROM accounts WHERE user_id = ?', (user_id,)).fetchone()[0] or 0
        return jsonify({'reply': f"Total saldo Anda: **Rp {total_balance:,.0f}**."})
    elif 'boros' in message or 'pengeluaran' in message:
        expense = db.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'expense' AND category != 'Transfer' AND strftime('%Y-%m', date) = ?", (user_id, current_month)).fetchone()[0] or 0
        return jsonify({'reply': f"Bulan ini pengeluaran Anda sudah mencapai **Rp {expense:,.0f}**."})
    return jsonify({'reply': "Maaf, mesin Vector RAG tidak menemukan transaksi yang cocok, dan saya tidak memahami maksud Anda."})

@ai_bp.route('/api/predict_future', methods=['GET'])
@login_required
def predict_future():
    user_id = session['user_id']
    db = get_db()
    
    # Fetch all expenses grouped by day
    txs = db.execute('''
        SELECT date, SUM(amount) as total 
        FROM transactions 
        WHERE user_id = ? AND type = 'expense'
        GROUP BY date
        ORDER BY date ASC
    ''', (user_id,)).fetchall()
    
    if len(txs) < 3:
        return jsonify({'status': 'error', 'message': 'Not enough data to predict. Need at least 3 days of expenses.'})
        
    try:
        import pandas as pd
        from sklearn.linear_model import LinearRegression
        import numpy as np
        from datetime import datetime, timedelta
    except ImportError:
        return jsonify({'status': 'error', 'message': 'Fitur AI dinonaktifkan di versi ini karena keterbatasan ukuran server.'})

    
    df = pd.DataFrame(txs, columns=['date', 'total'])
    df['date'] = pd.to_datetime(df['date'])
    df['days_since'] = (df['date'] - df['date'].min()).dt.days
    
    X = df[['days_since']]
    y = df['total']
    
    model = LinearRegression()
    model.fit(X, y)
    
    # Predict next 7 days
    last_day = df['days_since'].max()
    future_X = np.array([[last_day + i] for i in range(1, 8)])
    future_dates = [(df['date'].max() + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 8)]
    predictions = model.predict(future_X)
    
    results = [{'date': d, 'predicted_expense': max(0, p)} for d, p in zip(future_dates, predictions)]
    
    return jsonify({
        'status': 'success',
        'predictions': results,
        'message': 'Prediction generated using Linear Regression AI.'
    })
