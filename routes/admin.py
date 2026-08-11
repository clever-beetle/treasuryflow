from flask import Blueprint, render_template, request, session
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
