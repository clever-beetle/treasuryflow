from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify
from utils import get_db, login_required
import json

extra_bp = Blueprint('extra', __name__)

@extra_bp.route('/leaderboard')
@login_required
def leaderboard():
    db = get_db()
    users_raw = db.execute('''
        SELECT u.username, a.xp, a.level, a.badges
        FROM user_achievements a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.xp DESC
        LIMIT 50
    ''').fetchall()
    
    users = []
    for u in users_raw:
        udict = dict(u)
        udict['badges_list'] = json.loads(udict['badges'])
        users.append(udict)
        
    return render_template('leaderboard.html', users=users)

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
    goals = db.execute("SELECT name, due_date, target_amount FROM financial_goals WHERE user_id = ? AND status != 'Completed'", (user_id,)).fetchall()
    for g in goals:
        events.append({
            'title': f"Goal Due: {g['name']} (Rp {g['target_amount']:,.0f})",
            'start': g['due_date'],
            'color': '#3b82f6' # Blue
        })
        
    return jsonify(events)
