import os
import sys
import time
import threading
import sqlite3
import psycopg2
import psycopg2.pool
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

# Configure loguru
logger.remove()
logger.add(sys.__stderr__ if sys.__stderr__ else sys.stderr, level="INFO", catch=True)

cache = Cache(config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 60})
limiter = Limiter(key_func=get_remote_address, default_limits=["2000 per day", "500 per hour"])
babel = Babel()
bg_executor = ThreadPoolExecutor(max_workers=4)

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "treasuryflow@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

CATEGORIES = {
    'income': ['Gaji', 'Investasi', 'Hadiah', 'Penjualan Aset', 'Lainnya (Pemasukan)'],
    'expense': ['Makanan & Minuman', 'Transportasi', 'Belanja', 'Tagihan',
                'Hiburan', 'Kesehatan', 'Pendidikan', 'Cicilan & Utang', 'Lainnya (Pengeluaran)']
}

DEFAULT_OTHER_CATEGORIES = {
    'income': 'Lainnya (Pemasukan)',
    'expense': 'Lainnya (Pengeluaran)',
}


def normalize_category_list(items, cat_type='expense'):
    """Deduplicate categories case-insensitively, sort A-Z, and keep 'Lainnya (...)' at the bottom."""
    other_label = DEFAULT_OTHER_CATEGORIES.get(cat_type, 'Lainnya (Pengeluaran)')
    seen = set()
    regular = []
    has_other = False
    ignored_lower = {'transfer', 'transfer in', 'transfer out'}

    for raw in (items or []):
        name = ' '.join(str(raw or '').split())
        if not name:
            continue
        low = name.lower()
        if low in ignored_lower:
            continue
        if low in ('lainnya', 'lainnya (pemasukan)', 'lainnya (pengeluaran)'):
            has_other = True
            continue
        if low in seen:
            continue
        seen.add(low)
        regular.append(name)

    regular.sort(key=lambda s: s.casefold())
    if has_other or other_label:
        regular.append(other_label)
    return regular


def get_user_categories(db, user_id):
    """Return cleanly deduplicated & neatly ordered built-in and custom categories for a user."""
    default_lower = {
        k: {c.strip().lower() for c in v} | {'lainnya', 'transfer', 'transfer in', 'transfer out'}
        for k, v in CATEGORIES.items()
    }
    raw_rows = db.execute(
        'SELECT id, type, name FROM user_categories WHERE user_id = ? ORDER BY id ASC',
        (user_id,)
    ).fetchall()

    custom_only = {'income': [], 'expense': []}
    custom_seen = {'income': set(), 'expense': set()}
    custom_rows = []

    for r in raw_rows:
        r_dict = dict(r)
        t = r_dict.get('type')
        if t not in ('income', 'expense'):
            continue
        clean_name = ' '.join(str(r_dict.get('name') or '').split())
        if not clean_name:
            continue
        low = clean_name.lower()
        # Skip legacy seeded copies of built-in defaults or bare 'Lainnya' duplicates
        if low in default_lower[t] or low in custom_seen[t]:
            continue
        custom_seen[t].add(low)
        custom_only[t].append(clean_name)
        custom_rows.append({
            'id': r_dict.get('id'),
            'type': t,
            'name': clean_name,
        })

    custom_only['income'].sort(key=lambda s: s.casefold())
    custom_only['expense'].sort(key=lambda s: s.casefold())
    custom_rows.sort(key=lambda r: (0 if r['type'] == 'income' else 1, r['name'].casefold()))

    merged = {
        'income': normalize_category_list(list(CATEGORIES['income']) + custom_only['income'], 'income'),
        'expense': normalize_category_list(list(CATEGORIES['expense']) + custom_only['expense'], 'expense'),
    }

    defaults_clean = {
        'income': normalize_category_list(CATEGORIES['income'], 'income'),
        'expense': normalize_category_list(CATEGORIES['expense'], 'expense'),
    }

    return {
        'merged': merged,
        'custom': custom_only,
        'custom_rows': custom_rows,
        'defaults': defaults_clean,
    }


def wib_now():
    """Current time in WIB (UTC+7) as a naive datetime, independent of the server's local timezone."""
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=7)


def spreadsheet_safe(value):
    """Prevent CSV/Excel formula injection: prefix text starting with = + - @ (or tab/CR) with an apostrophe."""
    if isinstance(value, str) and value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


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


def parse_amount(raw, default=0.0):
    """Parse a user-entered amount into a float.

    Accepts Indonesian formatting ("150.000", "150.000,50"), plain numbers
    ("150000"), and machine formatting ("150000.0", "150000.50").
    """
    import re
    from decimal import Decimal
    if raw is None:
        return default
    if isinstance(raw, (int, float, Decimal)):
        return float(raw)
    s = str(raw).strip().replace('Rp', '').replace('rp', '').replace(' ', '')
    if not s:
        return default
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif '.' in s and re.fullmatch(r'-?\d{1,3}(\.\d{3})+', s):
        s = s.replace('.', '')
    try:
        val = float(s)
    except ValueError:
        return default
    if val != val or val in (float('inf'), float('-inf')):
        return default
    return val


def format_amount_input(value):
    """Format a stored amount for an editable text input without losing decimals."""
    v = parse_amount(value)
    v = abs(v)
    if v == int(v):
        return '{:,.0f}'.format(v).replace(',', '.')
    s = '{:,.2f}'.format(v)
    s = s.replace(',', '#').replace('.', ',').replace('#', '.')
    return s.rstrip('0').rstrip(',')


@limiter.request_filter
def _limiter_skip_static():
    from flask import request
    return request.endpoint == 'static' or request.path.startswith('/static/') or request.path in ('/sw.js', '/favicon.ico', '/api/version')


DATABASE = 'treasury_flow.db'
DATABASE_URL = os.environ.get('DATABASE_URL')
REPLICA_DATABASE_URL = os.environ.get('REPLICA_DATABASE_URL')

_pg_pools = {}
_pool_lock = threading.Lock()
_conn_last_used = {}


def _get_pg_pool(dsn):
    pool = _pg_pools.get(dsn)
    if pool is not None and not pool.closed:
        return pool
    with _pool_lock:
        pool = _pg_pools.get(dsn)
        if pool is None or pool.closed:
            pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=8,
                dsn=dsn,
                sslmode='require',
                connect_timeout=5,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
            )
            _pg_pools[dsn] = pool
        return pool


def _acquire_pg_conn(dsn):
    pool = _get_pg_pool(dsn)
    for _ in range(2):
        conn = pool.getconn()
        if conn.closed != 0:
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass
            continue
        last_ts = _conn_last_used.get(id(conn), 0.0)
        now_ts = time.monotonic()
        # Only ping connections idle > 45s (e.g. Neon serverless sleep), zero overhead on active clicks
        if last_ts and (now_ts - last_ts) > 45.0:
            try:
                with conn.cursor() as cur:
                    cur.execute('SELECT 1')
                if not conn.autocommit:
                    conn.rollback()
            except Exception:
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                continue
        _conn_last_used[id(conn)] = now_ts
        return conn, pool
    # Fallback direct connect if pool had two stale sockets
    conn = psycopg2.connect(
        dsn,
        sslmode='require',
        connect_timeout=5,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )
    return conn, None


def _release_pg_conn(conn, pool, discard=False):
    if conn is None:
        return
    if pool is None:
        try:
            conn.close()
        except Exception:
            pass
        return
    if discard or conn.closed != 0:
        _conn_last_used.pop(id(conn), None)
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass
        return
    try:
        if conn.autocommit:
            conn.autocommit = False
        else:
            conn.rollback()
        _conn_last_used[id(conn)] = time.monotonic()
        pool.putconn(conn)
    except Exception:
        _conn_last_used.pop(id(conn), None)
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass


def _sync_replica_writes(replica_dsn, writes_batch):
    if not replica_dsn or not writes_batch:
        return
    conn = None
    pool = None
    discard = False
    try:
        conn, pool = _acquire_pg_conn(replica_dsn)
        cur = conn.cursor()
        for pg_query, params in writes_batch:
            try:
                cur.execute(pg_query, params)
            except Exception as e:
                logger.warning(f"Replica statement skipped - {e}")
                conn.rollback()
        conn.commit()
    except Exception as e:
        discard = True
        logger.warning(f"Replica DB async sync failed - {e}")
    finally:
        _release_pg_conn(conn, pool, discard=discard)


class DBWrapper:
    def __init__(self, primary_conn, replica_conn=None, pool=None, dsn=None):
        self.conn = primary_conn
        self.primary_conn = primary_conn
        self.replica_conn = replica_conn
        self._pool = pool
        self._dsn = dsn
        self._has_executed = False
        self._pending_replica_writes = []

    def execute(self, query, params=()):
        pg_query = query.replace('?', '%s')
        cursor = None

        try:
            cursor = self.primary_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(pg_query, params)
            self._has_executed = True
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            if not self._has_executed and self._dsn:
                # Stale pooled socket on first query of request: transparently swap & retry once
                _release_pg_conn(self.primary_conn, self._pool, discard=True)
                self.primary_conn, self._pool = _acquire_pg_conn(self._dsn)
                self.conn = self.primary_conn
                cursor = self.primary_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(pg_query, params)
                self._has_executed = True
            else:
                raise
        except psycopg2.errors.UniqueViolation as e:
            if query.strip().upper().startswith('INSERT'):
                self.primary_conn.rollback()
                try:
                    tbl = query.strip().split()[2].strip('(')
                    fix_cursor = self.primary_conn.cursor()
                    fix_cursor.execute(f"SELECT setval('{tbl}_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM {tbl}), false)")
                    self.primary_conn.commit()
                    logger.info(f"Auto-fixed sequence for {tbl}")
                    cursor = self.primary_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    cursor.execute(pg_query, params)
                    self._has_executed = True
                except Exception as retry_err:
                    logger.error(f"Sequence fix retry failed: {retry_err}")
                    raise e
            else:
                raise

        is_write = query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP'))
        if is_write:
            if self.replica_conn:
                try:
                    rep_cursor = self.replica_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                    rep_cursor.execute(pg_query, params)
                except Exception as e:
                    logger.warning(f"Replica DB write failed - {e}")
            elif REPLICA_DATABASE_URL:
                self._pending_replica_writes.append((pg_query, params))

        return cursor

    def cursor(self):
        return self

    def commit(self):
        self.primary_conn.commit()
        if self.replica_conn:
            try:
                self.replica_conn.commit()
            except Exception:
                pass
        elif self._pending_replica_writes and REPLICA_DATABASE_URL:
            batch = list(self._pending_replica_writes)
            self._pending_replica_writes.clear()
            if os.environ.get("TESTING") != "True":
                bg_executor.submit(_sync_replica_writes, REPLICA_DATABASE_URL, batch)

    def rollback(self):
        self._pending_replica_writes.clear()
        self.primary_conn.rollback()
        if self.replica_conn:
            try:
                self.replica_conn.rollback()
            except Exception:
                pass

    def close(self):
        self._pending_replica_writes.clear()
        _release_pg_conn(self.primary_conn, self._pool)
        if self.replica_conn:
            try:
                self.replica_conn.close()
            except Exception:
                pass


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        if DATABASE_URL:
            conn, pool = _acquire_pg_conn(DATABASE_URL)
            db = g._database = DBWrapper(conn, replica_conn=None, pool=pool, dsn=DATABASE_URL)
        else:
            conn = sqlite3.connect(DATABASE, timeout=15.0)
            conn.row_factory = sqlite3.Row
            db = g._database = conn
    return db


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan masuk terlebih dahulu untuk mengakses halaman ini.', 'danger')
            from flask import request
            next_url = request.full_path if request.full_path and not request.full_path.endswith('?') else request.path
            if next_url and next_url != '/login' and next_url.startswith('/'):
                return redirect(url_for('auth.login', next=next_url))
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
            flash('Akses ditolak. Halaman ini membutuhkan hak akses Admin.', 'danger')
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
    except Exception:
        return False


def _send_reset_email_task(email_input, fullname, reset_url):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_server = os.environ.get("SMTP_SERVER", SMTP_SERVER)
    smtp_port = int(os.environ.get("SMTP_PORT", SMTP_PORT))
    smtp_email = os.environ.get("SMTP_EMAIL", SMTP_EMAIL)
    smtp_password = os.environ.get("SMTP_PASSWORD", SMTP_PASSWORD)

    if os.environ.get("TESTING") == "True" or os.environ.get("FLASK_ENV") == "testing":
        logger.info(f"[TESTING] Skipping real SMTP send to {email_input}")
        return

    if not smtp_password:
        logger.warning(f"SMTP_PASSWORD belum diatur di environment; batal mengirim email reset ke {email_input}")
        return

    msg = MIMEMultipart()
    msg['From'] = smtp_email
    msg['To'] = email_input
    msg['Subject'] = "Treasury Flow - Permintaan Reset Password"

    body = f"""Halo {fullname or email_input},

Kami menerima permintaan untuk mereset password akun Treasury Flow Anda.
Klik tautan berikut untuk membuat password baru:

{reset_url}

Demi keamanan Anda, tautan ini hanya berlaku selama 15 menit. Jika Anda tidak merasa melakukan permintaan ini, abaikan email ini dan akun Anda tetap aman.

Salam hangat,
Kevin Fernando
Founder, Fernando Capital
Treasury Flow"""

    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
        server.starttls()
        server.login(smtp_email, smtp_password)
        server.sendmail(smtp_email, email_input, msg.as_string())
        server.quit()
        logger.info(f"Password reset email sent to {email_input}")
    except Exception as e:
        try:
            logger.error(f"Failed to send email to {email_input}: {e}")
        except Exception:
            pass


def send_reset_email(email_input, fullname, reset_url):
    bg_executor.submit(_send_reset_email_task, email_input, fullname, reset_url)
