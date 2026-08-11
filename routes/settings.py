from flask import Blueprint, render_template, request, url_for, redirect, session, g, flash, Response, jsonify
from utils import get_db, login_required, format_rupiah, format_rupiah_input, CATEGORIES
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

            is_hashed = user['password'].startswith('scrypt:') or user['password'].startswith('pbkdf2:')
            pw_correct = check_password_hash(user['password'], old_password) if is_hashed else (old_password == user['password'])
            
            if not pw_correct:
                error = "Incorrect current password."
            elif new_password != confirm_password:
                error = "New password and confirmation do not match."
            else:
                hashed_pw = generate_password_hash(new_password)
                db.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_pw, user_id))
                db.commit()
                session.clear()
                return redirect(url_for('auth.login', message="Password updated successfully. Please log in again."))

        elif action == 'delete_account':
            password_check = request.form.get('password_check')
            is_hashed = user['password'].startswith('scrypt:') or user['password'].startswith('pbkdf2:')
            pw_correct = check_password_hash(user['password'], password_check) if is_hashed else (password_check == user['password'])
            if not pw_correct:
                error = "Password salah! Gagal menghapus akun."
            else:
                db.execute("DELETE FROM budgets WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM credit_cards WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM user_categories WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM financial_goals WHERE user_id = ?", (user_id,))
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
                return redirect(url_for('auth.login'))

        elif action == 'add_category':
            cat_type = request.form.get('type')
            cat_name = request.form.get('name')
            if cat_type and cat_name:
                # Check if it already exists to prevent duplicates
                existing = db.execute("SELECT id FROM user_categories WHERE user_id = ? AND name = ? AND type = ?", (user_id, cat_name, cat_type)).fetchone()
                if existing:
                    error = f"Kategori '{cat_name}' sudah ada."
                else:
                    db.execute("INSERT INTO user_categories (user_id, name, type) VALUES (?, ?, ?)", (user_id, cat_name, cat_type))
                    db.commit()
                    message = f"Kategori '{cat_name}' berhasil ditambahkan."
            else:
                error = "Data kategori tidak valid."

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
                db.execute("DELETE FROM credit_cards WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM financial_goals WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM debt_payments WHERE debt_id IN (SELECT id FROM debts_receivables WHERE user_id = ?)", (user_id,))
                db.execute("DELETE FROM debts_receivables WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM recurring_installments WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM assets WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
                db.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
                db.commit()
                
                message = "Seluruh data finansial Anda telah berhasil direset. Akun Anda tetap aman."

        user = db.execute('SELECT fullname, username, email, password FROM users WHERE id = ?', (user_id,)).fetchone()

    user_categories = db.execute("SELECT * FROM user_categories WHERE user_id = ?", (user_id,)).fetchall()
    return render_template('settings.html', user=user, error=error, message=message, user_categories=user_categories)

@settings_bp.route('/setup/accounts', methods=['GET', 'POST'])
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
        return redirect(url_for('settings.setup_account', message=message, error=error))

    if edit_id:
        account_to_edit = db.execute('SELECT id, name, initial_balance FROM accounts WHERE id = ? AND user_id = ?', (edit_id, user_id)).fetchone()

    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            raw_balance = request.form['initial_balance'].replace('.', '').replace(',', '.')
            balance = float(raw_balance)
            
            if action == 'edit':
                edit_account_id = request.form['edit_account_id']
                db.execute('UPDATE accounts SET initial_balance = ? WHERE id = ? AND user_id = ?', (balance, edit_account_id, user_id))
                db.commit()
                message = "Initial account balance has been successfully updated."
                return redirect(url_for('settings.setup_account', message=message))

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
        except Exception as e:
             if 'UNIQUE' in str(e) or 'IntegrityError' in str(type(e).__name__):
                 error = "Data integrity error occurred."
             else:
                 error = f"An error occurred: {e}"

    accounts = db.execute('SELECT id, name, initial_balance, current_balance FROM accounts WHERE user_id = ?', (user_id,)).fetchall()
    return render_template('setup_account.html', accounts=accounts, message=message, error=error, categories=ACCOUNT_TYPES, account_to_edit=account_to_edit)

@settings_bp.route('/add_cc', methods=['POST'])
@login_required
def add_cc():
    db = get_db()
    user_id = session['user_id']
    try:
        name = request.form['name']
        raw_limit = request.form.get('limit_amount', '0').replace('.', '').replace(',', '.')
        limit_amount = float(raw_limit) if raw_limit else 0.0
        raw_usage = request.form.get('current_usage', '0').replace('.', '').replace(',', '.')
        current_usage = float(raw_usage) if raw_usage else 0.0
        db.execute('INSERT INTO credit_cards (user_id, name, limit_amount, current_usage) VALUES (?, ?, ?, ?)',
                   (user_id, name, limit_amount, current_usage))
        db.commit()
        flash('Kartu kredit berhasil ditambahkan.', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan kartu kredit: {e}', 'danger')
    return redirect(url_for('performance.financial_performance'))

@settings_bp.route('/edit_cc/<int:id>', methods=['POST'])
@login_required
def edit_cc(id):
    db = get_db()
    user_id = session['user_id']
    try:
        name = request.form['name']
        raw_limit = request.form.get('limit_amount', '0').replace('.', '').replace(',', '.')
        limit_amount = float(raw_limit) if raw_limit else 0.0
        raw_usage = request.form.get('current_usage', '0').replace('.', '').replace(',', '.')
        current_usage = float(raw_usage) if raw_usage else 0.0
        db.execute('UPDATE credit_cards SET name = ?, limit_amount = ?, current_usage = ? WHERE id = ? AND user_id = ?',
                   (name, limit_amount, current_usage, id, user_id))
        db.commit()
        flash('Kartu kredit berhasil diperbarui.', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui kartu kredit: {e}', 'danger')
    return redirect(url_for('performance.financial_performance'))

@settings_bp.route('/delete_cc/<int:id>', methods=['POST'])
@login_required
def delete_cc(id):
    db = get_db()
    user_id = session['user_id']
    try:
        db.execute('DELETE FROM credit_cards WHERE id = ? AND user_id = ?', (id, user_id))
        db.commit()
        flash('Kartu kredit berhasil dihapus.', 'success')
    except Exception as e:
        flash(f'Gagal menghapus kartu kredit: {e}', 'danger')
    return redirect(url_for('performance.financial_performance'))

