from flask import Blueprint, render_template, request, url_for, redirect, session, g, flash, Response, jsonify
from utils import get_db, login_required, format_rupiah, format_rupiah_input, CATEGORIES, cache
from models import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets, smtplib, json, csv, os
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fpdf import FPDF

performance_bp = Blueprint('performance', __name__)

@performance_bp.route('/financial_performance', methods=['GET', 'POST'])
@login_required
def financial_performance():
    try:
        db = get_db()
        user_id = session['user_id']

        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'add_debt':
                person_name = request.form.get('person_name')
                type_record = request.form.get('type')
                raw_amount = request.form.get('total_amount', '0').replace('.', '').replace(',', '.')
                total_amount = float(raw_amount)
                due_date = request.form.get('due_date')
                notes = request.form.get('notes')
                
                db.execute('''
                    INSERT INTO debts_receivables (user_id, person_name, type, total_amount, remaining_amount, due_date, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, person_name, type_record, total_amount, total_amount, due_date, notes))
                db.commit()
                
            elif action == 'pay_debt':
                debt_id = int(request.form.get('debt_id'))
                target_account_id = int(request.form.get('account_name'))
                raw_paid = request.form.get('amount_paid', '0').replace('.', '').replace(',', '.')
                amount_paid = float(raw_paid)
                notes = request.form.get('notes')
                
                debt = db.execute("SELECT * FROM debts_receivables WHERE id = ?", (debt_id,)).fetchone()
                acc_row = db.execute("SELECT name FROM accounts WHERE id = ?", (target_account_id,)).fetchone()
                
                if debt and acc_row:
                    new_remaining = float(debt['remaining_amount']) - amount_paid
                    if new_remaining < 0: new_remaining = 0.0
                    new_status = 'LUNAS' if new_remaining <= 0 else 'BELUM LUNAS'
                    
                    db.execute('UPDATE debts_receivables SET remaining_amount = ?, status = ? WHERE id = ?', (new_remaining, new_status, debt_id))
                    db.execute('INSERT INTO debt_payments (debt_id, account_name, amount_paid, notes) VALUES (?, ?, ?, ?)', (debt_id, acc_row['name'], amount_paid, notes))
                    
                    cash_flow_type = 'expense' if debt['type'] == 'debt' else 'income'
                    clean_acc_label = acc_row['name'].split('] ')[1] if '] ' in acc_row['name'] else acc_row['name']
                    tx_desc = f"Cicilan {debt['type']} ({debt['person_name']}) via {clean_acc_label}: {notes}"
                    tx_date = datetime.now().strftime('%Y-%m-%d')
                    
                    db.execute('''
                        INSERT INTO transactions (user_id, date, account_id, type, amount, description, category)
                        VALUES (?, ?, ?, ?, ?, ?, 'Utang-Piutang')
                    ''', (user_id, tx_date, target_account_id, cash_flow_type, amount_paid, tx_desc))
                    
                    adjustment = -amount_paid if cash_flow_type == 'expense' else amount_paid
                    db.execute("UPDATE accounts SET current_balance = current_balance + ? WHERE id = ? AND user_id = ?", (adjustment, target_account_id, user_id))
                    db.commit()

            elif action == 'delete_debt':
                debt_id = int(request.form.get('debt_id'))
                db.execute("DELETE FROM debts_receivables WHERE id = ? AND user_id = ?", (debt_id, user_id))
                db.execute("DELETE FROM debt_payments WHERE debt_id = ?", (debt_id,))
                db.commit()
                    
            elif action == 'add_installment':
                name = request.form.get('name')
                raw_cycle_amount = request.form.get('amount_per_cycle', '0').replace('.', '').replace(',', '.')
                amount_per_cycle = float(raw_cycle_amount)
                due_day = int(request.form.get('due_day_of_month', 1))
                is_tenor = int(request.form.get('is_temporary_tenor', 0))
                total_tenor = request.form.get('total_tenor')
                total_tenor = int(total_tenor) if total_tenor else None
                
                db.execute('''
                    INSERT INTO recurring_installments (user_id, name, amount_per_cycle, due_day_of_month, is_temporary_tenor, total_tenor, current_tenor)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                ''', (user_id, name, amount_per_cycle, due_day, is_tenor, total_tenor))
                db.commit()

            elif action == 'edit_installment':
                inst_id = int(request.form.get('inst_id'))
                name = request.form.get('name')
                raw_cycle_amount = request.form.get('amount_per_cycle', '0').replace('.', '').replace(',', '.')
                amount_per_cycle = float(raw_cycle_amount)
                due_day = int(request.form.get('due_day_of_month', 1))
                is_tenor = int(request.form.get('is_temporary_tenor', 0))
                total_tenor = request.form.get('total_tenor')
                total_tenor = int(total_tenor) if total_tenor else None
                
                db.execute('''
                    UPDATE recurring_installments 
                    SET name = ?, amount_per_cycle = ?, due_day_of_month = ?, is_temporary_tenor = ?, total_tenor = ?
                    WHERE id = ? AND user_id = ?
                ''', (name, amount_per_cycle, due_day, is_tenor, total_tenor, inst_id, user_id))
                db.commit()

            elif action == 'delete_installment':
                inst_id = int(request.form.get('inst_id'))
                db.execute("DELETE FROM recurring_installments WHERE id = ? AND user_id = ?", (inst_id, user_id))
                db.commit()

            elif action == 'add_asset':
                asset_name = request.form.get('asset_name')
                category = request.form.get('category')
                purchase_date = request.form.get('purchase_date')
                raw_price = request.form.get('purchase_price', '0').replace('.', '').replace(',', '.')
                purchase_price = float(raw_price)
                quantity = request.form.get('quantity')
                notes = request.form.get('notes')
                
                db.execute('''
                    INSERT INTO assets (user_id, asset_name, category, purchase_date, purchase_price, quantity, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, asset_name, category, purchase_date, purchase_price, quantity, notes))
                db.commit()

            elif action == 'edit_asset':
                asset_id = int(request.form.get('asset_id'))
                asset_name = request.form.get('asset_name')
                category = request.form.get('category')
                purchase_date = request.form.get('purchase_date')
                raw_price = request.form.get('purchase_price', '0').replace('.', '').replace(',', '.')
                purchase_price = float(raw_price)
                quantity = request.form.get('quantity')
                notes = request.form.get('notes')
                
                db.execute('''
                    UPDATE assets 
                    SET asset_name = ?, category = ?, purchase_date = ?, purchase_price = ?, quantity = ?, notes = ?
                    WHERE id = ? AND user_id = ?
                ''', (asset_name, category, purchase_date, purchase_price, quantity, notes, asset_id, user_id))
                db.commit()

            elif action == 'delete_asset':
                asset_id = int(request.form.get('asset_id'))
                db.execute("DELETE FROM assets WHERE id = ? AND user_id = ?", (asset_id, user_id))
                db.commit()

            elif action == 'add_goal':
                name = request.form.get('goal_name')
                target = float(request.form.get('target_amount', '0').replace('.', '').replace(',', '.'))
                current = request.form.get('current_amount', '0').replace('.', '').replace(',', '.')
                current = float(current) if current else 0.0
                due_date = request.form.get('due_date')
                
                db.execute('''
                    INSERT INTO financial_goals (user_id, name, target_amount, current_amount, due_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, name, target, current, due_date))
                db.commit()

            elif action == 'saving_goal':
                goal_id = int(request.form.get('goal_id'))
                amount = float(request.form.get('saving_amount', '0').replace('.', '').replace(',', '.'))
                
                db.execute('''
                    UPDATE financial_goals 
                    SET current_amount = current_amount + ? 
                    WHERE id = ? AND user_id = ?
                ''', (amount, goal_id, user_id))
                
                goal = db.execute('SELECT target_amount, current_amount FROM financial_goals WHERE id = ?', (goal_id,)).fetchone()
                if goal['current_amount'] >= goal['target_amount']:
                    db.execute("UPDATE financial_goals SET status = 'Achieved' WHERE id = ?", (goal_id,))
                    
                db.commit()

            elif action == 'delete_goal':
                goal_id = int(request.form.get('goal_id'))
                db.execute('DELETE FROM financial_goals WHERE id = ? AND user_id = ?', (goal_id, user_id))
                db.commit()
                
            return redirect(url_for('performance.financial_performance'))

        days_range = request.args.get('days', type=int, default=7)
        if days_range not in [3, 7, 30, 90, 180, 365]: days_range = 7
            
        today = datetime.now().date()
        today_str = today.strftime('%Y-%m-%d')
        days_ago_str = (today - timedelta(days=days_range)).strftime('%Y-%m-%d')
        
        accounts_data = db.execute("SELECT name, initial_balance, current_balance FROM accounts WHERE user_id = ?", (user_id,)).fetchall()
        total_net_worth = sum((acc['current_balance'] or 0) for acc in accounts_data)
        theme_colors = ["#11237e", "#3f51b5", "#7986cb", "#9fa8da", "#c5cae9"]
        
        distribution_list = []
        if total_net_worth > 0:
            for index, acc in enumerate(accounts_data):
                current = acc['current_balance'] or 0
                percentage = (current / total_net_worth) * 100
                clean_name = acc['name'].split('] ')[1] if '] ' in acc['name'] else acc['name']
                if current > 0:
                    distribution_list.append({
                        'name': clean_name,
                        'balance': current,
                        'percentage': round(percentage, 1),
                        'color': theme_colors[index % len(theme_colors)]
                    })

        expense_custom_range = db.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND category != 'Transfer' AND date BETWEEN ? AND ?", (user_id, days_ago_str, today_str)).fetchone()[0]
        income_custom_range = db.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'income' AND category != 'Transfer' AND date BETWEEN ? AND ?", (user_id, days_ago_str, today_str)).fetchone()[0]
        max_expense = db.execute("SELECT COALESCE(MAX(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND category != 'Transfer' AND date BETWEEN ? AND ?", (user_id, days_ago_str, today_str)).fetchone()[0]
        min_expense = db.execute("SELECT COALESCE(MIN(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND category != 'Transfer' AND date BETWEEN ? AND ?", (user_id, days_ago_str, today_str)).fetchone()[0]

        avg_expense_daily = expense_custom_range / days_range
        avg_income_daily = income_custom_range / days_range
        proyeksi_seminggu_out = avg_expense_daily * 7
        proyeksi_sebulan_out = avg_expense_daily * 30

        records_active = db.execute("SELECT * FROM debts_receivables WHERE user_id = ? AND status = 'BELUM LUNAS' ORDER BY due_date ASC", (user_id,)).fetchall()
        records_history = db.execute("SELECT * FROM debts_receivables WHERE user_id = ? AND status = 'LUNAS' ORDER BY due_date DESC", (user_id,)).fetchall()
        
        raw_accounts = db.execute("SELECT id, name FROM accounts WHERE user_id = ?", (user_id,)).fetchall()
        clean_accounts = []
        for acc in raw_accounts:
            clean_label = acc['name'].split('] ')[1] if '] ' in acc['name'] else acc['name']
            clean_accounts.append({'raw': acc['id'], 'clean': clean_label})

        installments = db.execute("SELECT * FROM recurring_installments WHERE user_id = ? AND is_active = 1 ORDER BY due_day_of_month ASC", (user_id,)).fetchall()

        assets_list = db.execute("SELECT * FROM assets WHERE user_id = ? ORDER BY purchase_date DESC", (user_id,)).fetchall()
        total_asset_value = sum((asset['purchase_price'] or 0) for asset in assets_list)

        asset_alloc_raw = db.execute("SELECT category, COALESCE(SUM(purchase_price), 0) as total FROM assets WHERE user_id = ? GROUP BY category", (user_id,)).fetchall()
        import json
        asset_alloc = json.dumps({
            'labels': [a['category'] for a in asset_alloc_raw],
            'data': [float(a['total']) for a in asset_alloc_raw]
        })

        goals_list = db.execute('''
            SELECT id, name, target_amount, current_amount, due_date, status,
                COALESCE((current_amount / NULLIF(target_amount, 0) * 100), 0) as percentage
            FROM financial_goals WHERE user_id = ? ORDER BY status DESC, due_date ASC
        ''', (user_id,)).fetchall()

        savings_rate = 0
        if income_custom_range > 0:
            savings_rate = ((income_custom_range - expense_custom_range) / income_custom_range) * 100

        prev_period_start = (today - timedelta(days=days_range*2)).strftime('%Y-%m-%d')
        prev_period_end = (today - timedelta(days=days_range+1)).strftime('%Y-%m-%d')
        prev_expense_row = db.execute('''
            SELECT SUM(amount) as total FROM transactions
            WHERE user_id = ? AND type = 'expense' AND date >= ? AND date <= ? AND category != 'Transfer'
        ''', (user_id, prev_period_start, prev_period_end)).fetchone()
        prev_expense = prev_expense_row['total'] if prev_expense_row['total'] else 0
        
        if prev_expense > 0:
            diff_pct = ((expense_custom_range - prev_expense) / prev_expense) * 100
            if diff_pct > 5:
                smart_insight = f"Perhatian: Pengeluaran {days_range} hari terakhir Anda naik {diff_pct:.1f}% dibanding periode sebelumnya."
                insight_type = "warning"
            elif diff_pct < -5:
                smart_insight = f"Kerja bagus! Pengeluaran {days_range} hari terakhir Anda turun {abs(diff_pct):.1f}% dibanding periode sebelumnya."
                insight_type = "success"
            else:
                smart_insight = f"Pengeluaran {days_range} hari terakhir stabil dibanding periode sebelumnya."
                insight_type = "neutral"
        else:
            smart_insight = "Terus catat transaksi Anda agar AI dapat membandingkan pengeluaran periode ini dan sebelumnya."
            insight_type = "neutral"
                           analytics_savings_rate=analytics_savings_rate, analytics_time_series=analytics_time_series,
                           analytics_donut=analytics_donut, analytics_insights=analytics_insights)

@performance_bp.route('/manage_budget', methods=['POST'])
@login_required
def manage_budget():
    db = get_db()
    user_id = session['user_id']
    action = request.form.get('action')
    
    if action == 'add':
        category_name = request.form.get('category_name')
        raw_limit = request.form.get('limit_amount', '0').replace('.', '').replace(',', '.')
        limit_amount = float(raw_limit)
        
        try:
            db.execute('INSERT INTO budgets (user_id, category_name, limit_amount) VALUES (?, ?, ?)', 
                       (user_id, category_name, limit_amount))
            db.commit()
            flash('Anggaran berhasil ditambahkan!', 'success')
        except db.IntegrityError:
            flash('Anggaran untuk kategori ini sudah ada.', 'warning')
            
    elif action == 'delete':
        budget_id = request.form.get('budget_id')
        db.execute('DELETE FROM budgets WHERE id = ? AND user_id = ?', (budget_id, user_id))
        db.commit()
        flash('Anggaran berhasil dihapus.', 'success')
        
    return redirect(url_for('dashboard.dashboard'))

