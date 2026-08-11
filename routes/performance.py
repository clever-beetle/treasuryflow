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
@cache.cached(timeout=30, query_string=True, unless=lambda: request.method == 'POST')
def financial_performance():
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
    total_net_worth = sum(acc['current_balance'] for acc in accounts_data)
    theme_colors = ["#11237e", "#3f51b5", "#7986cb", "#9fa8da", "#c5cae9"]
    
    distribution_list = []
    if total_net_worth > 0:
        for index, acc in enumerate(accounts_data):
            percentage = (acc['current_balance'] / total_net_worth) * 100
            clean_name = acc['name'].split('] ')[1] if '] ' in acc['name'] else acc['name']
            if acc['current_balance'] > 0:
                distribution_list.append({
                    'name': clean_name,
                    'balance': acc['current_balance'],
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
    total_asset_value = sum(asset['purchase_price'] for asset in assets_list)

    asset_alloc_raw = db.execute("SELECT category, SUM(purchase_price) as total FROM assets WHERE user_id = ? GROUP BY category", (user_id,)).fetchall()
    import json
    asset_alloc = json.dumps({
        'labels': [a['category'] for a in asset_alloc_raw],
        'data': [a['total'] for a in asset_alloc_raw]
    })

    goals_list = db.execute('''
        SELECT id, name, target_amount, current_amount, due_date, status,
               CASE WHEN target_amount = 0 THEN 0 ELSE (current_amount / target_amount * 100) END as percentage
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

    credit_cards = db.execute('SELECT * FROM credit_cards WHERE user_id = ?', (user_id,)).fetchall()
    total_saldo = sum(acc['current_balance'] for acc in db.execute('SELECT current_balance FROM accounts WHERE user_id = ?', (user_id,)).fetchall())
    total_debt = sum(r['remaining_amount'] for r in records_active)
    total_cc_usage = sum(cc['current_usage'] for cc in credit_cards)
    total_cc_limit = sum(cc['limit_amount'] for cc in credit_cards)
    total_annual_subscriptions = sum(inst['amount_per_cycle'] * 12 for inst in installments)
    net_worth = total_saldo + total_asset_value - total_debt - total_cc_usage

    
    # --- Analytics Integration ---
    period = request.args.get('period', type=int, default=30)
    if period not in [7, 30, 90, 180, 365]:
        period = 30
        
    today_dt = datetime.now()
    days_ago_str = (today_dt - timedelta(days=period)).strftime('%Y-%m-%d')
    
    analytics_transactions = db.execute('''
        SELECT t.id, t.date, t.type, t.amount, t.category, t.description, a.name AS account_name
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ? AND t.date >= ? AND t.category != 'Transfer'
        ORDER BY t.date ASC
    ''', (user_id, days_ago_str)).fetchall()
    
    analytics_total_income = sum(t['amount'] for t in analytics_transactions if t['type'] == 'income')
    analytics_total_expense = sum(t['amount'] for t in analytics_transactions if t['type'] == 'expense')
    analytics_net_flow = analytics_total_income - analytics_total_expense
    analytics_savings_rate = (analytics_net_flow / analytics_total_income * 100) if analytics_total_income > 0 else 0
    
    date_map = {}
    for i in range(period + 1):
        d = (today_dt - timedelta(days=period - i)).strftime('%Y-%m-%d')
        date_map[d] = {'income': 0, 'expense': 0}
        
    for t in analytics_transactions:
        if t['date'] in date_map:
            date_map[t['date']][t['type']] += t['amount']
            
    chart_labels = []
    chart_income = []
    chart_expense = []
    chart_netflow = []
    cumulative_net = 0
    for d, vals in date_map.items():
        chart_labels.append(d[-5:])
        chart_income.append(vals['income'])
        chart_expense.append(vals['expense'])
        cumulative_net += (vals['income'] - vals['expense'])
        chart_netflow.append(cumulative_net)
        
    import json
    analytics_time_series = json.dumps({
        'labels': chart_labels,
        'income': chart_income,
        'expense': chart_expense,
        'netflow': chart_netflow
    })
    
    cat_map = {}
    for t in analytics_transactions:
        if t['type'] == 'expense':
            cat_map[t['category']] = cat_map.get(t['category'], 0) + t['amount']
            
    sorted_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)
    analytics_donut = json.dumps({
        'labels': [c[0] for c in sorted_cats],
        'data': [c[1] for c in sorted_cats]
    })
    
    analytics_insights = []
    if analytics_total_income > 0:
        if analytics_savings_rate >= 20:
            analytics_insights.append({"icon": "trending-up", "color": "emerald-500", "title": "Great Savings Rate", "desc": f"You saved {analytics_savings_rate:.1f}% of your income this period. Excellent financial discipline!"})
        elif analytics_savings_rate > 0:
            analytics_insights.append({"icon": "minus-circle", "color": "blue-500", "title": "Positive Cash Flow", "desc": f"You are saving {analytics_savings_rate:.1f}%. Try to aim for 20% by reducing non-essentials."})
        else:
            analytics_insights.append({"icon": "alert-triangle", "color": "destructive", "title": "Negative Cash Flow", "desc": "You spent more than you earned. Review your top expenses to cut back."})
    else:
        analytics_insights.append({"icon": "info", "color": "muted-foreground", "title": "No Income Recorded", "desc": "Add income transactions to calculate your savings rate."})
        
    if sorted_cats:
        top_cat = sorted_cats[0]
        pct = (top_cat[1] / analytics_total_expense * 100) if analytics_total_expense > 0 else 0
        analytics_insights.append({"icon": "pie-chart", "color": "amber-500", "title": f"Top Expense: {top_cat[0]}", "desc": f"You spent Rp {top_cat[1]:,.0f} on {top_cat[0]}, which is {pct:.1f}% of your total expenses."})
    # --- End Analytics Integration ---
    return render_template('financial_performance.html', 
                           expense_custom_range=expense_custom_range, income_custom_range=income_custom_range,
                           avg_expense_daily=avg_expense_daily, avg_income_daily=avg_income_daily,
                           proyeksi_seminggu_out=proyeksi_seminggu_out, proyeksi_sebulan_out=proyeksi_sebulan_out,
                           max_expense=max_expense, min_expense=min_expense, days_range=days_range,
                           distribution_list=distribution_list, records_active=records_active, records_history=records_history, 
                           accounts=clean_accounts, installments=installments,
                           assets_list=assets_list, total_asset_value=total_asset_value, goals_list=goals_list,
                           savings_rate=savings_rate, smart_insight=smart_insight, insight_type=insight_type,
                           credit_cards=credit_cards, net_worth=net_worth, total_saldo=total_saldo,
                           total_debt=total_debt, total_cc_usage=total_cc_usage, total_cc_limit=total_cc_limit,
                           total_annual_subscriptions=total_annual_subscriptions,
                           analytics_period=period, analytics_total_income=analytics_total_income,
                           analytics_total_expense=analytics_total_expense, analytics_net_flow=analytics_net_flow,
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

