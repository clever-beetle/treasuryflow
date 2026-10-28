from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify
from utils import get_db, login_required

extra_bp = Blueprint('extra', __name__)

@extra_bp.route('/tools')
@login_required
def tools():
    return render_template('tools.html')

@extra_bp.route('/kiosk')
@login_required
def kiosk():
    return render_template('kiosk.html')

@extra_bp.route('/notifications/read', methods=['POST'])
@login_required
def read_notifications():
    db = get_db()
    db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (session['user_id'],))
    db.commit()
    return jsonify({'status': 'success'})

@extra_bp.route('/calendar')
@login_required
def calendar_view():
    return render_template('calendar.html')

@extra_bp.route('/api/calendar_events')
@login_required
def api_calendar_events():
    db = get_db()
    user_id = session['user_id']
    events = []
    
    # Add Financial Goals due dates
    goals = db.execute("SELECT name, due_date, target_amount FROM financial_goals WHERE user_id = ? AND status NOT IN ('Achieved', 'Completed')", (user_id,)).fetchall()
    for g in goals:
        if g['due_date']:
            target_val = float(g['target_amount'] or 0)
            events.append({
                'title': f"Goal: {g['name']} (Rp {target_val:,.0f})",
                'start': str(g['due_date'])[:10],
                'color': '#3b82f6' # Blue
            })
            
    # Add Active Debts / Receivables due dates
    debts = db.execute("SELECT person_name, type, due_date, remaining_amount FROM debts_receivables WHERE user_id = ? AND status = 'BELUM LUNAS'", (user_id,)).fetchall()
    for d in debts:
        if d['due_date']:
            rem = float(d['remaining_amount'] or 0)
            label = "Utang" if d['type'] == 'debt' else "Piutang"
            color = '#ef4444' if d['type'] == 'debt' else '#10b981' # Red for debt, green for receivable
            events.append({
                'title': f"{label}: {d['person_name']} (Rp {rem:,.0f})",
                'start': str(d['due_date'])[:10],
                'color': color
            })
            
    # Add Active Recurring Installments / Subscriptions
    import calendar as cal_mod
    from datetime import datetime, timedelta
    today = (datetime.now() + timedelta(hours=7)).date()
    months_to_check = [
        today,
        (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    ]
    installments = db.execute("SELECT name, amount_per_cycle, due_day_of_month FROM recurring_installments WHERE user_id = ? AND is_active = 1", (user_id,)).fetchall()
    for inst in installments:
        try:
            amt = float(inst['amount_per_cycle'] or 0)
        except (ValueError, TypeError):
            amt = 0.0
        try:
            due_day = int(inst['due_day_of_month'] or 1)
        except (ValueError, TypeError):
            due_day = 1
        for m_date in months_to_check:
            max_day = cal_mod.monthrange(m_date.year, m_date.month)[1]
            actual_day = min(max(1, due_day), max_day)
            date_str = f"{m_date.year:04d}-{m_date.month:02d}-{actual_day:02d}"
            events.append({
                'title': f"Cicilan/Tagihan: {inst['name']} (Rp {amt:,.0f})",
                'start': date_str,
                'color': '#8b5cf6' # Purple
            })
            
    return jsonify(events)
