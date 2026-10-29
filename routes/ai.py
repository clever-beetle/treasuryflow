from flask import Blueprint, render_template, request, url_for, redirect, session, g, flash, Response, jsonify
from utils import logger, get_db, login_required, format_rupiah, format_rupiah_input, CATEGORIES, wib_now
from datetime import datetime, timedelta

ai_bp = Blueprint('ai', __name__)

def linear_regression(x, y):
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(x[i]*y[i] for i in range(n))
    sum_x2 = sum(x[i]**2 for i in range(n))
    
    denominator = (n * sum_x2 - sum_x**2)
    if denominator == 0:
        return 0, sum_y/n
        
    m = (n * sum_xy - sum_x * sum_y) / denominator
    b = (sum_y - m * sum_x) / n
    return m, b

@ai_bp.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    try:
        data = request.get_json(silent=True) or {}
        message = data.get('message', '').lower()
        user_id = session['user_id']
        db = get_db()
        
        reply = "Maaf, saya tidak mengerti pertanyaan Anda. Coba tanya tentang 'saldo', 'utang', atau 'apakah saya boros?'"
        
        today = wib_now()
        current_month = today.strftime('%Y-%m')
        
        # 1. Saldo Check
        if 'saldo' in message or 'uang' in message or 'sisa' in message:
            total_balance = db.execute("SELECT SUM(current_balance) FROM accounts WHERE user_id = ? AND (account_type = 'asset' OR account_type IS NULL)", (user_id,)).fetchone()[0] or 0
            if total_balance > 0:
                reply = f"Total saldo Anda di semua akun saat ini adalah **{format_rupiah(total_balance)}**. Tetap bijak mengelolanya ya!"
            else:
                reply = "Saat ini saldo Anda tercatat Rp 0. Ayo catat pemasukan Anda terlebih dahulu."
                
        # 2. Boros / Pengeluaran Check
        elif 'boros' in message or 'pengeluaran' in message or 'habis' in message:
            first_day = today.replace(day=1).strftime('%Y-%m-%d')
            import calendar as cal_mod
            last_day_num = cal_mod.monthrange(today.year, today.month)[1]
            last_day = today.replace(day=last_day_num).strftime('%Y-%m-%d')
            expense = db.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'expense' AND COALESCE(category, '') != 'Transfer' AND date >= ? AND date <= ?", (user_id, first_day, last_day)).fetchone()[0] or 0
            income = db.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'income' AND COALESCE(category, '') != 'Transfer' AND date >= ? AND date <= ?", (user_id, first_day, last_day)).fetchone()[0] or 0
            
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
            debt_rec = db.execute("SELECT SUM(remaining_amount) FROM debts_receivables WHERE user_id = ? AND type = 'debt' AND status = 'BELUM LUNAS'", (user_id,)).fetchone()[0] or 0
            cc_debt = db.execute("SELECT SUM(ABS(current_balance)) FROM accounts WHERE user_id = ? AND account_type = 'liability' AND current_balance < 0", (user_id,)).fetchone()[0] or 0
            total_debt = float(debt_rec) + float(cc_debt)
            total_piutang = db.execute("SELECT SUM(remaining_amount) FROM debts_receivables WHERE user_id = ? AND type = 'receivable' AND status = 'BELUM LUNAS'", (user_id,)).fetchone()[0] or 0
            
            if total_debt == 0 and total_piutang == 0:
                reply = "Bagus sekali! Anda tidak memiliki utang maupun piutang aktif."
            else:
                reply = f"Anda memiliki total utang sebesar **Rp {total_debt:,.0f}** dan total piutang sebesar **Rp {total_piutang:,.0f}**."

        # 4. Budget Check
        elif 'budget' in message or 'anggaran' in message:
            reply = "Untuk mengecek detail anggaran, silakan lihat grafik 'Anggaran Bulanan' di halaman Dashboard Anda ya!"
            
        return jsonify({'reply': reply})
    except Exception as e:
        try:
            db.rollback()
        except:
            pass
        logger.error(f"Chat Error: {e}")
        return jsonify({'reply': 'Aduh, terjadi kesalahan pada sistem saya. Coba lagi nanti ya!'})

@ai_bp.route('/api/forecast', methods=['GET'])
@login_required
def api_forecast():
    try:
        user_id = session['user_id']
        db = get_db()
        
        expenses = db.execute("""
            SELECT substr(CAST(date AS TEXT), 1, 7) as month, SUM(amount) as total
            FROM transactions 
            WHERE user_id = ? AND type = 'expense' AND COALESCE(category, '') != 'Transfer'
            GROUP BY substr(CAST(date AS TEXT), 1, 7)
            ORDER BY month ASC
            LIMIT 6
        """, (user_id,)).fetchall()
        
        if len(expenses) < 2:
            return jsonify({'status': 'insufficient_data', 'message': 'Butuh minimal 2 bulan data transaksi untuk melakukan prediksi AI.'})
            
        x = list(range(1, len(expenses) + 1))
        y = [float(e['total']) for e in expenses]
        
        m, b = linear_regression(x, y)
        next_x = len(x) + 1
        prediction = m * next_x + b
        
        return jsonify({
            'status': 'success',
            'prediction': max(0, float(prediction)),
            'historical_points': len(expenses)
        })
    except Exception as e:
        try:
            db.rollback()
        except:
            pass
        logger.error(f"Forecast Error: {e}")
        return jsonify({'status': 'error', 'message': 'AI Engine error'})

@ai_bp.route('/api/rag_chat', methods=['POST'])
@login_required
def api_rag_chat():
    try:
        data = request.get_json(silent=True) or {}
        message = data.get('message', '').lower()
        user_id = session['user_id']
        db = get_db()
        
        transactions = db.execute("SELECT date, description, category, type, amount FROM transactions WHERE user_id = ?", (user_id,)).fetchall()
        
        if not transactions:
            return jsonify({'reply': 'Maaf, Anda belum memiliki transaksi apapun untuk saya pelajari.'})
            
        words = set(message.lower().split())
        scored_txs = []
        
        for tx in transactions:
            desc = tx['description'] or ''
            cat = tx['category'] or ''
            text = (desc + " " + cat).lower()
            
            score = sum(1 for w in words if w in text)
            if score > 0:
                scored_txs.append((score, tx))
                
        if not scored_txs:
            return api_chat_fallback(message, db, user_id)
            
        scored_txs.sort(key=lambda x: x[0], reverse=True)
        top_matches = [tx for score, tx in scored_txs[:3]]
        
        total_found = 0
        details = []
        for tx in top_matches:
            val = float(tx['amount'] or 0)
            total_found += val if tx['type'] == 'expense' else 0
            details.append(f"- Rp {val:,.0f} pada {tx['date']} untuk {tx['category']} ({tx['description']})")
            
        reply = f"Berdasarkan mesin pencarian AI, saya menemukan data transaksi yang berkaitan dengan '{message}'.\n\nTotal Pengeluaran: **Rp {total_found:,.0f}**.\n\nRincian:\n"
        reply += "\n".join(details)
        
        return jsonify({'reply': reply})
        
    except Exception as e:
        try:
            db.rollback()
        except:
            pass
        logger.error(f"RAG Error: {e}")
        return jsonify({'reply': 'Aduh, Vector Engine saya sedang bermasalah.'})
        
def api_chat_fallback(message, db, user_id):
    today = wib_now()
    first_day = today.replace(day=1).strftime('%Y-%m-%d')
    import calendar as cal_mod
    last_day_num = cal_mod.monthrange(today.year, today.month)[1]
    last_day = today.replace(day=last_day_num).strftime('%Y-%m-%d')
    if 'saldo' in message or 'uang' in message or 'sisa' in message:
        total_balance = db.execute("SELECT SUM(current_balance) FROM accounts WHERE user_id = ? AND (account_type = 'asset' OR account_type IS NULL)", (user_id,)).fetchone()[0] or 0
        return jsonify({'reply': f"Total saldo Anda: **{format_rupiah(total_balance)}**."})
    elif 'boros' in message or 'pengeluaran' in message:
        expense = db.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'expense' AND COALESCE(category, '') != 'Transfer' AND date >= ? AND date <= ?", (user_id, first_day, last_day)).fetchone()[0] or 0
        return jsonify({'reply': f"Bulan ini pengeluaran Anda sudah mencapai **{format_rupiah(expense)}**."})
    return jsonify({'reply': "Maaf, mesin AI tidak menemukan transaksi yang cocok, dan saya tidak memahami maksud Anda."})

@ai_bp.route('/api/predict_future', methods=['GET'])
@login_required
def predict_future():
    user_id = session['user_id']
    db = get_db()
    
    txs = db.execute('''
        SELECT date, SUM(amount) as total 
        FROM transactions 
        WHERE user_id = ? AND type = 'expense' AND COALESCE(category, '') != 'Transfer'
        GROUP BY date
        ORDER BY date ASC
    ''', (user_id,)).fetchall()
    
    if len(txs) < 3:
        return jsonify({'status': 'error', 'message': 'Not enough data to predict. Need at least 3 days of expenses.'})
        
    try:
        from datetime import date as dt_date
        valid_points = []
        for tx in txs:
            d_val = tx['date']
            dt_obj = None
            if isinstance(d_val, datetime):
                dt_obj = d_val
            elif hasattr(d_val, 'year') and hasattr(d_val, 'month') and hasattr(d_val, 'day'):
                dt_obj = datetime.combine(d_val, datetime.min.time())
            elif isinstance(d_val, str):
                try:
                    dt_obj = datetime.strptime(d_val[:10], '%Y-%m-%d')
                except (ValueError, TypeError):
                    continue
            else:
                continue

            try:
                amt = float(tx['total'] or 0)
            except (ValueError, TypeError):
                amt = 0.0

            if dt_obj is not None:
                valid_points.append((dt_obj, amt))

        if len(valid_points) < 3:
            return jsonify({'status': 'error', 'message': 'Not enough data to predict. Need at least 3 days of expenses.'})

        min_date = min(p[0] for p in valid_points)
        x = [(p[0] - min_date).days for p in valid_points]
        y = [p[1] for p in valid_points]
        
        m, b = linear_regression(x, y)
        
        last_date = max(p[0] for p in valid_points)
        last_x = max(x)
        
        results = []
        for i in range(1, 8):
            future_x = last_x + i
            future_date = (last_date + timedelta(days=i)).strftime('%Y-%m-%d')
            pred = m * future_x + b
            results.append({
                'date': future_date,
                'predicted_expense': max(0, pred)
            })
            
        return jsonify({
            'status': 'success',
            'predictions': results,
            'message': 'Prediction generated using custom Linear Regression AI.'
        })
    except Exception as e:
        try:
            db.rollback()
        except:
            pass
        logger.error(f"Predict Future Error: {e}")
        return jsonify({'status': 'error', 'message': 'Fitur AI gagal diproses.'})
