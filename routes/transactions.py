from flask import Blueprint, render_template, request, url_for, redirect, session, flash, Response, jsonify, send_file, make_response
from utils import get_db, login_required, CATEGORIES
from datetime import datetime
import io
import csv
from fpdf import FPDF
import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.chart import BarChart, Reference

transactions_bp = Blueprint('transactions', __name__)

@transactions_bp.route('/calendar', strict_slashes=False, endpoint='transactions_calendar')
@login_required
def transactions_calendar():
    from flask import request
    # Pass all query args to transactions_list but override view
    args = request.args.copy()
    args['view'] = 'calendar'
    request.args = args
    return transactions_list()

@transactions_bp.route('', strict_slashes=False)
@transactions_bp.route('/', strict_slashes=False)
@login_required
def transactions_list():
    db = get_db()
    user_id = session['user_id']
    view = request.args.get('view', 'list')
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    selected_category = request.args.get('category', '')
    selected_account = request.args.get('account_id', '')
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'desc')
    
    # Base query
    query = '''
        SELECT t.*, a.name as account_name 
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ?
    '''
    params = [user_id]
    
    if search_query:
        query += ' AND t.description LIKE ?'
        params.append(f'%{search_query}%')
    if start_date:
        query += ' AND t.date >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND t.date <= ?'
        params.append(end_date)
    if selected_category:
        query += ' AND t.category = ?'
        params.append(selected_category)
    if selected_account:
        query += ' AND t.account_id = ?'
        params.append(selected_account)
        
    # Validate sort parameters to prevent SQL injection
    allowed_sort_columns = {'date', 'amount', 'category', 'description', 'type'}
    allowed_sort_orders = {'asc', 'desc'}
    if sort_by not in allowed_sort_columns:
        sort_by = 'date'
    if sort_order.lower() not in allowed_sort_orders:
        sort_order = 'desc'
        
    query += f' ORDER BY t.{sort_by} {sort_order}'
    
    transactions = db.execute(query, params).fetchall()
    
    # Calculate totals
    total_income = sum(t['amount'] for t in transactions if t['type'] == 'income')
    total_expense = sum(t['amount'] for t in transactions if t['type'] == 'expense')
    net_flow = total_income - total_expense
    
    # Pagination for list view
    per_page = 20
    total_tx = len(transactions)
    total_pages = (total_tx + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    
    tx_page = transactions[start:end]
    
    accounts = db.execute('SELECT * FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    
    # Calendar data
    import calendar
    now = datetime.now()
    now_date = now.date()
    cal_year = request.args.get('cal_year', now.year, type=int)
    cal_month = request.args.get('cal_month', now.month, type=int)
    
    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(cal_year, cal_month)
    
    from datetime import date as dt_date, datetime as dt_datetime
    cal_tx_map = {}
    for tx in transactions:
        d_val = tx['date']
        if isinstance(d_val, (dt_datetime, dt_date)):
            d_str = d_val.strftime('%Y-%m-%d')
        else:
            d_str = str(d_val)[:10]
        if d_str not in cal_tx_map:
            cal_tx_map[d_str] = {'income': 0, 'expense': 0}
        cal_tx_map[d_str][tx['type']] += tx['amount']
    
    return render_template('transactions_list.html', 
                           month_days=month_days,
                           transactions=tx_page, 
                           all_transactions=transactions,
                           total_income=total_income,
                           total_expense=total_expense,
                           net_flow=net_flow,
                           view=view,
                           page=page,
                           total_pages=total_pages,
                           search_query=search_query,
                           start_date=start_date,
                           end_date=end_date,
                           selected_category=selected_category,
                           selected_account=selected_account,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           accounts=accounts,
                           categories=CATEGORIES,
                           cal_year=cal_year,
                           cal_month=cal_month,
                           now=now_date,
                           cal_tx_map=cal_tx_map,
                           month_name=datetime(cal_year, cal_month, 1).strftime('%B'))

@transactions_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_transaction():
    db = get_db()
    user_id = session['user_id']
    if request.method == 'POST':
        t_type = request.form.get('type')
        date = request.form.get('date')
        amount_str = request.form.get('amount', '0').replace('.', '').replace(',', '')
        amount = float(amount_str) if amount_str else 0
        category = request.form.get('category')
        account_id = request.form.get('account_id')
        description = request.form.get('description', '')
        to_account_id = request.form.get('to_account_id')
        
        if t_type == 'transfer':
            if account_id == to_account_id:
                flash('Cannot transfer to same account', 'danger')
                return redirect(url_for('transactions.add_transaction'))
                
            db.execute('''
                INSERT INTO transactions (user_id, account_id, date, type, amount, description, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, account_id, date, 'expense', amount, f'Transfer to account {to_account_id}: {description}', 'Transfer'))
            
            db.execute('''
                INSERT INTO transactions (user_id, account_id, date, type, amount, description, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, to_account_id, date, 'income', amount, f'Transfer from account {account_id}: {description}', 'Transfer'))
            
            db.execute('UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?', (amount, account_id))
            db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (amount, to_account_id))
        else:
            db.execute('''
                INSERT INTO transactions (user_id, account_id, date, type, amount, description, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, account_id, date, t_type, amount, description, category))
            
            if t_type == 'income':
                db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (amount, account_id))
            else:
                db.execute('UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?', (amount, account_id))
                
        db.commit()
        flash('Transaction added', 'success')
        return redirect(url_for('transactions.transactions_list'))
        
    accounts = db.execute('SELECT * FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    return render_template('add_transaction.html', accounts=accounts, categories=CATEGORIES, now=datetime.now())

@transactions_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    db = get_db()
    user_id = session['user_id']
    tx = db.execute('SELECT * FROM transactions WHERE id = ? AND user_id = ?', (id, user_id)).fetchone()
    if not tx:
        flash('Transaction not found', 'danger')
        return redirect(url_for('transactions.transactions_list'))
        
    if request.method == 'POST':
        # Revert old balance
        if tx['type'] == 'income':
            db.execute('UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?', (tx['amount'], tx['account_id']))
        else:
            db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (tx['amount'], tx['account_id']))
            
        # Apply new
        t_type = request.form.get('type')
        date = request.form.get('date')
        amount_str = request.form.get('amount', '0').replace('.', '').replace(',', '')
        amount = float(amount_str) if amount_str else 0
        category = request.form.get('category')
        account_id = request.form.get('account_id')
        description = request.form.get('description', '')
        
        db.execute('''
            UPDATE transactions 
            SET account_id=?, date=?, type=?, amount=?, description=?, category=?
            WHERE id=? AND user_id=?
        ''', (account_id, date, t_type, amount, description, category, id, user_id))
        
        if t_type == 'income':
            db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (amount, account_id))
        else:
            db.execute('UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?', (amount, account_id))
            
        db.commit()
        flash('Transaction updated', 'success')
        return redirect(url_for('transactions.transactions_list'))
        
    accounts = db.execute('SELECT * FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    return render_template('add_transaction.html', tx=tx, accounts=accounts, categories=CATEGORIES)

@transactions_bp.route('/delete/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    db = get_db()
    user_id = session['user_id']
    tx = db.execute('SELECT * FROM transactions WHERE id = ? AND user_id = ?', (transaction_id, user_id)).fetchone()
    if tx:
        if tx['type'] == 'income':
            db.execute('UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?', (tx['amount'], tx['account_id']))
        else:
            db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (tx['amount'], tx['account_id']))
        db.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
        db.commit()
        flash('Transaction deleted', 'success')
    return redirect(url_for('transactions.transactions_list'))

@transactions_bp.route('/bulk_delete', methods=['POST'])
@login_required
def bulk_delete_transactions():
    db = get_db()
    user_id = session['user_id']
    tx_ids = request.form.getlist('transaction_ids')
    for tid in tx_ids:
        tx = db.execute('SELECT * FROM transactions WHERE id = ? AND user_id = ?', (tid, user_id)).fetchone()
        if tx:
            if tx['type'] == 'income':
                db.execute('UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?', (tx['amount'], tx['account_id']))
            else:
                db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (tx['amount'], tx['account_id']))
            db.execute('DELETE FROM transactions WHERE id = ?', (tid,))
    db.commit()
    flash('Selected transactions deleted', 'success')
    return redirect(url_for('transactions.transactions_list'))

@transactions_bp.route('/bulk_edit', methods=['POST'])
@login_required
def bulk_edit_transactions():
    db = get_db()
    user_id = session['user_id']
    tx_ids = request.form.get('transaction_ids_bulk', '').split(',')
    category = request.form.get('bulk_category')
    
    if category and tx_ids:
        for tid in tx_ids:
            if tid:
                db.execute('UPDATE transactions SET category = ? WHERE id = ? AND user_id = ?', (category, tid, user_id))
        db.commit()
        flash('Transactions updated', 'success')
    return redirect(url_for('transactions.transactions_list'))

@transactions_bp.route('/export_csv')
@login_required
def export_csv():
    db = get_db()
    user_id = session['user_id']
    transactions = db.execute('''
        SELECT t.date, t.type, t.amount, t.description, t.category, a.name as account_name 
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ? ORDER BY t.date DESC
    ''', (user_id,)).fetchall()
    
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Date', 'Type', 'Amount', 'Description', 'Category', 'Account'])
    for t in transactions:
        cw.writerow([t['date'], t['type'], t['amount'], t['description'], t['category'], t['account_name']])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=transactions.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@transactions_bp.route('/export_excel')
@login_required
def export_excel():
    db = get_db()
    user_id = session['user_id']
    transactions = db.execute('''
        SELECT t.date, t.type, t.amount, t.description, t.category, a.name as account_name 
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ? ORDER BY t.date DESC
    ''', (user_id,)).fetchall()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"
    headers = ['Date', 'Type', 'Amount (Rp)', 'Description', 'Category', 'Account']
    ws.append(headers)
    
    header_fill = PatternFill(start_color="11237E", end_color="11237E", fill_type="solid")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill

    cat_totals = {}
    row_idx = 2
    for tx in transactions:
        amount = tx['amount']
        type_cap = tx['type'].capitalize() if tx['type'] else ''
        ws.append([tx['date'], type_cap, amount, tx['description'], tx['category'], tx['account_name']])
        if tx['type'] == 'expense':
            cat = tx['category']
            cat_totals[cat] = cat_totals.get(cat, 0) + amount
        ws.cell(row=row_idx, column=3).number_format = '#,##0'
        row_idx += 1

    if cat_totals:
        ws_chart = wb.create_sheet("Expense Analysis")
        ws_chart.append(["Category", "Total Spent"])
        r = 2
        for cat, total in cat_totals.items():
            ws_chart.append([cat, total])
            r += 1
        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = "Expenses by Category"
        chart.y_axis.title = 'Amount (Rp)'
        chart.x_axis.title = 'Category'
        data = Reference(ws_chart, min_col=2, min_row=1, max_row=r-1, max_col=2)
        cats = Reference(ws_chart, min_col=1, min_row=2, max_row=r-1)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        ws_chart.add_chart(chart, "D2")

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, download_name="finance_report.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@transactions_bp.route('/export_pdf')
@login_required
def export_pdf():
    db = get_db()
    user_id = session['user_id']
    transactions = db.execute('''
        SELECT t.date, t.type, t.amount, t.description, t.category, a.name as account_name 
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ? ORDER BY t.date DESC
    ''', (user_id,)).fetchall()
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Transactions Report", ln=1, align='C')
    for t in transactions:
        pdf.cell(200, 10, txt=f"{t['date']} - {t['type']} - Rp{t['amount']} - {t['category']} - {t['description']}", ln=1)
    
    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers.set('Content-Disposition', 'attachment', filename='transactions.pdf')
    response.headers.set('Content-Type', 'application/pdf')
    return response

@transactions_bp.route('/transaction/<int:id>/receipt')
@login_required
def download_receipt(id):
    user_id = session['user_id']
    db = get_db()
    tx = db.execute('''
        SELECT t.*, a.name as account_name 
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.id = ? AND t.user_id = ?
    ''', (id, user_id)).fetchone()
    
    if not tx:
        flash('Transaction not found', 'danger')
        return redirect(url_for('transactions.transactions_list'))
        
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=15)
    pdf.cell(200, 10, txt="TREASURY FLOW - TRANSACTION RECEIPT", ln=1, align='C')
    pdf.cell(200, 10, txt="--------------------------------------------------", ln=1, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Date: {tx['date']}", ln=1)
    pdf.cell(200, 10, txt=f"Account: {tx['account_name']}", ln=1)
    pdf.cell(200, 10, txt=f"Type: {tx['type'].upper()}", ln=1)
    pdf.cell(200, 10, txt=f"Category: {tx['category']}", ln=1)
    pdf.cell(200, 10, txt=f"Description: {tx['description']}", ln=1)
    pdf.cell(200, 10, txt=f"Amount: Rp {tx['amount']:,.0f}", ln=1)
    pdf.cell(200, 10, txt="--------------------------------------------------", ln=1, align='C')
    pdf.cell(200, 10, txt="Generated automatically by Treasury Flow", ln=1, align='C')
    
    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers.set('Content-Disposition', 'attachment', filename=f'receipt_{id}.pdf')
    response.headers.set('Content-Type', 'application/pdf')
    return response
