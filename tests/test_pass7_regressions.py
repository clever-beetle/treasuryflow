import io
import uuid
import csv
from datetime import datetime, timezone, timedelta


def _register_and_login(client, prefix):
    username = f"{prefix}_{uuid.uuid4().hex[:6]}"
    password = "StrongPass123"
    client.post('/register', data={
        'fullname': 'Pass Seven',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)
    return username


def test_spreadsheet_safe_helper():
    from utils import spreadsheet_safe
    assert spreadsheet_safe('=HYPERLINK("http://evil","x")').startswith("'=")
    assert spreadsheet_safe('+62812') == "'+62812"
    assert spreadsheet_safe('-5') == "'-5"
    assert spreadsheet_safe('@SUM(A1)') == "'@SUM(A1)"
    assert spreadsheet_safe('Makan siang') == 'Makan siang'
    assert spreadsheet_safe(15000) == 15000
    assert spreadsheet_safe(None) is None


def test_wib_now_is_utc_plus_7_regardless_of_server_tz():
    from utils import wib_now
    expected = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=7)
    assert abs((wib_now() - expected).total_seconds()) < 5
    assert wib_now().tzinfo is None


def test_exports_neutralize_formula_injection(client):
    username = _register_and_login(client, 'pass7_export')
    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()['id']
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, '[BANK] BCA', 1000000, 1000000, 'asset')", (user_id,))
        db.commit()
        acc_id = db.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,)).fetchone()['id']

    payload = '=HYPERLINK("http://evil.example","klik")'
    client.post('/transactions/add', data={
        'date': '2026-10-01', 'type': 'expense', 'amount': '10.000',
        'category': 'Belanja', 'account_id': acc_id, 'description': payload
    }, follow_redirects=True)

    res_csv = client.get('/transactions/export_csv')
    assert res_csv.status_code == 200
    rows = list(csv.reader(io.StringIO(res_csv.data.decode('utf-8-sig'))))
    descs = [r[3] for r in rows[1:]]
    assert "'" + payload in descs
    assert payload not in descs

    res_xlsx = client.get('/transactions/export_excel')
    assert res_xlsx.status_code == 200
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(res_xlsx.data))
    ws = wb.active
    values = [ws.cell(row=r, column=4).value for r in range(2, ws.max_row + 1)]
    assert "'" + payload in values
    # Must be stored as plain text, never as a formula cell
    for r in range(2, ws.max_row + 1):
        assert ws.cell(row=r, column=4).data_type != 'f'


def test_deleted_income_category_falls_back_to_valid_income_default(client):
    username = _register_and_login(client, 'pass7_cat')
    from utils import get_db, CATEGORIES
    with client.application.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()['id']
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, '[BANK] BCA', 0, 0, 'asset')", (user_id,))
        db.commit()
        acc_id = db.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,)).fetchone()['id']

    client.post('/settings', data={'action': 'add_category', 'type': 'income', 'name': 'Freelance'}, follow_redirects=True)
    client.post('/transactions/add', data={
        'date': '2026-10-01', 'type': 'income', 'amount': '750.000',
        'category': 'Freelance', 'account_id': acc_id, 'description': 'Proyek web'
    }, follow_redirects=True)
    with client.application.app_context():
        db = get_db()
        cat_id = db.execute("SELECT id FROM user_categories WHERE user_id = ? AND name = 'Freelance'", (user_id,)).fetchone()['id']

    client.post('/settings', data={'action': 'delete_category', 'category_id': cat_id}, follow_redirects=True)
    with client.application.app_context():
        db = get_db()
        cat = db.execute("SELECT category FROM transactions WHERE user_id = ? AND description = 'Proyek web'", (user_id,)).fetchone()['category']
    assert cat == 'Lainnya (Pemasukan)'
    assert cat in CATEGORIES['income']


def test_smtp_password_not_hardcoded():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / 'utils.py').read_text(encoding='utf-8')
    assert 'os.environ.get("SMTP_PASSWORD", "")' in src



def test_end_to_end_balance_synchronization_across_all_modules(client):
    """
    Verifies 100% Rupiah-for-Rupiah balance & record synchronization across:
    - Dashboard, Financial Performance, Setup Accounts, and AI Assistant (including NULL account_type & Liability)
    - Buying an Asset with account_id deduction (Cash -> Portfolio keeps Net Worth accurate)
    - Disbursing Debt/Receivable with account_id mutation & Paying Debt -> Deleting/Editing Debt Tx reverses remaining_amount & status
    - Saving to Goal with account_id -> Editing & Deleting Goal Tx updates financial_goals.current_amount & status
    - Auto-Sync Recurring Installment linked to Credit Card Liability -> creates Transfer pair, reduces CC debt, advances tenor, and prevents double-charge
    """
    username = _register_and_login(client, 'pass8_sync')
    from utils import get_db

    with client.application.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()['id']
        # 1. Asset account with explicit 'asset' type (Initial: 10,000,000)
        db.execute(
            "INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, '[BANK] BCA', 10000000, 10000000, 'asset')",
            (user_id,)
        )
        # 2. Legacy wallet with account_type = NULL (Initial: 2,000,000) — must be included everywhere!
        db.execute(
            "INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, 'Dompet Tunai', 2000000, 2000000, NULL)",
            (user_id,)
        )
        # 3. Credit Card liability account with Rp 3,000,000 debt (-3,000,000)
        db.execute(
            "INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type, limit_amount) VALUES (?, '[KARTU KREDIT] BCA Card', -3000000, -3000000, 'liability', 15000000)",
            (user_id,)
        )
        db.commit()
        rows = db.execute("SELECT id, name FROM accounts WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        bca_id, cash_id, cc_id = rows[0]['id'], rows[1]['id'], rows[2]['id']

    # Buy Gold Asset for Rp 1,500,000 deducting from BCA -> BCA: 8,500,000 | Total Cash: 10,500,000 | Portfolio: 1,500,000
    res_asset = client.post('/financial_performance', data={
        'action': 'add_asset',
        'asset_name': 'Logam Mulia Antam',
        'category': 'Emas',
        'purchase_date': '2026-10-10',
        'purchase_price': '1.500.000',
        'quantity': '1',
        'account_id': str(bca_id)
    }, follow_redirects=True)
    assert res_asset.status_code == 200

    # Lend Rp 500,000 (Receivable) from BCA -> BCA: 8,000,000 | Total Cash: 10,000,000
    client.post('/financial_performance', data={
        'action': 'add_debt',
        'type': 'receivable',
        'person_name': 'Rina',
        'total_amount': '500.000',
        'due_date': '2026-12-31',
        'account_id': str(bca_id)
    }, follow_redirects=True)

    # Record a Debt of Rp 1,000,000 (without wallet disbursement) and pay it off in full via BCA -> BCA: 7,000,000 | Total Cash: 9,000,000
    client.post('/financial_performance', data={
        'action': 'add_debt',
        'type': 'debt',
        'person_name': 'Budi',
        'total_amount': '1.000.000',
        'due_date': '2026-12-31'
    }, follow_redirects=True)
    with client.application.app_context():
        db = get_db()
        budi_debt_id = db.execute("SELECT id FROM debts_receivables WHERE user_id = ? AND person_name = 'Budi'", (user_id,)).fetchone()['id']

    client.post('/financial_performance', data={
        'action': 'pay_debt',
        'debt_id': str(budi_debt_id),
        'account_name': str(bca_id),
        'amount_paid': '1.000.000',
        'notes': 'Pelunasan'
    }, follow_redirects=True)

    # Create a Goal (Target Rp 1,000,000) and save Rp 1,000,000 deducting from BCA -> BCA: 6,000,000 | Total Cash: 8,000,000 | Goal: Achieved
    client.post('/financial_performance', data={
        'action': 'add_goal',
        'goal_name': 'Dana Darurat Mini',
        'target_amount': '1.000.000',
        'current_amount': '0',
        'due_date': '2027-01-01'
    }, follow_redirects=True)
    with client.application.app_context():
        db = get_db()
        goal_id = db.execute("SELECT id FROM financial_goals WHERE user_id = ? AND name = 'Dana Darurat Mini'", (user_id,)).fetchone()['id']

    client.post('/financial_performance', data={
        'action': 'saving_goal',
        'goal_id': str(goal_id),
        'saving_amount': '1.000.000',
        'account_id': str(bca_id)
    }, follow_redirects=True)

    # Verify Dashboard, Financial Performance, Setup Accounts, and AI Chat all agree on Total Cash = Rp 8.000.000!
    res_dash = client.get('/dashboard')
    res_perf = client.get('/financial_performance')
    res_setup = client.get('/setup/accounts')
    res_ai = client.post('/api/chat', json={'message': 'berapa saldo saya?'})

    assert b'Rp 8.000.000' in res_dash.data
    assert b'Rp 8.000.000' in res_perf.data
    assert b'Rp 6.000.000' in res_setup.data  # BCA
    assert b'Rp 2.000.000' in res_setup.data  # Dompet Tunai (NULL account_type)
    assert 'Rp 8.000.000' in res_ai.get_json()['reply']

    # Now test bidirectional sync on EDIT & DELETE of Goal and Debt payment transactions!
    with client.application.app_context():
        db = get_db()
        goal_tx_id = db.execute("SELECT id FROM transactions WHERE user_id = ? AND description = 'Tabungan Target: Dana Darurat Mini'", (user_id,)).fetchone()['id']
        debt_tx_id = db.execute("SELECT id FROM transactions WHERE user_id = ? AND category = 'Utang-Piutang' AND description LIKE 'Cicilan debt (Budi)%'", (user_id,)).fetchone()['id']

    # Edit Goal savings tx from 1,000,000 down to 400,000 -> Goal drops to 400,000 ('In Progress') and BCA rises to 6,600,000
    client.post(f'/transactions/edit/{goal_tx_id}', data={
        'amount': '400.000',
        'date': '2026-10-15',
        'type': 'expense',
        'category': 'Investasi',
        'account_id': str(bca_id),
        'description': 'Tabungan Target: Dana Darurat Mini'
    }, follow_redirects=True)

    with client.application.app_context():
        db = get_db()
        g_row = db.execute("SELECT current_amount, status FROM financial_goals WHERE id = ?", (goal_id,)).fetchone()
        assert g_row['current_amount'] == 400000
        assert g_row['status'] == 'In Progress'
        bca_bal = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()['current_balance']
        assert bca_bal == 6600000

    # Delete Goal savings tx -> Goal drops to 0 and BCA rises back to 7,000,000
    client.post(f'/transactions/delete/{goal_tx_id}', follow_redirects=True)
    # Delete Budi Debt payment tx -> Budi debt returns to 1,000,000 ('BELUM LUNAS') and BCA rises back to 8,000,000
    client.post(f'/transactions/delete/{debt_tx_id}', follow_redirects=True)

    with client.application.app_context():
        db = get_db()
        g_row2 = db.execute("SELECT current_amount, status FROM financial_goals WHERE id = ?", (goal_id,)).fetchone()
        assert g_row2['current_amount'] == 0
        d_row2 = db.execute("SELECT remaining_amount, status FROM debts_receivables WHERE id = ?", (budi_debt_id,)).fetchone()
        assert d_row2['remaining_amount'] == 1000000
        assert d_row2['status'] == 'BELUM LUNAS'
        bca_bal2 = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()['current_balance']
        assert bca_bal2 == 8000000

    # Finally test Auto-Sync Recurring Installment linked to Credit Card (cc_id)
    with client.application.app_context():
        db = get_db()
        db.execute("DELETE FROM feature_flags WHERE name = 'auto_sync'")
        db.execute("INSERT INTO feature_flags (name, is_active) VALUES ('auto_sync', 1)")
        db.execute('''
            INSERT INTO recurring_installments (user_id, name, amount_per_cycle, due_day_of_month, is_temporary_tenor, total_tenor, current_tenor, is_active, linked_account_id)
            VALUES (?, 'Cicilan Kamera CC', 500000, 1, 1, 1, 1, 1, ?)
        ''', (user_id, cc_id))
        db.commit()

    # First dashboard load triggers auto_sync -> BCA: 7,500,000 | CC debt: -2,500,000 | installment completed (is_active=0)
    client.get('/dashboard')
    # Second dashboard load must NOT double-charge
    client.get('/dashboard')

    with client.application.app_context():
        db = get_db()
        bca_final = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()['current_balance']
        cc_final = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (cc_id,)).fetchone()['current_balance']
        inst_row = db.execute("SELECT is_active, current_tenor FROM recurring_installments WHERE user_id = ? AND name = 'Cicilan Kamera CC'", (user_id,)).fetchone()
        assert bca_final == 7500000
        assert cc_final == -2500000
        assert inst_row['is_active'] in (0, False)
        # Clean up global auto_sync flag for subsequent tests
        db.execute("UPDATE feature_flags SET is_active = 0 WHERE name = 'auto_sync'")
        db.commit()


def test_reset_password_flow_indonesian_and_wib_expiry(client):
    username = _register_and_login(client, 'pass8_pw')
    client.get('/logout', follow_redirects=True)

    res_forgot = client.post('/forgot_password', data={'username': f"{username}@test.com"}, follow_redirects=True)
    assert res_forgot.status_code == 200
    assert b'Tautan reset password sedang dikirim' in res_forgot.data

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        token = db.execute("SELECT reset_token FROM users WHERE username = ?", (username,)).fetchone()['reset_token']
        assert token

    res_reset = client.post(f'/reset_password/{token}', data={
        'password': 'NewStrongPassword99',
        'confirm_password': 'NewStrongPassword99'
    }, follow_redirects=True)
    assert res_reset.status_code == 200
    assert b'Password Anda berhasil direset' in res_reset.data

    res_login = client.post('/login', data={'username': username, 'password': 'NewStrongPassword99'}, follow_redirects=True)
    assert res_login.status_code == 200
    assert '/dashboard' in res_login.request.path
