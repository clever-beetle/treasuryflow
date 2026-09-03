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

dashboard_bp = Blueprint('dashboard', __name__)

def recalculate_account_balances(db, user_id):
    # Recalculate all account balances for a user to ensure strict consistency
    db.execute('''
        UPDATE accounts
        SET current_balance = COALESCE(initial_balance, 0) + 
            COALESCE((SELECT SUM(amount) FROM transactions WHERE account_id = accounts.id AND type = 'income' AND user_id = ?), 0) - 
            COALESCE((SELECT SUM(amount) FROM transactions WHERE account_id = accounts.id AND type = 'expense' AND user_id = ?), 0)
        WHERE user_id = ?
    ''', (user_id, user_id, user_id))
    db.commit()

@dashboard_bp.route('/')
@login_required
def dashboard():
    db = get_db()
    user_id = session['user_id']
    
    # Sync balances before loading dashboard
    recalculate_account_balances(db, user_id)
    
    filter_account_id = request.args.get('account_id', type=str)
    filter_type = request.args.get('type', type=str)
    
    accounts = db.execute('SELECT * FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    
    today = datetime.now().date()
    today_str = today.strftime('%Y-%m-%d')
    period = request.args.get('period', type=int, default=30)
    if period not in [3, 7, 30, 90, 365]:
        period = 30
        
    days_ago_str = (today - timedelta(days=period)).strftime('%Y-%m-%d')
    
    # Bundle scalar queries into a single round-trip to reduce latency
    stats_query = '''
        SELECT 
            (SELECT SUM(current_balance) FROM accounts WHERE user_id = %(uid)s AND account_type = 'asset') as total_balance,
            (SELECT SUM(amount) FROM transactions WHERE user_id = %(uid)s AND type = 'expense' AND date >= %(days_ago)s AND category != 'Transfer') as total_expense,
            (SELECT SUM(amount) FROM transactions WHERE user_id = %(uid)s AND type = 'income' AND date >= %(days_ago)s AND category != 'Transfer') as total_income,
            (SELECT SUM(amount) FROM transactions WHERE user_id = %(uid)s AND type = 'expense' AND date = %(today)s AND category != 'Transfer') as expense_today,
            (SELECT SUM(limit_amount) FROM budgets WHERE user_id = %(uid)s) as total_budget
    '''
    # SQLite uses ?, Postgres uses %s, but since DBWrapper replaces ? with %s we can use ? safely if we pass tuple
    stats_query_compat = '''
        SELECT 
            (SELECT SUM(current_balance) FROM accounts WHERE user_id = ? AND account_type = 'asset') as total_balance,
            (SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'expense' AND date >= ? AND category != 'Transfer') as total_expense,
            (SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'income' AND date >= ? AND category != 'Transfer') as total_income,
            (SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = 'expense' AND date = ? AND category != 'Transfer') as expense_today,
            (SELECT SUM(limit_amount) FROM budgets WHERE user_id = ?) as total_budget
    '''
    stats = db.execute(stats_query_compat, (user_id, user_id, days_ago_str, user_id, days_ago_str, user_id, today_str, user_id)).fetchone()
    
    total_balance = stats['total_balance'] or 0
    total_expense = stats['total_expense'] or 0
    total_income = stats['total_income'] or 0
    expense_today = stats['expense_today'] or 0
    total_budget = stats['total_budget'] or 0
    budget_usage = (total_expense / total_budget * 100) if total_budget > 0 else 0
    
    # Chart Data
    chart_data_rows = db.execute('''
        SELECT date, type, SUM(amount) as total
        FROM transactions
        WHERE user_id = ? AND date >= ? AND category != 'Transfer'
        GROUP BY date, type
        ORDER BY date ASC
    ''', (user_id, days_ago_str)).fetchall()
    
    date_map = {}
    for i in range(period + 1):
        d = (today - timedelta(days=period - i)).strftime('%Y-%m-%d')
        date_map[d] = {'income': 0, 'expense': 0}
        
    for r in chart_data_rows:
        if r['date'] in date_map:
            date_map[r['date']][r['type']] = r['total']
            
    chart_labels = []
    chart_income = []
    chart_expense = []
    for d, vals in date_map.items():
        chart_labels.append(d[-5:])
        chart_income.append(vals['income'])
        chart_expense.append(vals['expense'])
        
    import json
    chart_data = json.dumps({
        'labels': chart_labels,
        'income': chart_income,
        'expense': chart_expense
    })
    
    upcoming_alerts = []
    current_day = today.day

    db_alerts_debt = db.execute("SELECT * FROM debts_receivables WHERE user_id = ? AND status = 'BELUM LUNAS'", (user_id,)).fetchall()
    db_alerts_inst = db.execute("SELECT * FROM recurring_installments WHERE user_id = ? AND is_active = 1", (user_id,)).fetchall()

    for debt in db_alerts_debt:
        try:
            debt_date = datetime.strptime(debt['due_date'], '%Y-%m-%d').date()
            days_left = (debt_date - today).days
            if 0 <= days_left <= 7:
                upcoming_alerts.append({
                    'name': debt['person_name'],
                    'type': 'Debt/Receivable',
                    'info': f"Due in {days_left} days ({debt['due_date']})",
                    'amount': debt['remaining_amount']
                })
        except ValueError:
            pass

    for inst in db_alerts_inst:
        due_day = inst['due_day_of_month']
        days_left_inst = due_day - current_day
        if 0 <= days_left_inst <= 7:
            upcoming_alerts.append({
                'name': inst['name'],
                'type': 'Subscription',
                'info': f"Bill due in {days_left_inst} days (Every day {due_day})",
                'amount': inst['amount_per_cycle']
            })

    query = '''
        SELECT t.id, t.date, t.description, t.type, t.amount, a.name as account_name
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ?
    '''
    params = [user_id]
    
    if filter_account_id and filter_account_id != 'all':
        query += ' AND t.account_id = ?'
        params.append(filter_account_id)
        
    if filter_type and filter_type != 'all':
        query += ' AND t.type = ?'
        params.append(filter_type)
        
    query += ' ORDER BY t.date DESC LIMIT 25'

    filtered_transactions = db.execute(query, params).fetchall()

    goals = db.execute('''
        SELECT id, name, target_amount, current_amount, due_date,
               (current_amount / target_amount * 100) as percentage
        FROM financial_goals 
        WHERE user_id = ? AND status = 'In Progress'
        ORDER BY due_date ASC LIMIT 2
    ''', (user_id,)).fetchall()
    
    # Expense by Category (Donut Chart)
    cat_rows = db.execute('''
        SELECT category, SUM(amount) as total
        FROM transactions
        WHERE user_id = ? AND type = 'expense' AND date >= ? AND category != 'Transfer'
        GROUP BY category
        ORDER BY total DESC
    ''', (user_id, days_ago_str)).fetchall()
    
    category_chart_data = json.dumps({
        'labels': [r['category'] for r in cat_rows],
        'data': [r['total'] for r in cat_rows]
    })

    # Fetch active budgets & compute monthly usage
    first_day_current_month = today.replace(day=1).strftime('%Y-%m-%d')
    budgets_raw = db.execute('SELECT id, category_name, limit_amount FROM budgets WHERE user_id = ?', (user_id,)).fetchall()
    
    budgets_data = []
    for b in budgets_raw:
        spent_row = db.execute('''
            SELECT SUM(amount) as total FROM transactions
            WHERE user_id = ? AND type = 'expense' AND category = ? AND date >= ?
        ''', (user_id, b['category_name'], first_day_current_month)).fetchone()
        spent = spent_row['total'] if spent_row['total'] else 0
        pct = (spent / b['limit_amount']) * 100 if b['limit_amount'] > 0 else 0
        budgets_data.append({
            'id': b['id'],
            'category_name': b['category_name'],
            'limit_amount': b['limit_amount'],
            'current_spent': spent,
            'percentage': pct
        })

    total_assets = sum(asset['purchase_price'] for asset in db.execute('SELECT purchase_price FROM assets WHERE user_id = ?', (user_id,)).fetchall()) + total_balance
    total_debt_records = sum(debt['remaining_amount'] for debt in db.execute("SELECT remaining_amount FROM debts_receivables WHERE user_id = ? AND status='BELUM LUNAS'", (user_id,)).fetchall())
    total_liability_accounts = db.execute("SELECT SUM(current_balance) FROM accounts WHERE user_id = ? AND account_type = 'liability'", (user_id,)).fetchone()[0] or 0
    total_debt = total_debt_records + abs(total_liability_accounts)
    
    # Financial Health Score Algorithm
    health_score = 50
    if total_income > 0:
        savings_rate = (total_income - total_expense) / total_income
        if savings_rate >= 0.2: health_score += 25
        elif savings_rate > 0: health_score += int(savings_rate * 100)
    
    if total_assets > 0:
        debt_ratio = total_debt / total_assets
        if debt_ratio == 0: health_score += 25
        elif debt_ratio < 0.3: health_score += 15
        elif debt_ratio < 0.5: health_score += 5
    elif total_debt == 0:
        health_score += 25

    health_status = 'Excellent' if health_score >= 80 else 'Good' if health_score >= 50 else 'Warning'

    # AUTO RECURRING SYNC
    current_month_str = today.strftime('%Y-%m')
    first_day_of_month = today.replace(day=1).strftime('%Y-%m-%d')
    import calendar as cal_mod
    last_day = cal_mod.monthrange(today.year, today.month)[1]
    last_day_of_month = today.replace(day=last_day).strftime('%Y-%m-%d')
    installments_sync = db.execute("SELECT * FROM recurring_installments WHERE user_id = ? AND is_active = 1", (user_id,)).fetchall()
    for inst in installments_sync:
        if today.day >= inst['due_day_of_month']:
            desc = f"Auto-Sync: {inst['name']}"
            existing = db.execute("SELECT id FROM transactions WHERE user_id = ? AND description = ? AND date >= ? AND date <= ?", (user_id, desc, first_day_of_month, last_day_of_month)).fetchone()
            if not existing:
                account = db.execute("SELECT id FROM accounts WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
                if account:
                    try:
                        date_str = f"{current_month_str}-{inst['due_day_of_month']:02d}"
                        db.execute('''INSERT INTO transactions (user_id, date, account_id, type, amount, description, category) 
                                      VALUES (?, ?, ?, 'expense', ?, ?, 'Bills')''', 
                                   (user_id, date_str, account['id'], inst['amount_per_cycle'], desc))
                        db.execute('UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?', (inst['amount_per_cycle'], account['id']))
                        db.commit()
                    except Exception as e:
                        try:
                            db.rollback()
                        except:
                            pass
                        logger.error(f"Error sync recurring: {e}")


    # Fetch heatmap data
    days_ago_365 = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    heatmap_raw = db.execute('''
        SELECT date, SUM(amount) as total 
        FROM transactions 
        WHERE user_id = ? AND type = 'expense' AND date >= ?
        GROUP BY date
    ''', (user_id, days_ago_365)).fetchall()
    
    heatmap_data = []
    for r in heatmap_raw:
        heatmap_data.append({
            'date': r['date'],
            'value': r['total']
        })
    heatmap_json = json.dumps(heatmap_data, default=str)

    # BADGES GAMIFICATION
    badges = []
    if total_income > 0 and ((total_income - total_expense) / total_income) >= 0.5:
        badges.append({'icon': 'piggy-bank', 'name': 'The Saver', 'desc': 'Menabung > 50% pemasukan', 'color': 'text-emerald-500', 'bg': 'bg-emerald-500/10'})
    
    if total_debt == 0:
        badges.append({'icon': 'shield-check', 'name': 'Debt Free', 'desc': 'Bebas dari utang aktif', 'color': 'text-blue-500', 'bg': 'bg-blue-500/10'})
        
    tx_last_7_days = db.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND date >= ?", (user_id, days_ago_str)).fetchone()[0]
    if tx_last_7_days >= 3:
        badges.append({'icon': 'flame', 'name': 'Consistent', 'desc': 'Rutin mencatat transaksi', 'color': 'text-orange-500', 'bg': 'bg-orange-500/10'})
    
    # Gamification Check
    ach = db.execute('SELECT * FROM user_achievements WHERE user_id = ?', (user_id,)).fetchone()
    if not ach:
        db.execute("INSERT INTO user_achievements (user_id, xp, level, badges) VALUES (?, 0, 1, '[]')", (user_id,))
        db.commit()
        ach = {'xp': 0, 'level': 1, 'badges': '[]'}
        
    # Process liability accounts for dashboard display
    asset_accounts = []
    for acc in accounts:
        if acc.get('account_type') != 'liability':
            a = dict(acc)
            clean_name = a['name'].split('] ')[1] if '] ' in a['name'] else a['name']
            a['clean_name'] = clean_name
            asset_accounts.append(a)

    liability_accounts_info = []
    for acc in accounts:
        if acc.get('account_type') == 'liability':
            a = dict(acc)
            a['usage'] = abs(a.get('current_balance', 0))
            a['limit'] = a.get('limit_amount', 0) or 0
            a['available'] = max(0, a['limit'] - a['usage']) if a['limit'] > 0 else 0
            a['usage_pct'] = (a['usage'] / a['limit'] * 100) if a['limit'] > 0 else 0
            
            # Compute days until due
            due_day = a.get('billing_due_day')
            if due_day:
                next_due = today.replace(day=min(due_day, 28))
                if next_due <= today:
                    # Move to next month
                    if today.month == 12:
                        next_due = next_due.replace(year=today.year + 1, month=1)
                    else:
                        next_due = next_due.replace(month=today.month + 1)
                a['days_until_due'] = (next_due - today).days
            else:
                a['days_until_due'] = None
            
            clean_name = a['name'].split('] ')[1] if '] ' in a['name'] else a['name']
            a['clean_name'] = clean_name
            liability_accounts_info.append(a)

    return render_template('dashboard.html', ach=ach,
                           total_balance=total_balance, 
                           total_income=total_income,
                           total_expense=total_expense, 
                           expense_today=expense_today,
                           period=period,
                           chart_data=chart_data,
                           category_chart_data=category_chart_data,
                           total_budget=total_budget,
                           budget_usage=budget_usage,
                           accounts=accounts, 
                           asset_accounts=asset_accounts,
                           liability_accounts_info=liability_accounts_info,
                           latest_transactions=filtered_transactions, 
                           filter_account_id=filter_account_id,
                           filter_type=filter_type,
                           upcoming_alerts=upcoming_alerts,
                           goals=goals, budgets_data=budgets_data, health_score=health_score, health_status=health_status, badges=badges, heatmap_json=heatmap_json)

@dashboard_bp.route('/api/data-kalender')
@login_required
def data_kalender():
    user_id = session.get('user_id')
    db = get_db()
    query = '''
        SELECT date, 
               SUM(CASE WHEN type = 'income' AND category != 'Transfer' THEN amount ELSE 0 END) as total_in,
               SUM(CASE WHEN type = 'expense' AND category != 'Transfer' THEN amount ELSE 0 END) as total_out
        FROM transactions WHERE user_id = ? GROUP BY date
    '''
    rows = db.execute(query, (user_id,)).fetchall()
    events = []
    for row in rows:
        if row['total_in'] > 0:
            events.append({'title': f"+{row['total_in']:,.0f}", 'start': row['date'], 'backgroundColor': '#E8EAF6', 'textColor': '#11237E', 'display': 'block'})
        if row['total_out'] > 0:
            events.append({'title': f"-{row['total_out']:,.0f}", 'start': row['date'], 'backgroundColor': '#FEE2E2', 'textColor': '#EF4444', 'display': 'block'})
    return jsonify(events)