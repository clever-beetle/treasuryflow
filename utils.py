import os
import sqlite3
import psycopg2
import psycopg2.extras
import psycopg2.errors
import locale
from functools import wraps
from flask import session, flash, redirect, url_for, g
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_babel import Babel
from concurrent.futures import ThreadPoolExecutor
from loguru import logger
import sys

# Configure loguru (optional but good practice)
logger.remove()
logger.add(sys.stderr, level="INFO")

cache = Cache(config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 60})
limiter = Limiter(key_func=get_remote_address, default_limits=["2000 per day", "500 per hour"])
babel = Babel()
bg_executor = ThreadPoolExecutor(max_workers=3)

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "treasuryflow@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "mhqefkbwcunkptvj")

CATEGORIES = {
    'income': ['Gaji', 'Investasi', 'Hadiah', 'Penjualan Aset', 'Lainnya (Pemasukan)'],
    'expense': ['Makanan & Minuman', 'Transportasi', 'Belanja', 'Tagihan', 
                'Hiburan', 'Kesehatan', 'Pendidikan', 'Cicilan & Utang', 'Lainnya (Pengeluaran)']
}

def format_rupiah(value):
    if value is None:
        return 'Rp 0'
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 'Rp 0'
    sign = "-" if value < 0 else ""
    abs_value = abs(value)
    formatted = '{:,.0f}'.format(abs_value).replace(',', '.')
    return sign + 'Rp ' + formatted

def format_rupiah_input(value):
    if value is None:
        return '0'
    try:
        value = float(value)
    except (TypeError, ValueError):
        return '0'
    formatted = '{:,.0f}'.format(abs(value)).replace(',', '.')
    return formatted

DATABASE = 'treasury_flow.db'
DATABASE_URL = os.environ.get('DATABASE_URL')
REPLICA_DATABASE_URL = os.environ.get('REPLICA_DATABASE_URL')

class DBWrapper:
    def __init__(self, primary_conn, replica_conn=None):
        self.conn = primary_conn
        self.primary_conn = primary_conn
        self.replica_conn = replica_conn

    def execute(self, query, params=()):
        cursor = self.primary_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        pg_query = query.replace('?', '%s')
        
        try:
            cursor.execute(pg_query, params)
        except psycopg2.errors.UniqueViolation as e:
            # Auto-fix sequence on duplicate key for INSERT statements
            if query.strip().upper().startswith('INSERT'):
                self.primary_conn.rollback()
                err_str = str(e)
                # Extract table name from query: INSERT INTO tablename
                try:
                    tbl = query.strip().split()[2].strip('(')
                    fix_cursor = self.primary_conn.cursor()
                    fix_cursor.execute(f"SELECT setval('{tbl}_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM {tbl}), false)")
                    self.primary_conn.commit()
                    logger.info(f"Auto-fixed sequence for {tbl}")
                    # Retry the original query
                    cursor = self.primary_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(pg_query, params)
                except Exception as retry_err:
                    logger.error(f"Sequence fix retry failed: {retry_err}")
                    raise e
            else:
                raise
        
        if self.replica_conn:
            is_write = query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'PRAGMA'))
            if is_write:
                try:
                    rep_cursor = self.replica_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    rep_cursor.execute(pg_query, params)
                except Exception as e:
                    logger.warning(f"Replica DB write failed - {e}")
                    
        return cursor
        
    def cursor(self):
        return self

    def commit(self):
        self.primary_conn.commit()
        if self.replica_conn:
            try:
                self.replica_conn.commit()
            except:
                pass

    def rollback(self):
        self.primary_conn.rollback()
        if self.replica_conn:
            try:
                self.replica_conn.rollback()
            except:
                pass

    def close(self):
        self.primary_conn.close()
        if self.replica_conn:
            try:
                self.replica_conn.close()
            except:
                pass

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            rep_conn = None
            if REPLICA_DATABASE_URL:
                try:
                    rep_conn = psycopg2.connect(REPLICA_DATABASE_URL, sslmode='require')
                except Exception as e:
                    logger.warning(f"Could not connect to Replica DB - {e}")
            db = g._database = DBWrapper(conn, rep_conn)
        else:
            db = g._database = sqlite3.connect(DATABASE)
            db.row_factory = sqlite3.Row
    return db

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Authentication required. Please log in to access this page.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Authentication required.', 'danger')
            return redirect(url_for('auth.login'))
        
        db = get_db()
        user = db.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if not user or user['role'] != 'admin':
            flash('Admin privilege required.', 'danger')
            return redirect(url_for('dashboard.dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function

def is_feature_enabled(feature_name):
    try:
        db = get_db()
        flag = db.execute('SELECT is_active FROM feature_flags WHERE name = ?', (feature_name,)).fetchone()
        if flag and flag['is_active']:
            return True
        return False
    except:
        return False

def _send_reset_email_task(email_input, fullname, reset_url):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['To'] = email_input
    msg['Subject'] = "Treasury Flow - Password Reset Request"
    
    body = f"""Hi {fullname or email_input},

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
        logger.info(f"Password reset email sent to {email_input}")
    except Exception as e:
        logger.error(f"Failed to send email to {email_input}: {e}")

def send_reset_email(email_input, fullname, reset_url):
    bg_executor.submit(_send_reset_email_task, email_input, fullname, reset_url)

