import os
import sqlite3
import psycopg2
import psycopg2.extras
import locale
import csv 
import secrets
from io import StringIO 
from datetime import datetime, timedelta 
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, url_for, redirect, session, g, flash, Response, jsonify, current_app
from fpdf import FPDF
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
import pathlib
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from flasgger import Swagger

load_dotenv()

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN", ""),
    integrations=[FlaskIntegration()],
    traces_sample_rate=0.1,
    profiles_sample_rate=0.1,
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'finance-tracker-static-secret-key-fallback')
csrf = CSRFProtect(app)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SWAGGER={
        'title': 'Treasury Flow API',
        'uiversion': 3
    }
)
swagger = Swagger(app)

import utils
from utils import logger

# --- SQLAlchemy Initialization (Strangler Pattern) ---
from models import db
if utils.DATABASE_URL:
    # Use postgres for Vercel
    app.config['SQLALCHEMY_DATABASE_URI'] = utils.DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    import pathlib
    db_path = pathlib.Path(__file__).parent / utils.DATABASE
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

from flask_migrate import Migrate
from flask_talisman import Talisman

migrate = Migrate(app, db)
utils.cache.init_app(app)
utils.limiter.init_app(app)

# OpenTelemetry Instrumentation
if os.environ.get('ENABLE_TELEMETRY') == '1':
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        
        trace.set_tracer_provider(TracerProvider())
        trace.get_tracer_provider().add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter())
        )
        FlaskInstrumentor().instrument_app(app)
    except Exception:
        pass

csp = {
    'default-src': [
        '\'self\'',
        'https://cdn.jsdelivr.net',
        'https://cdnjs.cloudflare.com',
        'https://fonts.googleapis.com',
        'https://fonts.gstatic.com',
        'https://unpkg.com',
        'https://cdn.tailwindcss.com'
    ],
    'script-src': [
        '\'self\'',
        '\'unsafe-inline\'',
        '\'unsafe-eval\'',
        'https://cdn.jsdelivr.net',
        'https://cdn.tailwindcss.com',
        'https://unpkg.com'
    ],
    'style-src': [
        '\'self\'',
        '\'unsafe-inline\'',
        'https://cdn.jsdelivr.net',
        'https://cdnjs.cloudflare.com',
        'https://fonts.googleapis.com',
        'https://cdn.tailwindcss.com',
        'https://unpkg.com'
    ],
    'font-src': [
        '\'self\'',
        'https://fonts.gstatic.com',
        'https://cdnjs.cloudflare.com'
    ],
    'img-src': [
        '\'self\'',
        'data:',
        'https:'
    ]
}
#Talisman(app, content_security_policy=csp)

def get_locale():
    return request.accept_languages.best_match(['en', 'id'])
utils.babel.init_app(app, locale_selector=get_locale)

@app.route('/sw.js')
def sw():
    return app.send_static_file('sw.js')

@app.route('/robots.txt')
def robots():
    content = "User-agent: *\nAllow: /\nDisallow: /settings/\nSitemap: https://www.treasuryflow.web.id/sitemap.xml"
    response = make_response(content)
    response.headers['Content-Type'] = 'text/plain'
    return response

@app.route('/sitemap.xml')
def sitemap():
    import datetime
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://www.treasuryflow.web.id/</loc>
        <lastmod>{today}</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>https://www.treasuryflow.web.id/login</loc>
        <lastmod>{today}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>https://www.treasuryflow.web.id/register</loc>
        <lastmod>{today}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
</urlset>"""
    response = make_response(xml)
    response.headers['Content-Type'] = 'application/xml'
    return response

@app.route('/test_db')
def test_db():
    try:
        import psycopg2
        import traceback
        conn = psycopg2.connect(utils.DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM debts_receivables LIMIT 1")
        return "Query succeeded!"
    except Exception as e:
        import traceback
        return f"<pre>{traceback.format_exc()}</pre>"

# Database initialization is now moved to CLI commands to prevent slow Vercel cold starts
# ----------------------------------------------------

app.jinja_env.filters['rupiah'] = utils.format_rupiah
app.jinja_env.filters['format_rupiah_input'] = utils.format_rupiah_input

try:
    locale.setlocale(locale.LC_ALL, 'id_ID.utf8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'indonesian')
    except locale.Error:
        pass 

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = utils.get_db()
        cursor = db.cursor()
        
        try:
            db.conn.autocommit = True
        except:
            pass
            
        is_pg = bool(utils.DATABASE_URL)
        pk_type = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        blob_type = "BYTEA" if is_pg else "BLOB"
        
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                id {pk_type},
                fullname TEXT, 
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                password TEXT NOT NULL,
                reset_token TEXT,
                token_expiry TEXT
            )
        ''')
        
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS accounts (
                id {pk_type},
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                initial_balance REAL NOT NULL DEFAULT 0.0,
                current_balance REAL NOT NULL DEFAULT 0.0,
                account_type TEXT DEFAULT 'asset',
                limit_amount REAL DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE (user_id, name)
            )
        ''')
        
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS transactions (
                id {pk_type},
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                category TEXT,
                type TEXT NOT NULL,
                account_id INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users (id),
                FOREIGN KEY(account_id) REFERENCES accounts (id)
            )
        ''')
        
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS debts_receivables (
                id {pk_type},
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
        try:
            cursor.execute("ALTER TABLE debts_receivables ADD COLUMN status TEXT DEFAULT 'BELUM LUNAS'")
        except Exception:
            pass
            
        try:
            cursor.execute("ALTER TABLE accounts ADD COLUMN account_type TEXT DEFAULT 'asset'")
            cursor.execute("ALTER TABLE accounts ADD COLUMN limit_amount REAL DEFAULT 0.0")
        except Exception:
            pass
            
        try:
            # Migrate existing credit cards to accounts if they exist, then delete them from credit_cards
            # to avoid duplicate migration on subsequent runs.
            cursor.execute("SELECT * FROM credit_cards")
            cards = cursor.fetchall()
            for c in cards:
                # Add to accounts
                try:
                    cursor.execute('''
                        INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type, limit_amount)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    ''', (c['user_id'], f"[KARTU KREDIT] {c['name']}", 0.0, -float(c['current_usage']), 'liability', c['limit_amount']))
                    # Delete from credit cards
                    cursor.execute("DELETE FROM credit_cards WHERE id = %s", (c['id'],))
                except Exception as ex:
                    logger.warning(f"Failed to migrate card {c['id']}: {ex}")
        except Exception as e:
            pass
            
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS debt_payments (
                id {pk_type},
                debt_id INTEGER NOT NULL,
                account_name TEXT NOT NULL,
                amount_paid REAL NOT NULL,
                payment_date TEXT DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        ''')
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS recurring_installments (
                id {pk_type},
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
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS assets (
                id {pk_type},
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
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS financial_goals (
                id {pk_type},
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0,
                due_date TEXT NOT NULL,
                status TEXT DEFAULT 'In Progress',
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS credit_cards (
                id {pk_type},
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                limit_amount REAL NOT NULL,
                current_usage REAL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS user_categories (
                id {pk_type},
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                name TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE (user_id, type, name)
            )
        ''')
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS deleted_transactions (
                id {pk_type},
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                category TEXT,
                type TEXT NOT NULL,
                account_id INTEGER NOT NULL,
                deleted_at TEXT NOT NULL
            )
        ''')
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS notifications (
                id {pk_type},
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS user_achievements (
                id {pk_type},
                user_id INTEGER NOT NULL UNIQUE,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                badges TEXT DEFAULT '[]',
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS webauthn_credentials (
                id {pk_type},
                user_id INTEGER NOT NULL,
                credential_id TEXT NOT NULL,
                public_key {blob_type} NOT NULL,
                sign_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users (id)
            )
        ''')
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS budgets (
                id {pk_type},
                user_id INTEGER NOT NULL,
                category_name VARCHAR(100) NOT NULL,
                limit_amount FLOAT NOT NULL,
                CONSTRAINT uq_user_category_budget UNIQUE (user_id, category_name),
                FOREIGN KEY(user_id) REFERENCES users (id)
            )
        ''')
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS feature_flags (
                id {pk_type},
                name VARCHAR(50) UNIQUE NOT NULL,
                is_active BOOLEAN DEFAULT FALSE
            )
        ''')
        
        if is_pg:
            # Commit the CREATE TABLE statements first so they are saved
            db.commit()
            
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'")
                db.commit()
            except Exception:
                db.rollback()
                
            try:
                cursor.execute("ALTER TABLE transactions ADD COLUMN hash TEXT")
                db.commit()
            except Exception:
                db.rollback()
                
            try:
                cursor.execute("ALTER TABLE transactions ADD COLUMN previous_hash TEXT")
                db.commit()
            except Exception:
                db.rollback()
            
            try:
                cursor.execute("ALTER TABLE transactions ADD COLUMN linked_transaction_id INTEGER")
                db.commit()
            except Exception:
                db.rollback()

            try:
                cursor.execute("ALTER TABLE accounts ADD COLUMN billing_due_day INTEGER")
                db.commit()
            except Exception:
                db.rollback()

            # Fix PostgreSQL sequences - reset to MAX(id) to prevent duplicate key errors
            seq_tables = [
                'users', 'accounts', 'transactions', 'debts_receivables', 'debt_payments',
                'recurring_installments', 'assets', 'financial_goals', 'credit_cards',
                'user_categories', 'deleted_transactions', 'notifications', 'user_achievements',
                'webauthn_credentials', 'budgets', 'feature_flags', 'error_logs'
            ]
            for tbl in seq_tables:
                try:
                    # Try standard naming convention first: {table}_id_seq
                    cursor.execute(f"SELECT setval('{tbl}_id_seq', COALESCE((SELECT MAX(id) FROM {tbl}), 1), true)")
                    db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except:
                        pass
                    # Fallback: try pg_get_serial_sequence
                    try:
                        cursor.execute(f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), COALESCE((SELECT MAX(id) FROM {tbl}), 1), true)")
                        db.commit()
                    except Exception:
                        try:
                            db.rollback()
                        except:
                            pass
            
        if not is_pg:
            cursor.execute("PRAGMA table_info(users)")
            user_cols = [info[1] for info in cursor.fetchall()]
            if 'password' not in user_cols:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN password TEXT DEFAULT '12345'")
                except Exception:
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
            if 'role' not in user_cols:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
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
            if 'linked_transaction_id' not in trans_cols:
                try:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN linked_transaction_id INTEGER")
                except sqlite3.OperationalError:
                    pass
            if 'hash' not in trans_cols:
                try:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN hash TEXT")
                except sqlite3.OperationalError:
                    pass
            if 'previous_hash' not in trans_cols:
                try:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN previous_hash TEXT")
                except sqlite3.OperationalError:
                    pass
        
        # Promote user 1 to admin (God Mode)
        try:
            cursor.execute("UPDATE users SET role = 'admin' WHERE id = 1")
        except Exception:
            pass
            
        db.commit()

@app.cli.command("init-db")
def init_db_command():
    """Create new tables if they don't exist."""
    init_db()
    print("Initialized the database.")

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.transactions import transactions_bp
from routes.performance import performance_bp
from routes.settings import settings_bp
from routes.ai import ai_bp
from routes.admin import admin_bp
from routes.auth_biometric import auth_biometric_bp
from routes.graphql_api import graphql_bp
from routes.stream import stream_bp
from routes.extra import extra_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(transactions_bp, url_prefix='/transactions')
app.register_blueprint(performance_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(auth_biometric_bp)
app.register_blueprint(graphql_bp)
app.register_blueprint(stream_bp)
app.register_blueprint(extra_bp)



@app.context_processor
def inject_clean_url():
    def clean_url(endpoint, **kwargs):
        from flask import url_for
        filtered_kwargs = {}
        for k, v in kwargs.items():
            if v == '' or v is None:
                continue
            if k == 'page' and (v == 1 or v == '1'):
                continue
            if k == 'sort_by' and v == 'date':
                continue
            if k == 'sort_order' and v == 'desc':
                continue
            filtered_kwargs[k] = v
            
        if endpoint == 'transactions.transactions_list':
            if filtered_kwargs.get('view') == 'calendar':
                endpoint = 'transactions.transactions_calendar'
                filtered_kwargs.pop('view')
            elif filtered_kwargs.get('view') == 'list':
                filtered_kwargs.pop('view', None)
                
        return url_for(endpoint, **filtered_kwargs)
    return dict(clean_url=clean_url)

@app.after_request
def add_header(response):
    if 'text/html' in response.headers.get('Content-Type', ''):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
    return response

from flask_wtf.csrf import CSRFError
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('Your session expired or was invalid. Please try again.', 'warning')
    return redirect(request.url)

@app.route('/session_expired')
def session_expired():
    from flask import session
    try:
        if 'user_id' not in session:
            return "Not logged in"
        user_id = session['user_id']
        db = utils.get_db()
        cursor = db.cursor()
        
        queries = {
            "get_accounts": "SELECT name, initial_balance, current_balance, id FROM accounts WHERE user_id = %s",
            "debts_receivables": "SELECT * FROM debts_receivables WHERE user_id = %s AND status = 'BELUM LUNAS' ORDER BY due_date ASC",
            "recurring_installments": "SELECT * FROM recurring_installments WHERE user_id = %s AND is_active = 1 ORDER BY due_day_of_month ASC",
            "credit_cards": "SELECT * FROM credit_cards WHERE user_id = %s ORDER BY name ASC",
            "assets": "SELECT category, COALESCE(SUM(purchase_price), 0) as total FROM assets WHERE user_id = %s GROUP BY category",
            "financial_goals": "SELECT id, name, target_amount, current_amount, due_date, status, COALESCE((current_amount / NULLIF(target_amount, 0) * 100), 0) as percentage FROM financial_goals WHERE user_id = %s ORDER BY status DESC, due_date ASC"
        }
        
        results = []
        for name, q in queries.items():
            try:
                cursor.execute(q, (user_id,))
                cursor.fetchall()
                results.append(f"{name}: OK")
            except Exception as e:
                db.conn.rollback()
                return f"Query {name} failed: {e}"
        return "<br>".join(results)
    except Exception as e:
        return f"Outer Error: {e}"

@app.route('/test_performance')
def test_performance():
    from flask import session
    try:
        if 'user_id' not in session:
            return "Not logged in"
        user_id = session['user_id']
        db = utils.get_db()
        cursor = db.cursor()
        
        queries = {
            "get_accounts": "SELECT name, initial_balance, current_balance, id FROM accounts WHERE user_id = %s",
            "debts_receivables": "SELECT * FROM debts_receivables WHERE user_id = %s AND status = 'BELUM LUNAS' ORDER BY due_date ASC",
            "recurring_installments": "SELECT * FROM recurring_installments WHERE user_id = %s AND is_active = 1 ORDER BY due_day_of_month ASC",
            "credit_cards": "SELECT * FROM credit_cards WHERE user_id = %s ORDER BY name ASC",
            "assets": "SELECT category, COALESCE(SUM(purchase_price), 0) as total FROM assets WHERE user_id = %s GROUP BY category",
            "financial_goals": "SELECT id, name, target_amount, current_amount, due_date, status, COALESCE((current_amount / NULLIF(target_amount, 0) * 100), 0) as percentage FROM financial_goals WHERE user_id = %s ORDER BY status DESC, due_date ASC"
        }
        
        results = []
        for name, q in queries.items():
            try:
                res = db.execute(q, (user_id,))
                res.fetchall()
                results.append(f"{name}: OK")
            except Exception as e:
                db.primary_conn.rollback()
                return f"Query {name} failed: {e}"
        return "<br>".join(results)
    except Exception as e:
        return f"Outer Error: {e}"


@app.route('/debug_logs')
def debug_logs():
    try:
        db = psycopg2.connect(utils.DATABASE_URL, sslmode='require')
        cursor = db.cursor()
        cursor.execute("SELECT created_at, error FROM error_logs ORDER BY created_at DESC LIMIT 10")
        rows = cursor.fetchall()
        out = ""
        for r in rows:
            out += f"{r[0]}:\n{r[1]}\n\n"
        return f"<pre>{out}</pre>"
    except Exception as e:
        return f"Error: {e}"

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(Exception)
def handle_500(e):
    from werkzeug.exceptions import HTTPException
    import traceback
    err_str = f"Internal Server Error: {str(e)}\n{traceback.format_exc()}"
    print(err_str)
    
    try:
        db = psycopg2.connect(utils.DATABASE_URL, sslmode='require')
        db.autocommit = True
        cursor = db.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS error_logs (id SERIAL PRIMARY KEY, error TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("INSERT INTO error_logs (error) VALUES (%s)", (err_str,))
    except Exception as db_err:
        pass
        
    if isinstance(e, HTTPException):
        return e

    # Instead of full crashing, return a friendly flash or 500
    try:
        return f"Internal Server Error: {str(e)[:200]}... Please check logs.", 500
    except:
        return "Internal Server Error. Please contact admin.", 500
@app.context_processor
def inject_notifications():
    from utils import get_db
    if 'user_id' in session:
        try:
            db = get_db()
            notifs = db.execute('SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 5', (session['user_id'],)).fetchall()
            unread_count = db.execute('SELECT COUNT(*) as c FROM notifications WHERE user_id = ? AND is_read = 0', (session['user_id'],)).fetchone()['c']
            return dict(notifications=notifs, unread_count=unread_count)
        except Exception:
            return dict(notifications=[], unread_count=0)
    return dict(notifications=[], unread_count=0)

if __name__ == '__main__':
    app.run(debug=True)

@app.route('/test_all_queries')
def test_all_queries():
    from flask import session
    try:
        import psycopg2
        import psycopg2.extras
        if 'user_id' not in session:
            return "Not logged in"
        user_id = session['user_id']
        conn = psycopg2.connect(utils.DATABASE_URL, sslmode='require')
        conn.autocommit = True
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        queries = {
            "get_accounts": "SELECT name, initial_balance, current_balance, id FROM accounts WHERE user_id = %s",
            "debts_receivables": "SELECT * FROM debts_receivables WHERE user_id = %s AND status = 'BELUM LUNAS' ORDER BY due_date ASC",
            "recurring_installments": "SELECT * FROM recurring_installments WHERE user_id = %s AND is_active = 1 ORDER BY due_day_of_month ASC",
            "credit_cards": "SELECT * FROM credit_cards WHERE user_id = %s ORDER BY name ASC",
            "assets": "SELECT category, COALESCE(SUM(purchase_price), 0) as total FROM assets WHERE user_id = %s GROUP BY category",
            "financial_goals": "SELECT id, name, target_amount, current_amount, due_date, status, COALESCE((current_amount / NULLIF(target_amount, 0) * 100), 0) as percentage FROM financial_goals WHERE user_id = %s ORDER BY status DESC, due_date ASC",
            "transactions": "SELECT t.id, t.date, t.type, t.amount, t.category, t.description, a.name AS account_name FROM transactions t JOIN accounts a ON t.account_id = a.id WHERE t.user_id = %s AND t.category != 'Transfer' ORDER BY t.date ASC"
        }
        
        results = []
        for name, q in queries.items():
            try:
                cursor.execute(q, (user_id,))
                res = cursor.fetchall()
                results.append(f"{name}: OK (rows: {len(res)})")
            except Exception as e:
                return f"Query {name} failed: {e}"
        return "<br>".join(results)
    except Exception as e:
        return f"Outer Error: {e}"

@app.route('/run_migration')
def run_migration():
    try:
        import psycopg2
        import utils
        results = []

        if utils.DATABASE_URL:
            conn = psycopg2.connect(utils.DATABASE_URL, sslmode='require')
            conn.autocommit = True
            cursor = conn.cursor()
            try:
                cursor.execute("ALTER TABLE accounts ADD COLUMN account_type TEXT DEFAULT 'asset'")
                results.append("Added account_type to primary DB")
            except Exception as e:
                results.append(f"Primary account_type error: {e}")
                
            try:
                cursor.execute("ALTER TABLE accounts ADD COLUMN limit_amount REAL DEFAULT 0")
                results.append("Added limit_amount to primary DB")
            except Exception as e:
                results.append(f"Primary limit_amount error: {e}")

        if utils.REPLICA_DATABASE_URL:
            conn = psycopg2.connect(utils.REPLICA_DATABASE_URL, sslmode='require')
            conn.autocommit = True
            cursor = conn.cursor()
            try:
                cursor.execute("ALTER TABLE accounts ADD COLUMN account_type TEXT DEFAULT 'asset'")
                results.append("Added account_type to replica DB")
            except Exception as e:
                results.append(f"Replica account_type error: {e}")
                
            try:
                cursor.execute("ALTER TABLE accounts ADD COLUMN limit_amount REAL DEFAULT 0")
                results.append("Added limit_amount to replica DB")
            except Exception as e:
                results.append(f"Replica limit_amount error: {e}")
                
        return "<br>".join(results)
    except Exception as e:
        return f"Error: {e}"

@app.route('/dump_logs')
def dump_logs():
    try:
        import psycopg2
        conn = psycopg2.connect(utils.DATABASE_URL, sslmode='require')
        cursor = conn.cursor()
        cursor.execute("SELECT created_at, error FROM error_logs ORDER BY created_at DESC LIMIT 5")
        rows = cursor.fetchall()
        out = ""
        for r in rows:
            out += f"{r[0]}:\n{r[1]}\n\n"
        return f"<pre>{out}</pre>"
    except Exception as e:
        return f"Error connecting: {e}"







