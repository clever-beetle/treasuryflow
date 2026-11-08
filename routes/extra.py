import calendar as cal_mod
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, session, jsonify, url_for
from utils import get_db, login_required, wib_now, format_rupiah

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


def _months_in_window(start_str: str, end_str: str, today: date) -> list:
    """Return (year, month) tuples covering the requested FullCalendar window or default 4-month span."""
    start_d = None
    end_d = None
    if start_str:
        try:
            start_d = datetime.strptime(start_str[:10], '%Y-%m-%d').date()
        except ValueError:
            start_d = None
    if end_str:
        try:
            end_d = datetime.strptime(end_str[:10], '%Y-%m-%d').date()
        except ValueError:
            end_d = None

    if not start_d or not end_d or end_d < start_d:
        prev_m = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        end_m = today.replace(day=1)
        for _ in range(3):
            end_m = (end_m + timedelta(days=32)).replace(day=1)
        start_d, end_d = prev_m, end_m

    months = []
    cur = date(start_d.year, start_d.month, 1)
    limit = date(end_d.year, end_d.month, 1)
    guard = 0
    while cur <= limit and guard < 24:
        months.append((cur.year, cur.month))
        cur = (cur + timedelta(days=32)).replace(day=1)
        guard += 1
    return months


@extra_bp.route('/api/calendar_events')
@login_required
def api_calendar_events():
    db = get_db()
    user_id = session['user_id']
    events = []

    today = wib_now().date()
    months_window = _months_in_window(
        request.args.get('start', ''),
        request.args.get('end', ''),
        today,
    )
    perf_url = url_for('performance.financial_performance')
    accounts_url = url_for('settings.setup_account')

    # 1. Financial Goals due dates
    goals = db.execute(
        "SELECT name, due_date, target_amount, current_amount FROM financial_goals WHERE user_id = ? AND status NOT IN ('Achieved', 'Completed')",
        (user_id,)
    ).fetchall()
    for g_row in goals:
        if g_row['due_date']:
            target_val = float(g_row['target_amount'] or 0)
            fmt_val = format_rupiah(target_val)
            d_str = str(g_row['due_date'])[:10]
            events.append({
                'title': f"Target: {g_row['name']} ({fmt_val})",
                'start': d_str,
                'allDay': True,
                'backgroundColor': '#2563eb',
                'borderColor': '#2563eb',
                'textColor': '#ffffff',
                'extendedProps': {
                    'kind': 'goal',
                    'badge': 'Target Tabungan',
                    'item_name': g_row['name'],
                    'amount_formatted': fmt_val,
                    'raw_amount': target_val,
                    'action_url': f"{perf_url}?tab=goals",
                    'action_label': 'Buka Target Tabungan',
                }
            })

    # 2. Active Debts / Receivables due dates
    debts = db.execute(
        "SELECT person_name, type, due_date, remaining_amount, notes FROM debts_receivables WHERE user_id = ? AND status = 'BELUM LUNAS'",
        (user_id,)
    ).fetchall()
    for d_row in debts:
        if d_row['due_date']:
            rem = float(d_row['remaining_amount'] or 0)
            fmt_val = format_rupiah(rem)
            is_debt = d_row['type'] == 'debt'
            label = "Utang" if is_debt else "Piutang"
            color = '#e11d48' if is_debt else '#059669'
            d_str = str(d_row['due_date'])[:10]
            events.append({
                'title': f"{label}: {d_row['person_name']} ({fmt_val})",
                'start': d_str,
                'allDay': True,
                'backgroundColor': color,
                'borderColor': color,
                'textColor': '#ffffff',
                'extendedProps': {
                    'kind': 'debt' if is_debt else 'receivable',
                    'badge': 'Jatuh Tempo Utang' if is_debt else 'Tagihan Piutang',
                    'item_name': d_row['person_name'],
                    'amount_formatted': fmt_val,
                    'raw_amount': rem,
                    'notes': d_row['notes'] or '',
                    'action_url': f"{perf_url}?tab=debts",
                    'action_label': 'Kelola Utang & Piutang',
                }
            })

    # 3. Active Recurring Installments / Subscriptions across requested months
    installments = db.execute(
        "SELECT name, amount_per_cycle, due_day_of_month FROM recurring_installments WHERE user_id = ? AND is_active = 1",
        (user_id,)
    ).fetchall()
    for inst in installments:
        try:
            amt = float(inst['amount_per_cycle'] or 0)
        except (ValueError, TypeError):
            amt = 0.0
        try:
            due_day = int(inst['due_day_of_month'] or 1)
        except (ValueError, TypeError):
            due_day = 1
        fmt_val = format_rupiah(amt)
        for yr, mo in months_window:
            max_day = cal_mod.monthrange(yr, mo)[1]
            actual_day = min(max(1, due_day), max_day)
            date_str = f"{yr:04d}-{mo:02d}-{actual_day:02d}"
            events.append({
                'title': f"Cicilan: {inst['name']} ({fmt_val})",
                'start': date_str,
                'allDay': True,
                'backgroundColor': '#7c3aed',
                'borderColor': '#7c3aed',
                'textColor': '#ffffff',
                'extendedProps': {
                    'kind': 'installment',
                    'badge': 'Tagihan & Cicilan Rutin',
                    'item_name': inst['name'],
                    'amount_formatted': fmt_val,
                    'raw_amount': amt,
                    'action_url': f"{perf_url}?tab=debts",
                    'action_label': 'Kelola Cicilan Rutin',
                }
            })

    # 4. Liability Accounts (Credit Card / PayLater / Pinjol) Monthly Billing Due Days
    try:
        liability_accs = db.execute(
            "SELECT name, current_balance, billing_due_day FROM accounts WHERE user_id = ? AND account_type = 'liability' AND billing_due_day IS NOT NULL",
            (user_id,)
        ).fetchall()
    except Exception:
        liability_accs = []

    for acc in liability_accs:
        try:
            due_day = int(acc['billing_due_day'] or 0)
        except (ValueError, TypeError):
            due_day = 0
        if due_day < 1 or due_day > 31:
            continue
        clean_name = acc['name'].split('] ')[-1] if '] ' in acc['name'] else acc['name']
        used_amt = abs(float(acc['current_balance'] or 0))
        fmt_val = format_rupiah(used_amt)
        for yr, mo in months_window:
            max_day = cal_mod.monthrange(yr, mo)[1]
            actual_day = min(due_day, max_day)
            date_str = f"{yr:04d}-{mo:02d}-{actual_day:02d}"
            events.append({
                'title': f"Tagihan CC: {clean_name} ({fmt_val})",
                'start': date_str,
                'allDay': True,
                'backgroundColor': '#d97706',
                'borderColor': '#d97706',
                'textColor': '#ffffff',
                'extendedProps': {
                    'kind': 'credit_card',
                    'badge': 'Jatuh Tempo Kartu Kredit / Paylater',
                    'item_name': clean_name,
                    'amount_formatted': fmt_val,
                    'raw_amount': used_amt,
                    'action_url': accounts_url,
                    'action_label': 'Kelola Akun & Dompet',
                }
            })

    return jsonify(events)
