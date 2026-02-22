import os
import sqlite3
import locale
import csv 
from io import StringIO 
from datetime import datetime, timedelta 
from functools import wraps
from flask import Flask, render_template, request, url_for, redirect, session, g, flash, Response
from flask import jsonify
from fpdf import FPDF
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
        
        # 2. AUTO-FIX: Cek Kolom Password & Category (Biar gak perlu migrasi manual)
        cursor.execute("PRAGMA table_info(users)")
        user_cols = [info[1] for info in cursor.fetchall()]
        if 'password' not in user_cols:
            print(">>> Fixing: Menambahkan kolom password...")
            cursor.execute("ALTER TABLE users ADD COLUMN password TEXT DEFAULT '12345'")

        cursor.execute("PRAGMA table_info(transactions)")
        trans_cols = [info[1] for info in cursor.fetchall()]
        if 'category' not in trans_cols:
            print(">>> Fixing: Menambahkan kolom category...")
            cursor.execute("ALTER TABLE transactions ADD COLUMN category TEXT")
            
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
            'Superbank', 'Bank DKI', 'Bank Mega', 'BJB', 'Jenius', 'OCBC NISP', 'Panin Bank', 
            'Bank Neo Commerce', 'BTN', 'HSBC'
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
    
    # Mengambil daftar akun milik user
    accounts = db.execute('SELECT id, name FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    
    if not accounts:
        flash('Anda harus membuat minimal satu Akun sebelum mencatat transaksi.', 'warning')
        return redirect(url_for('setup_account'))

    error = None
    if request.method == 'POST':
        try:
            t_type = request.form.get('type') # income, expense, atau transfer
            date_str = request.form['date']
            raw_amount = request.form['amount'].replace('.', '').replace(',', '.')
            amount = float(raw_amount)
            description = request.form['description']

            # --- LOGIKA KHUSUS TRANSFER ---
            if t_type == 'transfer':
                from_id = request.form['account_id'] # Sumber
                to_id = request.form['to_account_id'] # Tujuan
                
                if not to_id:
                    raise ValueError("Harap pilih akun tujuan transfer.")
                if from_id == to_id:
                    raise ValueError("Akun asal dan tujuan tidak boleh sama.")

                # Ambil nama akun untuk catatan histori
                acc_from = db.execute('SELECT name FROM accounts WHERE id = ?', (from_id,)).fetchone()['name']
                acc_to = db.execute('SELECT name FROM accounts WHERE id = ?', (to_id,)).fetchone()['name']
                clean_from = acc_from.split('] ')[1] if '] ' in acc_from else acc_from
                clean_to = acc_to.split('] ')[1] if '] ' in acc_to else acc_to

                # 1. Simpan transaksi Keluar (dari sumber)
                db.execute('''
                    INSERT INTO transactions (user_id, date, account_id, type, amount, description, category) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, date_str, from_id, 'expense', amount, f"Transfer ke {clean_to}: {description}", "Transfer Out"))
                
                # 2. Simpan transaksi Masuk (ke tujuan)
                db.execute('''
                    INSERT INTO transactions (user_id, date, account_id, type, amount, description, category) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, date_str, to_id, 'income', amount, f"Terima dari {clean_from}: {description}", "Transfer In"))

                # 3. Update Saldo kedua akun
                db.execute('UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?', (amount, from_id))
                db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', (amount, to_id))
            
            # --- LOGIKA TRANSAKSI BIASA (INCOME/EXPENSE) ---
            else:
                account_id = request.form['account_id']
                category = request.form['category']
                
                if not category:
                    raise ValueError("Kategori wajib dipilih.")

                db.execute('''
                    INSERT INTO transactions (user_id, date, account_id, type, amount, description, category) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, date_str, account_id, t_type, amount, description, category))

                adjustment = amount if t_type == 'income' else -amount
                db.execute('UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?', 
                           (adjustment, account_id))
            
            db.commit()
            flash("Data berhasil disimpan!", 'success')
            return redirect(url_for('dashboard'))

        except Exception as e:
            error = str(e)

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

# --- FITUR BARU: EXPORT DATA KE EXCEL (CSV) ---
@app.route('/export_csv')
@login_required
def export_csv():
    user_id = session.get('user_id')
    db = get_db()
    
    # Ambil parameter tanggal dari URL
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = '''
        SELECT t.date, a.name as account_name, t.type, t.category, t.amount, t.description
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ?
    '''
    params = [user_id]

    # Tambahkan filter jika user milih tanggal
    if start_date and end_date:
        query += " AND t.date BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    
    query += " ORDER BY t.date DESC"
    transactions = db.execute(query, params).fetchall()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Tanggal', 'Akun', 'Tipe', 'Kategori', 'Jumlah', 'Deskripsi'])
    
    for t in transactions:
        full_name = t['account_name']
        clean_name = full_name.split('] ')[1] if '] ' in full_name else full_name
        cw.writerow([t['date'], clean_name, t['type'].capitalize(), t['category'], t['amount'], t['description']])

    output = si.getvalue()
    si.close()

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=riwayat_transaksi.csv"}
    )

@app.route('/export_pdf')
@login_required
def export_pdf():
    user_id = session.get('user_id')
    db = get_db()
    
    # Ambil parameter tanggal dari URL
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

    class PDF(FPDF):
        def header(self):
            logo_path = os.path.join(app.root_path, 'static', 'img', 'logo.png')
            if os.path.exists(logo_path):
                self.image(logo_path, 7, 5, 31)
            
            self.set_font('Arial', 'B', 15)
            self.set_text_color(17, 35, 126) 
            self.set_y(10) 
            self.cell(0, 8, 'LAPORAN TRANSAKSI', 0, 1, 'R')
            
            self.set_font('Arial', 'B', 9)
            self.set_text_color(100, 100, 100)
            
            # JUDUL DINAMIS: Kalau ada filter, tampilin rentang tanggalnya
            tagline = 'Treasury Flow by Fernando Capital'
            if start_date and end_date:
                tagline = f'Periode: {start_date} s/d {end_date}'
            self.cell(0, 5, tagline, 0, 1, 'R')
            
            self.ln(2)
            self.set_font('Arial', '', 8)
            self.set_text_color(150, 150, 150)
            waktu_cetak = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.cell(0, 4, f'Dicetak pada: {waktu_cetak}', 0, 1, 'R')
            self.cell(0, 4, f'User: {session.get("fullname", "User")}', 0, 1, 'R')
            
            self.ln(2)
            self.set_draw_color(17, 35, 126)
            self.set_line_width(0.8)
            self.line(10, 36, 200, 36) 
            self.ln(10)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, f'Halaman {self.page_no()} / {{nb}}', 0, 0, 'C')

    pdf = PDF()
    pdf.alias_nb_pages() 
    pdf.add_page()
    
    # Header Tabel
    pdf.set_fill_color(17, 35, 126)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Arial', 'B', 10)
    
    pdf.cell(30, 10, 'TANGGAL', 1, 0, 'C', True)
    pdf.cell(40, 10, 'KATEGORI', 1, 0, 'C', True)
    pdf.cell(25, 10, 'TIPE', 1, 0, 'C', True)
    pdf.cell(40, 10, 'JUMLAH', 1, 0, 'C', True)
    pdf.cell(55, 10, 'KETERANGAN', 1, 1, 'C', True)

    # Isi Tabel
    pdf.set_text_color(0)
    pdf.set_font('Arial', '', 9)
    fill = False
    
    for t in transactions:
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(30, 8, str(t['date']), 1, 0, 'C', fill)
        pdf.cell(40, 8, str(t['category']), 1, 0, 'L', fill)
        
        if t['type'] == 'income':
            pdf.set_text_color(40, 167, 69)
            tipe_txt = 'Masuk'
        else:
            pdf.set_text_color(239, 68, 68)
            tipe_txt = 'Keluar'
            
        pdf.cell(25, 8, tipe_txt, 1, 0, 'C', fill)
        pdf.set_text_color(0)
        
        pdf.cell(40, 8, f"Rp {t['amount']:,.2f}", 1, 0, 'R', fill)
        pdf.cell(55, 8, str(t['description'])[:30], 1, 1, 'L', fill)
        fill = not fill

    # Gunakan 'ignore' pada encode agar tidak crash jika ada karakter non-latin1
    response = Response(pdf.output(dest='S').encode('latin-1', 'ignore'))
    response.headers.set('Content-Disposition', 'attachment', filename='Laporan_Keuangan.pdf')
    response.headers.set('Content-Type', 'application/pdf')
    return response

@app.route('/api/data-kalender')
@login_required
def data_kalender():
    user_id = session.get('user_id')
    db = get_db()
    db.row_factory = sqlite3.Row 
    
    query = '''
        SELECT date, 
               SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as total_in,
               SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as total_out
        FROM transactions 
        WHERE user_id = ?
        GROUP BY date
    '''
    rows = db.execute(query, (user_id,)).fetchall()
    
    events = []
    for row in rows:
        # Pemasukan
        if row['total_in'] > 0:
            events.append({
                'title': f"+{row['total_in']:,.0f}",
                'start': row['date'],
                'backgroundColor': '#E8EAF6',
                'textColor': '#11237E',
                'display': 'block'
            })
        # Pengeluaran
        if row['total_out'] > 0:
            events.append({
                'title': f"-{row['total_out']:,.0f}",
                'start': row['date'],
                'backgroundColor': '#FEE2E2',
                'textColor': '#EF4444',
                'display': 'block'
            })
            
    return jsonify(events) 

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)