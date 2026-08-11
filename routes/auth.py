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
@limiter.limit("5 per minute")
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
        login_input = request.form['username']
        password = request.form['password']
        
        user = db.execute('SELECT id, password FROM users WHERE username = ? OR email = ?', (login_input, login_input)).fetchone()
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
            
            user_data = db.execute('SELECT fullname FROM users WHERE id = ?', (user['id'],)).fetchone()
            session['fullname'] = user_data['fullname'] if user_data and user_data['fullname'] else login_input
            return redirect(url_for('dashboard.dashboard'))
        else:
            error = "Invalid username/email or password."
    
    return render_template('login.html', error=error)

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
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
            hashed_pw = generate_password_hash(password)
            db.execute('INSERT INTO users (fullname, username, email, password) VALUES (?, ?, ?, ?)',
                       (fullname, username, email, hashed_pw))
            db.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login', registered=True))
            
    return render_template('register.html', error=error)

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
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
    
    if not user:
        flash('Invalid or expired reset token.', 'danger')
        return redirect(url_for('auth.login'))
        
    expiry_time = datetime.strptime(user['token_expiry'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expiry_time:
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

@auth_bp.route('/api/biometric_login', methods=['POST'])
def biometric_login():
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'error': 'No username provided'})
        
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    
    if user:
        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        return jsonify({'success': True})
        
    return jsonify({'success': False, 'error': 'User not found'})

