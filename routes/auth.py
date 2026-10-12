from flask import Blueprint, render_template, request, url_for, redirect, session, g, flash, Response, jsonify
from utils import get_db, login_required, format_rupiah, format_rupiah_input, CATEGORIES, limiter
from models import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets, smtplib, json, csv, os
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fpdf import FPDF
from utils import SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("30 per minute", methods=["POST"])
def login():
    """
    User Login Endpoint
    ---
    tags:
      - Authentication
    parameters:
      - name: username
        in: formData
        type: string
        required: true
        description: Username or Email
      - name: password
        in: formData
        type: string
        required: true
        description: User password
    responses:
      302:
        description: Redirect to dashboard on successful login
      200:
        description: HTML page with error message
    """
    error = None
    if request.method == 'POST':
        db = get_db()
        login_input = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        
        if not login_input or not password:
            error = "Username/email dan password wajib diisi."
        else:
            user = db.execute('''
                SELECT id, password, username, fullname, role 
                FROM users 
                WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)
            ''', (login_input, login_input)).fetchone()
            
            valid_login = False
            if user:
                is_hashed = user['password'].startswith('scrypt:') or user['password'].startswith('pbkdf2:')
                if not is_hashed:
                    if user['password'] == password:
                        new_hash = generate_password_hash(password)
                        db.execute('UPDATE users SET password = ? WHERE id = ?', (new_hash, user['id']))
                        db.commit()
                        valid_login = True
                else:
                    valid_login = check_password_hash(user['password'], password)
                    
            if valid_login:
                session.clear()
                session['user_id'] = user['id']
                session['username'] = user['username'] if user['username'] else login_input
                session['fullname'] = user['fullname'] if user['fullname'] else session['username']
                session['role'] = user['role'] if 'role' in user and user['role'] else 'user'
                
                next_page = request.args.get('next') or request.form.get('next')
                if next_page and next_page.startswith('/') and not next_page.startswith('//') and next_page != '/login':
                    return redirect(next_page)
                return redirect(url_for('dashboard.dashboard'))
            else:
                error = "Username/email atau password salah."
    
    return render_template('login.html', error=error)

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("20 per minute", methods=["POST"])
def register():
    error = None
    if request.method == 'POST':
        db = get_db()
        fullname = (request.form.get('fullname') or '').strip()
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        
        if not fullname or not username or not password or not email:
            error = "Semua bidang wajib diisi."
        elif len(username) < 3:
            error = "Username minimal harus 3 karakter."
        elif ' ' in username:
            error = "Username tidak boleh mengandung spasi."
        elif '@' not in email or '.' not in email.split('@')[-1] or len(email.split('@')[-1].split('.')[-1]) < 2:
            error = "Format alamat email tidak valid."
        elif len(password) < 6:
            error = "Password minimal harus 6 karakter."
        elif db.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(?)', (username,)).fetchone():
            error = "Username sudah digunakan, silakan pilih username lain."
        elif db.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(?)', (email,)).fetchone():
            error = "Alamat email sudah terdaftar."
        else:
            try:
                hashed_pw = generate_password_hash(password)
                db.execute('INSERT INTO users (fullname, username, email, password) VALUES (?, ?, ?, ?)',
                           (fullname, username, email, hashed_pw))
                db.commit()
                flash('Pendaftaran akun berhasil! Silakan masuk.', 'success')
                return redirect(url_for('auth.login', registered=True))
            except Exception as e:
                try:
                    db.rollback()
                except Exception:
                    pass
                if 'UNIQUE' in str(e).upper() or 'DUPLICATE' in str(e).upper():
                    error = "Username atau email sudah terdaftar."
                else:
                    error = "Terjadi kesalahan sistem saat mendaftar. Silakan coba lagi."
            
    return render_template('register.html', error=error)

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Anda telah berhasil keluar dari akun.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
@limiter.limit("15 per minute", methods=["POST"])
def forgot_password():
    if request.method == 'POST':
        email_input = request.form.get('username') or request.form.get('email')
        if not email_input:
            flash('Please enter your email address.', 'danger')
            return render_template('forgot_password.html')
        db = get_db()
        user = db.execute('SELECT id, fullname FROM users WHERE email = ?', (email_input,)).fetchone()
        
        if user:
            token = secrets.token_urlsafe(32)
            expiry = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            
            db.execute('UPDATE users SET reset_token = ?, token_expiry = ? WHERE id = ?', (token, expiry, user['id']))
            db.commit()
            
            from utils import send_reset_email
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            send_reset_email(email_input, user['fullname'], reset_url)
            flash('Password reset link is being sent to your email. It may take a moment to arrive.', 'success')
        else:
            flash('Email address not found in our system.', 'danger')
            
    return render_template('forgot_password.html')

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    db = get_db()
    user = db.execute('SELECT id, token_expiry FROM users WHERE reset_token = ?', (token,)).fetchone()
    
    if not user or not user['token_expiry']:
        flash('Invalid or expired reset token.', 'danger')
        return redirect(url_for('auth.login'))
        
    try:
        expiry_time = datetime.strptime(str(user['token_expiry'])[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        expiry_time = None

    if not expiry_time or datetime.now() > expiry_time:
        flash('Reset token has expired.', 'danger')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        new_password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
            
        hashed_pw = generate_password_hash(new_password)
        db.execute('UPDATE users SET password = ?, reset_token = NULL, token_expiry = NULL WHERE id = ?', (hashed_pw, user['id']))
        db.commit()
        flash('Your password has been successfully reset. Please log in.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('reset_password.html', token=token)

