# ==============================================================================
# File: app.py (Revisi Total Code, FINAL BUILD + HAPUS AKUN)
# ==============================================================================

import os
import sqlite3
from datetime import datetime, timedelta 
from functools import wraps
from flask import Flask, render_template, request, url_for, redirect, session, g
import socket 
import locale 

# Inisialisasi Aplikasi Flask
app = Flask(__name__)
app.secret_key = 'kunci_rahasia_dan_aman_sekali' 
DATABASE = 'treasury_flow.db'

# --- Konfigurasi Locale untuk Rupiah ---
try:
    locale.setlocale(locale.LC_ALL, 'id_ID.utf8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'indonesian')
    except locale.Error:
        pass 

# --- Custom Jinja Filter: format_rupiah (FIXED None Bug) ---
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

# --- Custom Jinja Filter: format_rupiah_input ---
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


# --- Konfigurasi Database ---

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def close_db_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

app.teardown_appcontext(close_db_connection)

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fullname TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            );
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                initial_balance REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE (user_id, name)
            );
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                account_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                amount REAL NOT NULL,
                description TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (account_id) REFERENCES accounts (id)
            );
        ''')
        db.commit()

if not os.path.exists(DATABASE):
    with app.app_context():
        init_db()

# --- Fungsi Utility ---

def check_login():
    return 'user_id' in session

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not check_login():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Rute Autentikasi ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        db = get_db()
        fullname = request.form['fullname']
        username = request.form['username']
        password = request.form['password']

        if not fullname or not username or not password:
            error = "Semua field harus diisi."
        elif db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            error = "Username sudah digunakan."
        else:
            db.execute('INSERT INTO users (fullname, username, password) VALUES (?, ?, ?)',
                       (fullname, username, password))
            db.commit()
            return redirect(url_for('login', registered=True))
    
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    registered = request.args.get('registered')
    message = "Registrasi berhasil! Silakan login." if registered else None

    if request.method == 'POST':
        db = get_db()
        username = request.form['username']
        password = request.form['password']
        
        user = db.execute('SELECT id, fullname, username, password FROM users WHERE username = ? AND password = ?',
                          (username, password)).fetchone()

        if user is None:
            error = "Username atau password salah."
        else:
            session.clear()
            session['user_id'] = user['id']
            session['fullname'] = user['fullname']
            return redirect(url_for('dashboard'))
    
    return render_template('login.html', error=error, message=message)

# Rute Logout Baru dengan Konfirmasi
@app.route('/logout')
def logout():
    # Clear session jika langsung diakses (tanpa konfirmasi)
    session.clear()
    return redirect(url_for('login'))

# --- Rute Dashboard dan Logika Statistik ---

@app.route('/')
@login_required
def dashboard():
    db = get_db()
    user_id = session['user_id']
    
    filter_account_id = request.args.get('account_id', type=str)
    filter_type = request.args.get('type', type=str)
    
    accounts = db.execute('SELECT id, name, initial_balance FROM accounts WHERE user_id = ?', 
                          (user_id,)).fetchall()
    
    account_balances = {acc['id']: acc['initial_balance'] for acc in accounts}
    
    transactions_for_balance = db.execute('SELECT account_id, type, amount FROM transactions WHERE user_id = ?', 
                                          (user_id,)).fetchall()

    for t in transactions_for_balance:
        if t['type'] == 'income':
            account_balances[t['account_id']] += t['amount']
        elif t['type'] == 'expense':
            account_balances[t['account_id']] -= t['amount']
    
    total_saldo = sum(account_balances.values()) 

    # --- Perhitungan Pengeluaran Statistik (FIXED None Handling) ---
    today = datetime.now().date()
    today_str = today.strftime('%Y-%m-%d')
    seven_days_ago_str = (today - timedelta(days=7)).strftime('%Y-%m-%d')

    total_expense_result = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense'", 
        (user_id,)
    ).fetchone()[0]
    total_expense = total_expense_result

    expense_1d_result = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND date = ?", 
        (user_id, today_str)
    ).fetchone()[0]
    expense_1d = expense_1d_result

    expense_7d_result = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND date BETWEEN ? AND ?", 
        (user_id, seven_days_ago_str, today_str)
    ).fetchone()[0]
    expense_7d = expense_7d_result
    # --- Akhir Perhitungan Statistik ---

    # Ambil Transaksi Terbaru dengan Filter
    query = '''
        SELECT t.date, t.description, t.type, t.amount, a.name as account_name
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

    return render_template('dashboard.html', 
                           total_saldo=total_saldo, 
                           total_expense=total_expense, 
                           expense_1d=expense_1d, 
                           expense_7d=expense_7d, 
                           accounts=accounts, 
                           latest_transactions=filtered_transactions, 
                           filter_account_id=filter_account_id,
                           filter_type=filter_type)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    db = get_db()
    user_id = session['user_id']
    error = None
    message = None
    
    user = db.execute('SELECT fullname, username, password FROM users WHERE id = ?', (user_id,)).fetchone()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_fullname':
            new_fullname = request.form['fullname']
            db.execute('UPDATE users SET fullname = ? WHERE id = ?', (new_fullname, user_id))
            db.commit()
            session['fullname'] = new_fullname 
            message = "Nama lengkap berhasil diperbarui."
        
        elif action == 'update_username':
            new_username = request.form['username']
            if db.execute('SELECT id FROM users WHERE username = ? AND id != ?', (new_username, user_id)).fetchone():
                error = "Username sudah digunakan oleh akun lain."
            else:
                db.execute('UPDATE users SET username = ? WHERE id = ?', (new_username, user_id))
                db.commit()
                message = "Username berhasil diperbarui."

        elif action == 'update_password':
            old_password = request.form['old_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']

            if old_password != user['password']:
                error = "Password lama salah."
            elif new_password != confirm_password:
                error = "Password baru dan konfirmasi tidak cocok."
            else:
                db.execute('UPDATE users SET password = ? WHERE id = ?', (new_password, user_id))
                db.commit()
                session.clear()
                return redirect(url_for('login', message="Password berhasil diganti. Silakan login kembali."))

        user = db.execute('SELECT fullname, username, password FROM users WHERE id = ?', (user_id,)).fetchone()

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

    # --- Data untuk Dropdown Akun ---
    CATEGORIES = {
        'CASH': ['Cash'],
        'E-WALLET': [
            'DANA', 'GoPay', 'LinkAja', 'OVO', 'ShopeePay', 
            'I-Saku', 'Astrapay', 'QRIS Merchant', 'Sakuku', 'BluePay'
        ],
        'BANK': [
            'BCA', 'BNI', 'BRI', 'BSI', 'CIMB Niaga', 'Mandiri', 'Maybank', 'Permata Bank', 'SeaBank', 
            'Superbank', 'Bank DKI', 'Bank Mega', 'BJB', 'Jenius', 'OCBC NISP', 'Panin Bank', 'DBS/Digibank', 
            'Bank Neo Commerce', 'BTN', 'Commonwealth Bank', 'CitiBank', 'HSBC', 'Standard Chartered'
        ]
    }
    
    CATEGORIES['E-WALLET'].sort()
    CATEGORIES['BANK'].sort()

    # --- Logika Hapus Akun ---
    if delete_id:
        # Cek apakah akun memiliki transaksi
        has_transactions = db.execute(
            'SELECT COUNT(id) FROM transactions WHERE account_id = ? AND user_id = ?', 
            (delete_id, user_id)
        ).fetchone()[0]

        account_name = db.execute('SELECT name FROM accounts WHERE id = ?', (delete_id,)).fetchone()
        account_name = account_name['name'] if account_name else "Akun"

        if has_transactions > 0:
            error = f"Gagal menghapus {account_name}. Akun ini masih memiliki {has_transactions} transaksi terkait. Hapus transaksi terlebih dahulu."
        else:
            db.execute('DELETE FROM accounts WHERE id = ? AND user_id = ?', (delete_id, user_id))
            db.commit()
            message = f"{account_name} berhasil dihapus."
        
        # Bersihkan query string setelah aksi
        return redirect(url_for('setup_account', message=message, error=error))


    if edit_id:
        account_to_edit = db.execute(
            'SELECT id, name, initial_balance FROM accounts WHERE id = ? AND user_id = ?', 
            (edit_id, user_id)
        ).fetchone()

    # --- Proses POST Request (Tambah/Edit) ---
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            raw_balance = request.form['initial_balance'].replace('.', '').replace(',', '.')
            balance = float(raw_balance)
            
            if action == 'edit':
                edit_account_id = request.form['edit_account_id']
                
                db.execute(
                    'UPDATE accounts SET initial_balance = ? WHERE id = ? AND user_id = ?',
                    (balance, edit_account_id, user_id)
                )
                db.commit()
                message = "Saldo Awal Akun berhasil diperbarui."
                return redirect(url_for('setup_account', message=message))

            elif action == 'add':
                category_key = request.form['category_key'] 
                name_detail = request.form['name_detail'] 

                if category_key not in CATEGORIES or name_detail not in CATEGORIES[category_key]:
                     raise ValueError("Pilihan kategori atau nama tidak valid.")

                if category_key == 'CASH':
                    final_name = "Cash"
                else:
                    final_name = f"[{category_key}] {name_detail}"
                
                existing_account = db.execute('SELECT id FROM accounts WHERE user_id = ? AND name = ?', 
                                              (user_id, final_name)).fetchone()
                if existing_account:
                     error = f"Akun '{final_name}' sudah terdaftar."
                else:
                    db.execute('INSERT INTO accounts (user_id, name, initial_balance) VALUES (?, ?, ?)',
                               (user_id, final_name, balance))
                    db.commit()
                    message = f"Akun '{final_name}' berhasil ditambahkan."
        
        except ValueError as e:
            error = str(e) or "Input saldo harus berupa angka yang valid (gunakan format angka ID: titik ribuan, koma desimal)."
        except sqlite3.IntegrityError:
             error = "Terjadi kesalahan integritas data."
        except Exception as e:
             error = f"Terjadi kesalahan: {e}"

    accounts = db.execute('SELECT id, name, initial_balance FROM accounts WHERE user_id = ?', 
                          (user_id,)).fetchall()
    
    return render_template('setup_account.html', 
                           accounts=accounts, 
                           message=message, 
                           error=error,
                           categories=CATEGORIES,
                           account_to_edit=account_to_edit)

@app.route('/add/transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    db = get_db()
    user_id = session['user_id']
    error = None
    message = None
    
    accounts = db.execute('SELECT id, name FROM accounts WHERE user_id = ?', (user_id,)).fetchall()

    if request.method == 'POST':
        try:
            date_str = request.form['date']
            account_id = request.form['account_id']
            type = request.form['type']
            
            raw_amount = request.form['amount'].replace('.', '').replace(',', '.')
            amount = float(raw_amount)
            
            description = request.form['description']
            
            if not date_str or not account_id or not type or amount <= 0:
                raise ValueError("Semua field wajib diisi dengan benar.")

            selected_account = db.execute('SELECT name FROM accounts WHERE id = ? AND user_id = ?', 
                                          (account_id, user_id)).fetchone()
            if not selected_account:
                raise ValueError("Akun tidak ditemukan.")
            
            db.execute('''
                INSERT INTO transactions (user_id, date, account_id, type, amount, description) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, date_str, account_id, type, amount, description))
            db.commit()
            
            message = f"Transaksi {type.capitalize()} sebesar Rp {amount:,.0f} berhasil dicatat di akun {selected_account['name']}."
            return redirect(url_for('dashboard'))

        except ValueError as e:
            error = str(e)
        except Exception as e:
            error = f"Terjadi kesalahan saat mencatat transaksi: {e}"

    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('add_transaction.html', 
                           accounts=accounts, 
                           today=today, 
                           error=error, 
                           message=message)

# --- App Runner ---

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


if __name__ == '__main__':
    TARGET_HOST = '0.0.0.0' 
    TARGET_PORT = 5000
    
    try:
        LOCAL_IP = get_local_ip()
    except Exception:
        LOCAL_IP = '127.0.0.1'

    print("-" * 50)
    print("🚀 TREASURY FLOW BERJALAN DI SERVER AMAN")
    print("-" * 50)
    print(f"1. Akses dari Laptop (Browser): http://127.0.0.1:{TARGET_PORT}/")
    print(f"2. Akses dari HP (Di Jaringan WiFi Sama): http://{LOCAL_IP}:{TARGET_PORT}/")
    print("-" * 50)
    
    app.run(debug=True, host=TARGET_HOST, port=TARGET_PORT)