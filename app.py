# ==============================================================================
# File: app.py (Revisi Total - FIX VITAL: Database Migration & Fungsionalitas)
# ==============================================================================

import os
import sqlite3
import locale
from datetime import datetime, timedelta 
from functools import wraps
from flask import Flask, render_template, request, url_for, redirect, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash

# --- KONFIGURASI APLIKASI ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'kunci_rahasia_default_yang_harus_diganti')

# Lokasi Database
DATABASE = 'treasury_flow.db'

# Daftar Kategori untuk Transaksi
CATEGORIES = {
    'income': ['Gaji', 'Investasi', 'Hadiah', 'Penjualan Aset', 'Lainnya (Pemasukan)'],
    'expense': ['Makanan & Minuman', 'Transportasi', 'Belanja', 'Tagihan', 
                'Hiburan', 'Kesehatan', 'Pendidikan', 'Cicilan & Utang', 'Lainnya (Pengeluaran)']
}

# --- FUNGSI FORMATTING ---

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


# --- FUNGSI DATABASE & MIGRATION FIX ---

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
        
        # 1. Pastikan tabel dasar ada
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fullname TEXT, 
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
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
        
        # 2. MIGRATION CHECK (FIX ERROR: no such column: t.category)
        try:
            # Jika kolom 'category' belum ada, SQLite akan error saat mencoba SELECT.
            # Kita gunakan PRAGMA table_info untuk memeriksa.
            cursor.execute("PRAGMA table_info(transactions)")
            columns = [info['name'] for info in cursor.fetchall()]
            
            if 'category' not in columns:
                print(">>> Menjalankan ALTER TABLE: Menambahkan kolom 'category' ke tabel transactions")
                cursor.execute("ALTER TABLE transactions ADD COLUMN category TEXT")
        except Exception as e:
            # Ini mungkin terjadi jika tabel transactions belum ada, tapi CREATE TABLE di atas sudah mengatasinya.
            print(f"Error saat migrasi database: {e}")
            pass
            
        db.commit()

if not os.path.exists(DATABASE):
    init_db()


# --- DECORATOR OTENTIKASI ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Anda harus login untuk mengakses halaman ini.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES OTENTIKASI ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        db = get_db()
        username = request.form['username']
        password = request.form['password']
        
        user = db.execute('SELECT id, password FROM users WHERE username = ?', (username,)).fetchone()

        if user and user['password'] == password: 
            session.clear()
            session['user_id'] = user['id']
            
            user_data = db.execute('SELECT fullname FROM users WHERE id = ?', (user['id'],)).fetchone()
            session['fullname'] = user_data['fullname'] if user_data and user_data['fullname'] else user['username']
            return redirect(url_for('dashboard'))
        else:
            error = "Username atau password salah."
    
    return render_template('login.html', error=error)

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
            flash('Registrasi berhasil! Silakan login.', 'success')
            return redirect(url_for('login', registered=True))
            
    return render_template('register.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ROUTES DASHBOARD & ACCOUNT MANAGEMENT ---

@app.route('/')
@login_required
def dashboard():
    db = get_db()
    user_id = session['user_id']
    
    filter_account_id = request.args.get('account_id', type=str)
    filter_type = request.args.get('type', type=str)
    
    accounts = db.execute('SELECT * FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    
    account_balances = {acc['id']: acc['initial_balance'] for acc in accounts}
    
    transactions_for_balance = db.execute('SELECT SUM(current_balance) FROM accounts WHERE user_id = ?', (user_id,)).fetchone()[0] or 0

    total_saldo = db.execute('SELECT SUM(current_balance) FROM accounts WHERE user_id = ?', (user_id,)).fetchone()[0] or 0

    # --- Perhitungan Pengeluaran Statistik ---
    today = datetime.now().date()
    today_str = today.strftime('%Y-%m-%d')
    
    days_range = request.args.get('days', type=int, default=7) 
    
    if days_range <= 0: days_range = 7
    days_ago_str = (today - timedelta(days=days_range)).strftime('%Y-%m-%d')
    
    # --- Statistik ---
    
    total_expense = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense'", 
        (user_id,)
    ).fetchone()[0]

    expense_1d = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND date = ?", 
        (user_id, today_str)
    ).fetchone()[0]

    expense_custom_range = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND type = 'expense' AND date BETWEEN ? AND ?", 
        (user_id, days_ago_str, today_str)
    ).fetchone()[0]
    
    # --- Akhir Perhitungan Statistik ---

    # Ambil Transaksi Terbaru dengan Filter
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

    return render_template('dashboard.html', 
                           total_saldo=total_saldo, 
                           total_expense=total_expense, 
                           expense_1d=expense_1d, 
                           expense_custom_range=expense_custom_range,
                           days_range=days_range,
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
    ACCOUNT_TYPES = {
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
    
    ACCOUNT_TYPES['E-WALLET'].sort()
    ACCOUNT_TYPES['BANK'].sort()

    # --- Logika Hapus Akun ---
    if delete_id:
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
                
                if category_key == 'CASH':
                    name_detail = 'Cash' 
                    final_name = "Cash"
                else:
                    name_detail = request.form['name_detail'] 
                    final_name = f"[{category_key}] {name_detail}"
                
                if category_key not in ACCOUNT_TYPES or name_detail not in ACCOUNT_TYPES[category_key]:
                     raise ValueError("Pilihan kategori atau nama tidak valid.")

                
                existing_account = db.execute('SELECT id FROM accounts WHERE user_id = ? AND name = ?', 
                                              (user_id, final_name)).fetchone()
                if existing_account:
                     error = f"Akun '{final_name}' sudah terdaftar."
                else:
                    db.execute('INSERT INTO accounts (user_id, name, initial_balance, current_balance) VALUES (?, ?, ?, ?)', (user_id, final_name, balance, balance))
                    message = f"Akun '{final_name}' berhasil ditambahkan."
                    db.commit()
        
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
                           categories=ACCOUNT_TYPES,
                           account_to_edit=account_to_edit)


# --- ROUTES TRANSAKSI (FIX BUG PENCATATAN & DROPDOWN) ---

@app.route('/add/transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    user_id = session['user_id']
    db = get_db()
    
    accounts = db.execute('SELECT id, name FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    
    if not accounts:
        flash('Anda harus membuat minimal satu Akun (Cash, Bank, E-Wallet) sebelum mencatat transaksi.', 'warning')
        return redirect(url_for('setup_account'))

    error = None
    if request.method == 'POST':
        try:
            date_str = request.form['date']
            account_id = request.form['account_id']
            type = request.form['type']
            category = request.form['category'] 
            
            raw_amount = request.form['amount'].replace('.', '').replace(',', '.')
            amount = float(raw_amount)
            
            description = request.form['description']
            
            if not date_str or not account_id or not type or amount <= 0 or not category:
                raise ValueError("Semua field wajib diisi dengan benar.")

            selected_account = db.execute('SELECT name FROM accounts WHERE id = ? AND user_id = ?', 
                                          (account_id, user_id)).fetchone()
            if not selected_account:
                raise ValueError("Akun tidak ditemukan.")
            
            # Simpan Transaksi
            db.execute('''
                INSERT INTO transactions (user_id, date, account_id, type, amount, description, category) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, date_str, account_id, type, amount, description, category))

            adjustment = amount if type == 'income' else -amount
            db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', 
                       (adjustment, account_id))
            
            db.commit()
            
            flash(f"Transaksi {type.capitalize()} sebesar {format_rupiah(amount)} berhasil dicatat di akun {selected_account['name']}.", 'success')
            return redirect(url_for('dashboard'))

        except ValueError as e:
            error = str(e)
        except Exception as e:
            error = f"Terjadi kesalahan saat mencatat transaksi: {e}"

    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('add_transaction.html', 
                           accounts=accounts,
                           categories=CATEGORIES, 
                           today=today, 
                           error=error)


# --- FITUR: MANAJEMEN TRANSAKSI (LIST & HAPUS) ---

@app.route('/transactions_list')
@login_required
def transactions_list():
    """Menampilkan semua transaksi pengguna (FIXED BUG VITAL)."""
    user_id = session.get('user_id')
    db = get_db()
    
    transactions = db.execute('''
        SELECT 
            t.id, t.date, t.type, t.amount, t.description, t.category, 
            a.name AS account_name
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ?
        ORDER BY t.date DESC, t.id DESC
    ''', (user_id,)).fetchall()
    
    return render_template('transactions_list.html', transactions=transactions)

@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    """Menghapus transaksi."""
    user_id = session.get('user_id')
    db = get_db()
    
    transaction = db.execute('SELECT account_id, type, amount FROM transactions WHERE id = ? AND user_id = ?', 
                   (transaction_id, user_id)).fetchone()

    if transaction:
        try:
            adjustment = -transaction['amount'] if transaction['type'] == 'income' else transaction['amount']
            db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', 
                       (adjustment, transaction['account_id']))

            db.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))

            db.commit()
            
            flash('Transaksi berhasil dihapus.', 'success')
        except Exception as e:
            flash(f'Gagal menghapus transaksi: {e}', 'danger')
    else:
        flash('Transaksi tidak ditemukan atau Anda tidak memiliki akses.', 'danger')
        
    return redirect(url_for('transactions_list'))


if __name__ == '__main__':
    # Memastikan migrasi database berjalan saat aplikasi dimulai jika file DB sudah ada
    if os.path.exists(DATABASE):
        with app.app_context():
            init_db() 
    else:
        init_db()
    app.run(debug=True)