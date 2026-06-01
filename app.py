import os
import sqlite3
import locale
import csv 
import secrets
from io import StringIO 
from datetime import datetime, timedelta 
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, url_for, redirect, session, g, flash, Response, jsonify
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'kunci_rahasia_default_yang_harus_diganti')

DATABASE = 'treasury_flow.db'

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = "treasuryflow@gmail.com"
SMTP_PASSWORD = "mhqefkbwcunkptvj"

CATEGORIES = {
    'income': ['Gaji', 'Investasi', 'Hadiah', 'Penjualan Aset', 'Lainnya (Pemasukan)'],
    'expense': ['Makanan & Minuman', 'Transportasi', 'Belanja', 'Tagihan', 
                'Hiburan', 'Kesehatan', 'Pendidikan', 'Cicilan & Utang', 'Lainnya (Pengeluaran)']
}

def format_rupiah(value):
    if value is None:
        return 'Rp 0,00'
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 'Rp 0,00'
    try:
        sign = "-" if value < 0 else ""
        abs_value = abs(value)
        formatted = locale.format_string("%.2f", abs_value, grouping=True)
        return sign + 'Rp ' + formatted
    except Exception:
        sign = "-" if value < 0 else ""
        abs_value = abs(value)
        return sign + 'Rp {:.2f}'.format(abs_value).replace('.', '#').replace(',', '.').replace('#', ',')

def format_rupiah_input(value):
    if value is None:
        return '0,00'
    try:
        formatted = locale.format_string("%.2f", value, grouping=True)
        return formatted
    except Exception:
        return '{:.2f}'.format(value).replace('.', '#').replace(',', '.').replace('#', ',')

app.jinja_env.filters['rupiah'] = format_rupiah
app.jinja_env.filters['format_rupiah_input'] = format_rupiah_input

try:
    locale.setlocale(locale.LC_ALL, 'id_ID.utf8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'indonesian')
    except locale.Error:
        pass 

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fullname TEXT, 
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                password TEXT NOT NULL,
                reset_token TEXT,
                token_expiry TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                initial_balance REAL NOT NULL DEFAULT 0.0,
                current_balance REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE (user_id, name)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                account_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                amount REAL NOT NULL,
                description TEXT,
                category TEXT,  
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (account_id) REFERENCES accounts (id)
            )
        ''')
        
        cursor.execute("PRAGMA table_info(users)")
        user_cols = [info[1] for info in cursor.fetchall()]
        if 'password' not in user_cols:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN password TEXT DEFAULT '12345'")
            except sqlite3.OperationalError:
                pass
        if 'email' not in user_cols:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
            except sqlite3.OperationalError:
                pass
        if 'reset_token' not in user_cols:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
            except sqlite3.OperationalError:
                pass
        if 'token_expiry' not in user_cols:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN token_expiry TEXT")
            except sqlite3.OperationalError:
                pass

        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        except sqlite3.OperationalError:
            pass

        cursor.execute("PRAGMA table_info(transactions)")
        trans_cols = [info[1] for info in cursor.fetchall()]
        if 'category' not in trans_cols:
            try:
                cursor.execute("ALTER TABLE transactions ADD COLUMN category TEXT")
            except sqlite3.OperationalError:
                pass
            
        db.commit()

if not os.path.exists(DATABASE):
    init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Authentication required. Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        db = get_db()
        login_input = request.form['username']
        password = request.form['password']
        
        user = db.execute('SELECT id, password FROM users WHERE username = ? OR email = ?', (login_input, login_input)).fetchone()

        if user and user['password'] == password: 
            session.clear()
            session['user_id'] = user['id']
            
            user_data = db.execute('SELECT fullname FROM users WHERE id = ?', (user['id'],)).fetchone()
            session['fullname'] = user_data['fullname'] if user_data and user_data['fullname'] else login_input
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid username/email or password."
    
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        db = get_db()
        fullname = request.form['fullname']
        username = request.form['username']
        email = request.form.get('email')
        password = request.form['password']
        
        if not fullname or not username or not password or not email:
            error = "All fields are required."
        elif db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            error = "Username is already taken."
        elif db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
            error = "Email address is already registered."
        else:
            db.execute('INSERT INTO users (fullname, username, email, password) VALUES (?, ?, ?, ?)',
                       (fullname, username, email, password))
            db.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login', registered=True))
            
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email_input = request.form['username']
        db = get_db()
        user = db.execute('SELECT id, fullname FROM users WHERE email = ?', (email_input,)).fetchone()
        
        if user:
            token = secrets.token_urlsafe(32)
            expiry = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            
            db.execute('UPDATE users SET reset_token = ?, token_expiry = ? WHERE id = ?', (token, expiry, user['id']))
            db.commit()
            
            reset_url = url_for('reset_password', token=token, _external=True)
            
            msg = MIMEMultipart()
            msg['From'] = SMTP_EMAIL
            msg['To'] = email_input
            msg['Subject'] = "Treasury Flow - Password Reset Request"
            
            body = f"""Hi {user['fullname'] or email_input},

We received a request to reset your password for your Treasury Flow account.
Click the link below to set a new password:

{reset_url}

For your security, this reset link is only valid for the next 2 minutes. If you did not initiate this request, no further action is required and your account remains secure.

Best regards,
Kevin Fernando
Founder, Fernando Capital
Treasury Flow"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            try:
                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                server.starttls()
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, email_input, msg.as_string())
                server.quit()
                flash('Password reset link has been successfully sent to your email.', 'success')
            except Exception:
                flash('Failed to send email. Please check your system SMTP configuration.', 'danger')
        else:
            flash('Email address not found in our system.', 'danger')
            
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    db = get_db()
    user = db.execute('SELECT id, token_expiry FROM users WHERE reset_token = ?', (token,)).fetchone()
    
    if not user:
        flash('Invalid or expired reset token.', 'danger')
        return redirect(url_for('login'))
        
    expiry_time = datetime.strptime(user['token_expiry'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expiry_time:
        flash('Reset token has expired.', 'danger')
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        new_password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
            
        db.execute('UPDATE users SET password = ?, reset_token = NULL, token_expiry = NULL WHERE id = ?', (new_password, user['id']))
        db.commit()
        flash('Your password has been successfully reset. Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('reset_password.html', token=token)

@app.route('/')
@login_required
def dashboard():
    db = get_db()
    user_id = session['user_id']
    
    filter_account_id = request.args.get('account_id', type=str)
    filter_type = request.args.get('type', type=str)
    
    accounts = db.execute('SELECT * FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    
    total_saldo = db.execute('SELECT SUM(current_balance) FROM accounts WHERE user_id = ?', (user_id,)).fetchone()[0] or 0

    today = datetime.now().date()
    today_str = today.strftime('%Y-%m-%d')
    
    days_range = request.args.get('days', type=int, default=7) 
    if days_range <= 0: days_range = 7
    days_ago_str = (today - timedelta(days=days_range)).strftime('%Y-%m-%d')
    
    total_expense = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND category != 'Transfer'", 
        (user_id,)
    ).fetchone()[0]

    expense_1d = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND date = ? AND category != 'Transfer'", 
        (user_id, today_str)
    ).fetchone()[0]

    expense_custom_range = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND date BETWEEN ? AND ? AND category != 'Transfer'", 
        (user_id, days_ago_str, today_str)
    ).fetchone()[0]
    
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

    return render_template('dashboard.html', 
                           total_saldo=total_saldo, 
                           total_expense=total_expense, 
                           expense_1d=expense_1d, 
                           expense_custom_range=expense_custom_range,
                           days_range=days_range,
                           accounts=accounts, 
                           latest_transactions=filtered_transactions, 
                           filter_account_id=filter_account_id,
                           filter_type=filter_type,
                           upcoming_alerts=upcoming_alerts,
                           goals=goals)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    db = get_db()
    user_id = session['user_id']
    error = None
    message = None
    
    user = db.execute('SELECT fullname, username, email, password FROM users WHERE id = ?', (user_id,)).fetchone()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_fullname':
            new_fullname = request.form['fullname']
            db.execute('UPDATE users SET fullname = ? WHERE id = ?', (new_fullname, user_id))
            db.commit()
            session['fullname'] = new_fullname 
            message = "Full name has been successfully updated."
        
        elif action == 'update_username':
            new_username = request.form['username']
            if db.execute('SELECT id FROM users WHERE username = ? AND id != ?', (new_username, user_id)).fetchone():
                error = "Username is already used by another account."
            else:
                db.execute('UPDATE users SET username = ? WHERE id = ?', (new_username, user_id))
                db.commit()
                message = "Username has been successfully updated."

        elif action == 'update_password':
            old_password = request.form['old_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']

            if old_password != user['password']:
                error = "Incorrect current password."
            elif new_password != confirm_password:
                error = "New password and confirmation do not match."
            else:
                db.execute('UPDATE users SET password = ? WHERE id = ?', (new_password, user_id))
                db.commit()
                session.clear()
                return redirect(url_for('login', message="Password updated successfully. Please log in again."))

        elif action == 'delete_account':
            password_check = request.form.get('password_check')
            if password_check != user['password']:
                error = "Password salah! Gagal menghapus akun."
            else:
                db.execute("DELETE FROM debt_payments WHERE debt_id IN (SELECT id FROM debts_receivables WHERE user_id = ?)", (user_id,))
                db.execute("DELETE FROM debts_receivables WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM recurring_installments WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM assets WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM users WHERE id = ?", (user_id,))
                db.commit()
                
                session.clear()
                flash("Akun Anda beserta seluruh data terkait telah berhasil dihapus secara permanen.", "success")
                return redirect(url_for('login'))

        user = db.execute('SELECT fullname, username, email, password FROM users WHERE id = ?', (user_id,)).fetchone()

    return render_template('settings.html', user=user, error=error, message=message)

@app.route('/setup/accounts', methods=['GET', 'POST'])
@login_required
def setup_account():
    db = get_db()
    error = None
    message = None
    user_id = session['user_id'] 
    
    edit_id = request.args.get('edit_id', type=int)
    delete_id = request.args.get('delete_id', type=int)
    account_to_edit = None

    ACCOUNT_TYPES = {
        'CASH': ['Cash'],
        'E-WALLET': ['DANA', 'GoPay', 'LinkAja', 'OVO', 'ShopeePay'],
        'BANK': ['BCA', 'BNI', 'BRI', 'BSI', 'CIMB Niaga', 'Mandiri', 'Bank Jago', 'Permata Bank', 'SeaBank', 
                'Superbank', 'Bank DKI', 'Bank Mega', 'BJB', 'Jenius', 'OCBC NISP', 'BTN', 'HSBC']
    }
    
    ACCOUNT_TYPES['E-WALLET'].sort()
    ACCOUNT_TYPES['BANK'].sort()

    if delete_id:
        has_transactions = db.execute('SELECT COUNT(id) FROM transactions WHERE account_id = ? AND user_id = ?', (delete_id, user_id)).fetchone()[0]
        account_name = db.execute('SELECT name FROM accounts WHERE id = ?', (delete_id,)).fetchone()
        account_name = account_name['name'] if account_name else "Account"

        if has_transactions > 0:
            error = f"Failed to delete {account_name}. This account still has {has_transactions} related transactions. Please delete transactions first."
        else:
            db.execute('DELETE FROM accounts WHERE id = ? AND user_id = ?', (delete_id, user_id))
            db.commit()
            message = f"{account_name} has been successfully deleted."
        return redirect(url_for('setup_account', message=message, error=error))

    if edit_id:
        account_to_edit = db.execute('SELECT id, name, initial_balance FROM accounts WHERE id = ? AND user_id = ?', (edit_id, user_id)).fetchone()

    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            raw_balance = request.form['initial_balance'].replace('.', '').replace(',', '.')
            balance = float(raw_balance)
            
            if action == 'edit':
                edit_account_id = request.form['edit_account_id']
                db.execute('UPDATE accounts SET initial_balance = ?, current_balance = ? WHERE id = ? AND user_id = ?', (balance, balance, edit_account_id, user_id))
                db.commit()
                message = "Initial account balance has been successfully updated."
                return redirect(url_for('setup_account', message=message))

            elif action == 'add':
                category_key = request.form['category_key'] 
                if category_key == 'CASH':
                    name_detail = 'Cash' 
                    final_name = "Cash"
                else:
                    name_detail = request.form['name_detail'] 
                    final_name = f"[{category_key}] {name_detail}"
                
                if category_key not in ACCOUNT_TYPES or name_detail not in ACCOUNT_TYPES[category_key]:
                     raise ValueError("Invalid category or name selection.")
                
                existing_account = db.execute('SELECT id FROM accounts WHERE user_id = ? AND name = ?', (user_id, final_name)).fetchone()
                if existing_account:
                     error = f"Account '{final_name}' is already registered."
                else:
                    db.execute('INSERT INTO accounts (user_id, name, initial_balance, current_balance) VALUES (?, ?, ?, ?)', (user_id, final_name, balance, balance))
                    message = f"Account '{final_name}' has been successfully added."
                    db.commit()
        
        except ValueError as e:
            error = str(e) or "Balance input must be a valid number."
        except sqlite3.IntegrityError:
             error = "Data integrity error occurred."
        except Exception as e:
             error = f"An error occurred: {e}"

    accounts = db.execute('SELECT id, name, initial_balance, current_balance FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    return render_template('setup_account.html', accounts=accounts, message=message, error=error, categories=ACCOUNT_TYPES, account_to_edit=account_to_edit)

@app.route('/add/transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    user_id = session['user_id']
    db = get_db()
    accounts = db.execute('SELECT id, name FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    
    if not accounts:
        flash('You must create at least one Account before recording any transaction.', 'warning')
        return redirect(url_for('setup_account'))

    error = None
    if request.method == 'POST':
        try:
            t_type = request.form.get('type')
            date_str = request.form['date']
            raw_amount = request.form['amount'].replace('.', '').replace(',', '.')
            amount = float(raw_amount)
            description = request.form['description']

            if t_type == 'transfer':
                from_id = request.form['account_id']
                to_id = request.form['to_account_id']
                
                if not to_id: raise ValueError("Please select a destination account for transfer.")
                if from_id == to_id: raise ValueError("Source and destination accounts cannot be the same.")

                acc_from_row = db.execute('SELECT name FROM accounts WHERE id = ?', (from_id,)).fetchone()
                acc_to_row = db.execute('SELECT name FROM accounts WHERE id = ?', (to_id,)).fetchone()
                
                clean_from = acc_from_row['name'].split('] ')[1] if '] ' in acc_from_row['name'] else acc_from_row['name']
                clean_to = acc_to_row['name'].split('] ')[1] if '] ' in acc_to_row['name'] else acc_to_row['name']

                db.execute('INSERT INTO transactions (user_id, date, account_id, type, amount, description, category) VALUES (?, ?, ?, ?, ?, ?, ?)',
                           (user_id, date_str, from_id, 'expense', amount, f"Transfer to {clean_to}: {description}", "Transfer"))
                db.execute('INSERT INTO transactions (user_id, date, account_id, type, amount, description, category) VALUES (?, ?, ?, ?, ?, ?, ?)',
                           (user_id, date_str, to_id, 'income', amount, f"Received from {clean_from}: {description}", "Transfer"))

                db.execute('UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?', (amount, from_id))
                db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (amount, to_id))
            else:
                account_id = request.form['account_id']
                category = request.form['category']
                if not category: raise ValueError("Category selection is required.")

                db.execute('INSERT INTO transactions (user_id, date, account_id, type, amount, description, category) VALUES (?, ?, ?, ?, ?, ?, ?)',
                           (user_id, date_str, account_id, t_type, amount, description, category))

                adjustment = amount if t_type == 'income' else -amount
                db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (adjustment, account_id))
            
            db.commit()
            flash("Transaction saved successfully!", 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            error = str(e)

    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('add_transaction.html', accounts=accounts, categories=CATEGORIES, today=today, error=error)

@app.route('/transactions_list')
@login_required
def transactions_list():
    user_id = session.get('user_id')
    db = get_db()
    transactions = db.execute('''
        SELECT t.id, t.date, t.type, t.amount, t.description, t.category, a.name AS account_name
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ?
        ORDER BY t.date DESC, t.id DESC
    ''', (user_id,)).fetchall()
    return render_template('transactions_list.html', transactions=transactions)

@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    user_id = session.get('user_id')
    db = get_db()
    transaction = db.execute('SELECT account_id, type, amount FROM transactions WHERE id = ? AND user_id = ?', (transaction_id, user_id)).fetchone()

    if transaction:
        try:
            adjustment = -transaction['amount'] if transaction['type'] == 'income' else transaction['amount']
            db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (adjustment, transaction['account_id']))
            db.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
            db.commit()
            flash('Transaction successfully deleted.', 'success')
        except Exception as e:
            flash(f'Failed to delete transaction: {e}', 'danger')
    else:
        flash('Transaction not found.', 'danger')
    return redirect(url_for('transactions_list'))

@app.route('/export_csv')
@login_required
def export_csv():
    user_id = session.get('user_id')
    db = get_db()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = '''
        SELECT t.date, a.name as account_name, t.type, t.category, t.amount, t.description
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ?
    '''
    params = [user_id]
    if start_date and end_date:
        query += " AND t.date BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    query += " ORDER BY t.date DESC"
    transactions = db.execute(query, params).fetchall()

    total_income = sum(t['amount'] for t in transactions if t['type'] == 'income')
    total_expense = sum(t['amount'] for t in transactions if t['type'] == 'expense')
    net_flow = total_income - total_expense

    si = StringIO()
    cw = csv.writer(si)
    
    cw.writerow(["TREASURY FLOW FINANCIAL REPORT"])
    cw.writerow([f"Period: {start_date or 'All'} to {end_date or 'All'}"])
    cw.writerow([])
    
    cw.writerow(["FINANCIAL SUMMARY"])
    cw.writerow(["Total Cash In (Income)", f"Rp {total_income:,.2f}"])
    cw.writerow(["Total Cash Out (Expense)", f"Rp {total_expense:,.2f}"])
    cw.writerow(["Net Flow / Savings", f"Rp {net_flow:,.2f}"])
    cw.writerow([])
    
    cw.writerow(["TRANSACTION LEDNING HISTORY"])
    cw.writerow(['Date', 'Description', 'Type', 'Category', 'Account', 'Amount'])
    
    for t in transactions:
        clean_name = t['account_name'].split('] ')[1] if '] ' in t['account_name'] else t['account_name']
        sign = "+" if t['type'] == 'income' else "-"
        cw.writerow([
            t['date'], 
            t['description'] or 'No Description', 
            t['type'].upper(), 
            t['category'], 
            clean_name, 
            f"{sign} Rp {t['amount']:,.2f}"
        ])

    output = si.getvalue()
    si.close()
    return Response(output, mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=financial_report_{start_date or 'all'}_to_{end_date or 'all'}.csv"})

@app.route('/export_pdf')
@login_required
def export_pdf():
    user_id = session.get('user_id')
    db = get_db()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = '''
        SELECT t.date, a.name as account_name, t.type, t.category, t.amount, t.description
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ?
    '''
    params = [user_id]
    if start_date and end_date:
        query += " AND t.date BETWEEN ? AND ?"
        params.extend([start_date, end_date])
        
    query += " ORDER BY t.date DESC"
    transactions = db.execute(query, params).fetchall()

    total_income = sum(t['amount'] for t in transactions if t['type'] == 'income')
    total_expense = sum(t['amount'] for t in transactions if t['type'] == 'expense')
    net_flow = total_income - total_expense
    fullname = session.get('fullname', 'User')

    class PDF(FPDF):
        def header(self):
            logo_path = os.path.join(app.root_path, 'static', 'img', 'logo.png')
            if os.path.exists(logo_path):
                self.image(logo_path, 8, 0, 35)

            self.set_y(12)
            self.set_font('Arial', 'B', 18)
            self.set_text_color(17, 35, 126)
            self.cell(0, 8, 'TREASURY FLOW', 0, 1, 'R')
            
            self.set_font('Arial', 'B', 10)
            self.set_text_color(108, 117, 125)
            self.cell(0, 6, 'FINANCIAL STATEMENTS REPORT', 0, 1, 'R')
            
            self.set_y(35)
            self.set_draw_color(17, 35, 126)
            self.set_line_width(0.5)
            self.line(10, 35, 200, 35)
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.set_text_color(108, 117, 125)
            self.cell(0, 10, 'Powered by Fernando Capital', 0, 0, 'L')
            self.cell(0, 10, f'Page {self.page_no()} / {{nb}}', 0, 0, 'R')

    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    pdf.set_y(42)
    label_width = 28
    
    pdf.set_font('Arial', 'B', 10)
    pdf.set_text_color(17, 35, 126)
    pdf.cell(label_width, 6, 'Prepared For', 0, 0, 'L')
    pdf.set_font('Arial', 'B', 10)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 6, f": {fullname}", 0, 1, 'L')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.set_text_color(17, 35, 126)
    pdf.cell(label_width, 6, 'Report Date', 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 6, f": {datetime.now().strftime('%B %d, %Y')}", 0, 1, 'L')

    pdf.set_font('Arial', 'B', 10)
    pdf.set_text_color(17, 35, 126)
    pdf.cell(label_width, 6, 'Period', 0, 0, 'L')
    pdf.set_font('Arial', '', 10)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 6, f": {start_date or 'All'} to {end_date or 'All'}", 0, 1, 'L')
    
    pdf.ln(10)

    pdf.set_font('Arial', 'B', 13)
    pdf.set_text_color(17, 35, 126)
    pdf.cell(0, 8, 'Financial Summary', 0, 1, 'L')
    
    col_w = 63.3 
    
    pdf.set_font('Arial', 'B', 9)
    pdf.set_text_color(108, 117, 125)
    pdf.cell(col_w, 5, 'TOTAL CASH IN (INCOME)', 0, 0, 'L')
    pdf.cell(col_w, 5, 'TOTAL CASH OUT (EXPENSE)', 0, 0, 'C')
    pdf.cell(col_w, 5, 'NET FLOW / SAVINGS', 0, 1, 'R')
    
    pdf.set_font('Arial', 'B', 13)
    pdf.set_text_color(16, 185, 129)
    pdf.cell(col_w, 8, f"+ Rp {total_income:,.2f}", 0, 0, 'L')
    
    pdf.set_text_color(239, 68, 68)
    pdf.cell(col_w, 8, f"- Rp {total_expense:,.2f}", 0, 0, 'C')
    
    if net_flow < 0:
        pdf.set_text_color(239, 68, 68)
        pdf.cell(col_w, 8, f"- Rp {abs(net_flow):,.2f}", 0, 1, 'R')
    else:
        pdf.set_text_color(17, 35, 126)
        pdf.cell(col_w, 8, f"Rp {net_flow:,.2f}", 0, 1, 'R')
        
    pdf.ln(10)

    pdf.set_font('Arial', 'B', 13)
    pdf.set_text_color(17, 35, 126)
    pdf.cell(0, 8, 'Transaction Ledger History', 0, 1, 'L')

    pdf.set_fill_color(17, 35, 126)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Arial', 'B', 9)
    pdf.set_draw_color(200, 200, 200)
    pdf.cell(22, 8, 'DATE', 1, 0, 'C', True)
    pdf.cell(60, 8, 'DESCRIPTION', 1, 0, 'C', True)
    pdf.cell(38, 8, 'CATEGORY', 1, 0, 'C', True)
    pdf.cell(35, 8, 'ACCOUNT', 1, 0, 'C', True)
    pdf.cell(35, 8, 'AMOUNT', 1, 1, 'C', True)

    pdf.set_text_color(17, 24, 39)
    pdf.set_font('Arial', '', 9)
    fill = False
    
    for t in transactions:
        if fill:
            pdf.set_fill_color(249, 250, 251)
        else:
            pdf.set_fill_color(255, 255, 255)
            
        current_y = pdf.get_y()
        if current_y > 260:
            pdf.add_page()
            pdf.set_fill_color(17, 35, 126)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font('Arial', 'B', 9)
            pdf.cell(22, 8, 'DATE', 1, 0, 'C', True)
            pdf.cell(60, 8, 'DESCRIPTION', 1, 0, 'C', True)
            pdf.cell(38, 8, 'CATEGORY', 1, 0, 'C', True)
            pdf.cell(35, 8, 'ACCOUNT', 1, 0, 'C', True)
            pdf.cell(35, 8, 'AMOUNT', 1, 1, 'C', True)
            
            pdf.set_text_color(17, 24, 39)
            pdf.set_font('Arial', '', 9)
            if fill:
                pdf.set_fill_color(249, 250, 251)
            else:
                pdf.set_fill_color(255, 255, 255)

        pdf.cell(22, 7, str(t['date']), 1, 0, 'C', fill=True)
        
        desc = t['description'] or '-'
        if len(desc) > 30: desc = desc[:27] + "..."
        pdf.cell(60, 7, str(desc), 1, 0, 'L', fill=True)
        
        pdf.cell(38, 7, str(t['category']), 1, 0, 'L', fill=True)
        
        clean_account = t['account_name'].split('] ')[1] if '] ' in t['account_name'] else t['account_name']
        if len(clean_account) > 18: clean_account = clean_account[:15] + "..."
        pdf.cell(35, 7, str(clean_account), 1, 0, 'L', fill=True)
        
        if t['type'] == 'income':
            pdf.set_text_color(16, 185, 129)
            amt_text = f"+Rp {t['amount']:,.2f}"
        else:
            pdf.set_text_color(239, 68, 68)
            amt_text = f"-Rp {t['amount']:,.2f}"
            
        pdf.cell(35, 7, amt_text, 1, 1, 'R', fill=True)
        pdf.set_text_color(17, 24, 39)
        fill = not fill

    response = Response(pdf.output(dest='S').encode('latin-1', 'ignore'))
    response.headers.set('Content-Disposition', 'attachment', filename=f"financial_statements_report_{start_date or 'all'}_to_{end_date or 'all'}.pdf")
    response.headers.set('Content-Type', 'application/pdf')
    return response

@app.route('/api/data-kalender')
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

@app.route('/financial_performance', methods=['GET', 'POST'])
@login_required
def financial_performance():
    db = get_db()
    user_id = session['user_id']
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS debts_receivables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            person_name TEXT NOT NULL,
            type TEXT NOT NULL,
            total_amount REAL NOT NULL,
            remaining_amount REAL NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT DEFAULT 'BELUM LUNAS',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS debt_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debt_id INTEGER NOT NULL,
            account_name TEXT NOT NULL,
            amount_paid REAL NOT NULL,
            payment_date TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS recurring_installments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            amount_per_cycle REAL NOT NULL,
            due_day_of_month INTEGER NOT NULL,
            is_temporary_tenor INTEGER DEFAULT 0,
            total_tenor INTEGER,
            current_tenor INTEGER,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            asset_name TEXT NOT NULL,
            category TEXT NOT NULL,
            purchase_date TEXT NOT NULL,
            purchase_price REAL NOT NULL,
            quantity TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS financial_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            current_amount REAL DEFAULT 0,
            due_date TEXT NOT NULL,
            status TEXT DEFAULT 'In Progress',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    db.commit()

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
            
        return redirect(url_for('financial_performance'))

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

    goals_list = db.execute('''
        SELECT id, name, target_amount, current_amount, due_date, status,
               (current_amount / target_amount * 100) as percentage
        FROM financial_goals WHERE user_id = ? ORDER BY status DESC, due_date ASC
    ''', (user_id,)).fetchall()

    return render_template('financial_performance.html', 
                           expense_custom_range=expense_custom_range, income_custom_range=income_custom_range,
                           avg_expense_daily=avg_expense_daily, avg_income_daily=avg_income_daily,
                           proyeksi_seminggu_out=proyeksi_seminggu_out, proyeksi_sebulan_out=proyeksi_sebulan_out,
                           max_expense=max_expense, min_expense=min_expense, days_range=days_range,
                           distribution_list=distribution_list, records_active=records_active, records_history=records_history, 
                           accounts=clean_accounts, installments=installments,
                           assets_list=assets_list, total_asset_value=total_asset_value, goals_list=goals_list)

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, port=5000)