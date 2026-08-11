import os
from flask import Blueprint, render_template, request, session, abort
from utils import get_db, admin_required

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()
    users_count = db.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    transactions_count = db.execute('SELECT COUNT(*) as count FROM transactions').fetchone()['count']
    
    return f"""
    <h1>God Mode - Admin Dashboard</h1>
    <p>Total Users: {users_count}</p>
    <p>Total Transactions: {transactions_count}</p>
    <a href='/dashboard'>Back to Dashboard</a>
    """

@admin_bp.route('/dev-console', methods=['GET', 'POST'])
def dev_console():
    try:
        # Secret Key Authentication
        provided_key = request.args.get('key')
        dev_secret_key = os.environ.get('DEV_SECRET_KEY')
        
        # Require DEV_SECRET_KEY to be set in environment and match provided key
        if not dev_secret_key or provided_key != dev_secret_key:
            abort(403)
            
        db = get_db()
        
        # Get all tables
        tables = []
        if os.environ.get('DATABASE_URL'):
            # PostgreSQL
            cursor = db.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
            tables = [row['table_name'] for row in cursor.fetchall()]
        else:
            # SQLite
            cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row['name'] for row in cursor.fetchall()]
            
        selected_table = request.args.get('view_table')
        table_data = None
        query_result = None
        error = None
        success = None
        
        if request.method == 'POST':
            query = request.form.get('query', '').strip()
            if query:
                try:
                    cursor = db.execute(query)
                    if query.upper().startswith('SELECT'):
                        query_result = [dict(row) for row in cursor.fetchall()]
                    else:
                        db.commit()
                        success = "Query executed successfully."
                except Exception as e:
                    error = str(e)
        elif selected_table in tables:
            try:
                # Prevent SQL injection by verifying selected_table is in tables list
                cursor = db.execute(f"SELECT * FROM {selected_table} LIMIT 100")
                table_data = [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                error = str(e)

        return render_template(
            'dev_console.html', 
            key=provided_key,
            tables=tables, 
            selected_table=selected_table,
            table_data=table_data,
            query_result=query_result,
            error=error,
            success=success
        )
    except Exception as e:
        import traceback
        err_msg = str(e) + "\\n" + traceback.format_exc()
        return render_template(
            'dev_console.html', 
            key=request.args.get('key'),
            tables=[], 
            selected_table=None,
            table_data=None,
            query_result=None,
            error=err_msg,
            success=None
        )
