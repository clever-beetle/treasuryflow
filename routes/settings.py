from flask import Blueprint, render_template, request, url_for, redirect, session, g, flash, Response, jsonify
from utils import get_db, login_required, format_rupiah, format_rupiah_input, parse_amount, CATEGORIES
from models import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets, smtplib, json, csv, os
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fpdf import FPDF

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/settings', methods=['GET', 'POST'])
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
            new_fullname = (request.form.get('fullname') or '').strip()
            if not new_fullname:
                error = "Nama lengkap tidak boleh kosong."
            else:
                db.execute('UPDATE users SET fullname = ? WHERE id = ?', (new_fullname, user_id))
                db.commit()
                session['fullname'] = new_fullname 
                message = "Nama lengkap berhasil diperbarui."
        
        elif action == 'update_username':
            new_username = (request.form.get('username') or '').strip()
            if not new_username:
                error = "Username tidak boleh kosong."
            elif len(new_username) < 3:
                error = "Username minimal harus 3 karakter."
            elif ' ' in new_username:
                error = "Username tidak boleh mengandung spasi."
            elif db.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(?) AND id != ?', (new_username, user_id)).fetchone():
                error = "Username sudah digunakan oleh akun lain."
            else:
                db.execute('UPDATE users SET username = ? WHERE id = ?', (new_username, user_id))
                db.commit()
                session['username'] = new_username
                message = "Username berhasil diperbarui."

        elif action == 'update_password':
            old_password = request.form.get('old_password') or ''
            new_password = request.form.get('new_password') or ''
            confirm_password = request.form.get('confirm_password') or ''

            is_hashed = user['password'].startswith('scrypt:') or user['password'].startswith('pbkdf2:')
            pw_correct = check_password_hash(user['password'], old_password) if is_hashed else (old_password == user['password'])
            
            if not pw_correct:
                error = "Password saat ini tidak sesuai."
            elif len(new_password) < 6:
                error = "Password baru minimal harus 6 karakter."
            elif new_password != confirm_password:
                error = "Password baru dan konfirmasi password tidak cocok."
            else:
                hashed_pw = generate_password_hash(new_password)
                db.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_pw, user_id))
                db.commit()
                session.clear()
                flash("Password berhasil diperbarui. Silakan masuk kembali dengan password baru Anda.", "success")
                return redirect(url_for('auth.login'))

        elif action == 'delete_account':
            password_check = request.form.get('password_check')
            is_hashed = user['password'].startswith('scrypt:') or user['password'].startswith('pbkdf2:')
            pw_correct = check_password_hash(user['password'], password_check) if is_hashed else (password_check == user['password'])
            if not pw_correct:
                error = "Password salah! Gagal menghapus akun."
            else:
                db.execute("DELETE FROM budgets WHERE user_id = ?", (user_id,))
                try:
                    db.execute("DELETE FROM credit_cards WHERE user_id = ?", (user_id,))
                except Exception:
                    pass
                db.execute("DELETE FROM user_categories WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM financial_goals WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM debt_payments WHERE debt_id IN (SELECT id FROM debts_receivables WHERE user_id = ?)", (user_id,))
                db.execute("DELETE FROM debts_receivables WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM recurring_installments WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM assets WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
                try:
                    db.execute("DELETE FROM deleted_transactions WHERE user_id = ?", (user_id,))
                except Exception:
                    pass
                try:
                    db.execute("DELETE FROM webauthn_credentials WHERE user_id = ?", (user_id,))
                except Exception:
                    pass
                try:
                    db.execute("DELETE FROM user_achievements WHERE user_id = ?", (user_id,))
                except Exception:
                    pass
                try:
                    db.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
                except Exception:
                    pass
                db.execute("DELETE FROM users WHERE id = ?", (user_id,))
                db.commit()
                
                session.clear()
                flash("Akun Anda beserta seluruh data terkait telah berhasil dihapus secara permanen.", "success")
                return redirect(url_for('auth.login'))

        elif action == 'add_category':
            cat_type = request.form.get('type')
            cat_name = (request.form.get('name') or '').strip()
            if cat_type in ['income', 'expense'] and cat_name:
                # Check if it already exists to prevent duplicates (case-insensitive)
                existing = db.execute("SELECT id FROM user_categories WHERE user_id = ? AND LOWER(name) = LOWER(?) AND type = ?", (user_id, cat_name, cat_type)).fetchone()
                if existing:
                    error = f"Kategori '{cat_name}' sudah ada."
                else:
                    db.execute("INSERT INTO user_categories (user_id, name, type) VALUES (?, ?, ?)", (user_id, cat_name, cat_type))
                    db.commit()
                    message = f"Kategori '{cat_name}' berhasil ditambahkan."
            else:
                error = "Nama kategori dan jenis kategori wajib diisi."

        elif action == 'delete_category':
            cat_id = request.form.get('category_id')
            if cat_id:
                db.execute("DELETE FROM user_categories WHERE id = ? AND user_id = ?", (cat_id, user_id))
                db.commit()
                message = "Kategori berhasil dihapus."

        elif action == 'reset_data':
            password_check = request.form.get('password_check')
            is_hashed = user['password'].startswith('scrypt:') or user['password'].startswith('pbkdf2:')
            pw_correct = check_password_hash(user['password'], password_check) if is_hashed else (password_check == user['password'])
            if not pw_correct:
                error = "Password salah! Gagal mereset data."
            else:
                db.execute("DELETE FROM budgets WHERE user_id = ?", (user_id,))
                try:
                    db.execute("DELETE FROM credit_cards WHERE user_id = ?", (user_id,))
                except Exception:
                    pass
                db.execute("DELETE FROM financial_goals WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM debt_payments WHERE debt_id IN (SELECT id FROM debts_receivables WHERE user_id = ?)", (user_id,))
                db.execute("DELETE FROM debts_receivables WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM recurring_installments WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM assets WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
                try:
                    db.execute("DELETE FROM deleted_transactions WHERE user_id = ?", (user_id,))
                except Exception:
                    pass
                db.commit()
                
                message = "Seluruh data finansial Anda telah berhasil direset. Akun Anda tetap aman."

        elif action == 'toggle_auto_sync':
            try:
                existing = db.execute("SELECT * FROM feature_flags WHERE name = 'auto_sync'").fetchone()
                if existing:
                    new_val = not existing['is_active']
                    db.execute("UPDATE feature_flags SET is_active = ? WHERE name = 'auto_sync'", (new_val,))
                else:
                    db.execute("INSERT INTO feature_flags (name, is_active) VALUES ('auto_sync', ?)", (1,))
                db.commit()
                message = "Auto Sync berhasil diperbarui."
            except Exception:
                db.rollback()

        user = db.execute('SELECT fullname, username, email, password FROM users WHERE id = ?', (user_id,)).fetchone()

    user_categories = db.execute("SELECT * FROM user_categories WHERE user_id = ?", (user_id,)).fetchall()
    
    # Get auto_sync status
    auto_sync_enabled = False
    try:
        flag = db.execute("SELECT is_active FROM feature_flags WHERE name = 'auto_sync'").fetchone()
        if flag:
            auto_sync_enabled = flag['is_active']
    except Exception:
        pass
    
    return render_template('settings.html', user=user, error=error, message=message, user_categories=user_categories, auto_sync_enabled=auto_sync_enabled)

@settings_bp.route('/setup/accounts', methods=['GET', 'POST'])
@login_required
def setup_account():
    db = get_db()
    error = request.args.get('error')
    message = request.args.get('message')
    user_id = session['user_id'] 
    
    edit_id = request.args.get('edit_id', type=int)
    delete_id = request.args.get('delete_id', type=int)
    account_to_edit = None

    ACCOUNT_TYPES = {
        'CASH': ['Cash'],
        'E-WALLET': ['DANA', 'GoPay', 'LinkAja', 'OVO', 'ShopeePay'],
        'BANK': ['BCA', 'BNI', 'BRI', 'BSI', 'CIMB Niaga', 'Mandiri', 'Bank Jago', 'Permata Bank', 'SeaBank', 
                'Superbank', 'Bank DKI', 'Bank Mega', 'BJB', 'Jenius', 'OCBC NISP', 'BTN', 'HSBC'],
        'KARTU KREDIT': ['BCA Card', 'Mandiri Card', 'BNI Card', 'BRI Card', 'NEX Card BRI', 'Honest Card', 'CIMB Niaga Card', 'Citi Card', 'HSBC Card', 'DBS Card', 'Mega Card', 'Lainnya'],
        'PAYLATER': ['SPayLater', 'GoPayLater', 'Traveloka PayLater', 'Kredivo', 'Akulaku', 'Indodana', 'Lainnya'],
        'PINJOL': ['SPinjam', 'AdaKami', 'Easycash', 'Kredit Pintar', 'Julo', 'Rupiah Cepat', 'Lainnya']
    }
    
    ACCOUNT_TYPES['E-WALLET'].sort()
    ACCOUNT_TYPES['BANK'].sort()

    if delete_id and request.method == 'POST':
        account_row = db.execute('SELECT name FROM accounts WHERE id = ? AND user_id = ?', (delete_id, user_id)).fetchone()
        if not account_row:
            error = "Akun tidak ditemukan atau Anda tidak memiliki akses."
        else:
            account_name = account_row['name']
            has_transactions = db.execute('SELECT COUNT(id) FROM transactions WHERE account_id = ? AND user_id = ?', (delete_id, user_id)).fetchone()[0]

            if has_transactions > 0:
                error = f"Gagal menghapus {account_name}. Akun ini masih memiliki {has_transactions} riwayat transaksi. Hapus transaksinya terlebih dahulu."
            else:
                try:
                    db.execute('UPDATE recurring_installments SET linked_account_id = NULL WHERE linked_account_id = ? AND user_id = ?', (delete_id, user_id))
                except Exception:
                    pass
                db.execute('DELETE FROM accounts WHERE id = ? AND user_id = ?', (delete_id, user_id))
                db.commit()
                from routes.dashboard import recalculate_account_balances
                recalculate_account_balances(db, user_id)
                message = f"{account_name} berhasil dihapus."
        return redirect(url_for('settings.setup_account', message=message, error=error))

    if edit_id:
        account_to_edit = db.execute('SELECT * FROM accounts WHERE id = ? AND user_id = ?', (edit_id, user_id)).fetchone()

    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            balance = parse_amount(request.form.get('initial_balance', '0'))
            
            if action == 'edit':
                edit_account_id = request.form.get('edit_account_id')
                
                # Check if liability account — negate balance (debt)
                acc_row = db.execute('SELECT account_type FROM accounts WHERE id = ? AND user_id = ?', (edit_account_id, user_id)).fetchone()
                if not acc_row:
                    error = "Akun tidak ditemukan atau Anda tidak memiliki akses."
                    accounts = db.execute('SELECT * FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
                    return render_template('setup_account.html', accounts=accounts, message=message, error=error, categories=ACCOUNT_TYPES, account_to_edit=account_to_edit)
                    
                if acc_row['account_type'] == 'liability':
                    balance = -abs(balance) if balance != 0 else 0
                
                billing_due_day_raw = request.form.get('billing_due_day', '')
                try:
                    billing_due_day = int(billing_due_day_raw) if billing_due_day_raw else None
                except (ValueError, TypeError):
                    billing_due_day = None
                
                limit_amount = parse_amount(request.form.get('limit_amount', '0'))
                try:
                    db.execute('UPDATE accounts SET initial_balance = ?, limit_amount = ?, billing_due_day = ? WHERE id = ? AND user_id = ?', (balance, limit_amount, billing_due_day, edit_account_id, user_id))
                except Exception:
                    db.rollback()
                    db.execute('UPDATE accounts SET initial_balance = ?, limit_amount = ? WHERE id = ? AND user_id = ?', (balance, limit_amount, edit_account_id, user_id))
                    
                db.commit()
                from routes.dashboard import recalculate_account_balances
                recalculate_account_balances(db, user_id)
                message = "Pengaturan akun berhasil diperbarui."
                return redirect(url_for('settings.setup_account', message=message))

            elif action == 'add':
                category_key = (request.form.get('category_key') or '').strip()
                if category_key == 'CASH':
                    name_detail = 'Cash' 
                    final_name = "Cash"
                else:
                    name_detail = (request.form.get('name_detail') or '').strip()
                    final_name = f"[{category_key}] {name_detail}"
                
                if not category_key or category_key not in ACCOUNT_TYPES or not name_detail or name_detail not in ACCOUNT_TYPES[category_key]:
                     raise ValueError("Pilihan kategori atau nama institusi tidak valid.")
                
                # Check if it's a liability type
                is_liability = category_key in ['KARTU KREDIT', 'PAYLATER', 'PINJOL']
                account_type = 'liability' if is_liability else 'asset'
                
                # For liability accounts, negate balance (debt stored as negative)
                if is_liability:
                    balance = -abs(balance) if balance != 0 else 0
                    limit_amount = parse_amount(request.form.get('limit_amount', '0'))
                    billing_due_day_raw = request.form.get('billing_due_day', '')
                    try:
                        billing_due_day = int(billing_due_day_raw) if billing_due_day_raw else None
                    except (ValueError, TypeError):
                        billing_due_day = None
                else:
                    limit_amount = 0.0
                    billing_due_day = None
                
                existing_account = db.execute('SELECT id FROM accounts WHERE user_id = ? AND LOWER(name) = LOWER(?)', (user_id, final_name)).fetchone()
                if existing_account:
                     error = f"Akun '{final_name}' sudah terdaftar."
                else:
                    try:
                        db.execute('INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type, limit_amount, billing_due_day) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                                   (user_id, final_name, balance, balance, account_type, limit_amount, billing_due_day))
                    except Exception:
                        db.rollback()
                        db.execute('INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type, limit_amount) VALUES (?, ?, ?, ?, ?, ?)', 
                                   (user_id, final_name, balance, balance, account_type, limit_amount))
                    db.commit()
                    from routes.dashboard import recalculate_account_balances
                    recalculate_account_balances(db, user_id)
                    message = f"Akun {final_name} berhasil didaftarkan."
        
        except ValueError as e:
            error = str(e) or "Input saldo harus berupa angka yang valid."
        except Exception as e:
            try:
                db.rollback()
            except:
                pass
            if 'UNIQUE' in str(e) or 'IntegrityError' in str(type(e).__name__):
                error = "Data integrity error occurred."
            else:
                error = f"An error occurred: {e}"

    accounts = db.execute('SELECT * FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    return render_template('setup_account.html', accounts=accounts, message=message, error=error, categories=ACCOUNT_TYPES, account_to_edit=account_to_edit)

