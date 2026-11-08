import uuid
from routes.auth_biometric import _decode_stored_public_key, _get_rp_id
from routes.dashboard import recalculate_account_balances
from utils import get_db
from version import APP_VERSION


def _register_and_login(client):
    uname = f"p9_{uuid.uuid4().hex[:8]}"
    pw = "Pass9Strong!"
    client.post('/register', data={
        'fullname': 'Pass Nine Tester',
        'username': uname,
        'email': f"{uname}@example.com",
        'password': pw,
        'confirm_password': pw,
    }, follow_redirects=True)
    client.post('/login', data={'username': uname, 'password': pw}, follow_redirects=True)
    return uname, pw


def test_version_system_and_audit_endpoint(client):
    res = client.get('/api/version')
    assert res.status_code == 200
    payload = res.get_json()
    assert payload['version'] == APP_VERSION
    assert payload['build']
    assert payload['release_date']

    _register_and_login(client)
    dash = client.get('/dashboard')
    assert dash.status_code == 200
    assert f"v{APP_VERSION}".encode() in dash.data

    settings_res = client.get('/settings')
    assert settings_res.status_code == 200
    assert f"v{APP_VERSION}".encode() in settings_res.data


def test_webauthn_postgres_bytea_decoding_and_persistent_settings(client):
    # Simulated 77-byte COSE_Key CBOR map starting with 0xa5 (non-ASCII CBOR map header)
    sample_cose_key = bytes.fromhex(
        "a5010203262001215820" + ("11" * 32) + "225820" + ("22" * 32)
    )
    hex_str = sample_cose_key.hex()

    # 1. SQLite TEXT hex string
    assert _decode_stored_public_key(hex_str) == sample_cose_key
    # 2. Legacy PostgreSQL BYTEA memoryview containing UTF-8 ASCII hex characters (root cause of prod failure)
    pg_legacy_memview = memoryview(hex_str.encode('ascii'))
    assert _decode_stored_public_key(pg_legacy_memview) == sample_cose_key
    # 3. PostgreSQL \x-prefixed hex representation
    assert _decode_stored_public_key("\\x" + hex_str) == sample_cose_key
    assert _decode_stored_public_key(b"\\x" + hex_str.encode('ascii')) == sample_cose_key
    # 4. Clean binary BYTEA memoryview
    assert _decode_stored_public_key(memoryview(sample_cose_key)) == sample_cose_key

    # RP ID normalization across www. and apex domain
    with client.application.test_request_context('https://www.treasuryflow.web.id/api/webauthn/login/generate'):
        assert _get_rp_id() == 'treasuryflow.web.id'
    with client.application.test_request_context('http://127.0.0.1:5000/api/webauthn/login/generate'):
        assert _get_rp_id() == 'localhost'

    # Persistent server-side Passkey status & deletion in Settings
    uname, _ = _register_and_login(client)
    with client.application.app_context():
        db = get_db()
        uid = db.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone()['id']
        db.execute(
            "INSERT INTO webauthn_credentials (user_id, credential_id, public_key, sign_count) VALUES (?, ?, ?, ?)",
            (uid, "abcdef1234567890abcdef12", sample_cose_key, 4)
        )
        db.commit()
        pk_id = db.execute("SELECT id FROM webauthn_credentials WHERE user_id = ?", (uid,)).fetchone()['id']

    set_page = client.get('/settings?tab=integrations')
    assert set_page.status_code == 200
    assert b'1 Terdaftar di Server' in set_page.data
    assert b'Digunakan 4 kali' in set_page.data

    del_res = client.post('/settings', data={
        'action': 'delete_passkey',
        'passkey_id': str(pk_id),
    }, follow_redirects=True)
    assert del_res.status_code == 200
    assert b'Belum Terdaftar' in del_res.data
    with client.application.app_context():
        db = get_db()
        rem = db.execute("SELECT COUNT(*) AS c FROM webauthn_credentials WHERE user_id = ?", (uid,)).fetchone()['c']
        assert rem == 0


def test_add_transaction_strict_category_separation_and_tabs(client):
    _register_and_login(client)
    client.post('/settings', data={'action': 'add_category', 'type': 'income', 'name': 'Dividen Saham'}, follow_redirects=True)
    client.post('/settings', data={'action': 'add_category', 'type': 'expense', 'name': 'Langganan Cloud'}, follow_redirects=True)

    res = client.get('/transactions/add')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    # Responsive 3-tab segmented grid present
    assert 'grid-cols-3' in html
    assert 'shadcn-select-portal' in html

    # Initial mode is expense: <select id="categorySelect"> must NOT contain income options in its initial DOM
    select_part = html.split('id="categorySelect"')[1].split('</select>')[0]
    assert 'Makanan &amp; Minuman' in select_part or 'Makanan & Minuman' in select_part
    assert 'Langganan Cloud' in select_part
    assert '<option value="Gaji">' not in select_part
    assert 'Dividen Saham' not in select_part

    # Both separated JS arrays must be present for dynamic switching
    assert 'Dividen Saham' in html
    assert 'INCOME_CATEGORIES' in html
    assert 'EXPENSE_CATEGORIES' in html


def test_calendar_events_rupiah_format_window_and_cc_due_day(client):
    uname, _ = _register_and_login(client)
    with client.application.app_context():
        db = get_db()
        uid = db.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone()['id']
        db.execute(
            "INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type, limit_amount, billing_due_day) VALUES (?, ?, ?, ?, 'liability', ?, ?)",
            (uid, '[KARTU KREDIT] BCA Card', -1500000, -1500000, 10000000, 20)
        )
        db.execute(
            "INSERT INTO recurring_installments (user_id, name, amount_per_cycle, due_day_of_month, is_active) VALUES (?, ?, ?, ?, 1)",
            (uid, 'Internet Fiber', 450000, 15)
        )
        db.execute(
            "INSERT INTO financial_goals (user_id, name, target_amount, current_amount, due_date, status) VALUES (?, ?, ?, ?, ?, 'In Progress')",
            (uid, 'Dana Darurat', 12000000, 2000000, '2027-03-25')
        )
        db.commit()

    ev_res = client.get('/api/calendar_events?start=2027-03-01&end=2027-03-31')
    assert ev_res.status_code == 200
    events = ev_res.get_json()
    titles = [e['title'] for e in events]

    # Check Indonesian dot formatting (Rp 1.500.000, Rp 450.000, Rp 12.000.000) and future window support
    assert any('BCA Card (Rp 1.500.000)' in t for t in titles)
    inst_ev = next((e for e in events if 'Internet Fiber (Rp 450.000)' in e['title'] and e['start'] == '2027-03-15'), None)
    assert inst_ev is not None
    assert inst_ev['extendedProps']['action_url'].endswith('?tab=liabilities')
    assert any('Dana Darurat (Rp 12.000.000)' in t for t in titles)

    # Verify both ?tab=liabilities and legacy ?tab=debts open the liabilities tab cleanly
    perf_liab = client.get('/financial_performance?tab=liabilities')
    assert perf_liab.status_code == 200
    assert b"activeTab: 'liabilities'" in perf_liab.data
    perf_debts_alias = client.get('/financial_performance?tab=debts')
    assert perf_debts_alias.status_code == 200
    assert b"activeTab: 'liabilities'" in perf_debts_alias.data

    # Check /transactions/?view=calendar Indonesian day & month headers
    cal_tx = client.get('/transactions/?view=calendar&cal_year=2026&cal_month=8')
    assert cal_tx.status_code == 200
    cal_html = cal_tx.data.decode('utf-8')
    assert 'Agustus 2026' in cal_html
    for day_lbl in ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']:
        assert day_lbl in cal_html


def test_dropdown_never_binds_resize_to_close_and_transfer_edit_mode(client):
    uname, _ = _register_and_login(client)
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'BANK',
        'name_detail': 'BCA',
        'initial_balance': '2.000.000',
    }, follow_redirects=True)
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'E-WALLET',
        'name_detail': 'GoPay',
        'initial_balance': '500.000',
    }, follow_redirects=True)

    with client.application.app_context():
        db = get_db()
        uid = db.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone()['id']
        accs = db.execute("SELECT id, name FROM accounts WHERE user_id = ? ORDER BY id ASC", (uid,)).fetchall()
        bca_id, gopay_id = accs[0]['id'], accs[1]['id']

    # Record a transfer between BCA and GoPay
    tf_res = client.post('/transactions/add', data={
        'type': 'transfer',
        'date': '2026-11-08',
        'amount': '250.000',
        'account_id': str(bca_id),
        'to_account_id': str(gopay_id),
        'description': 'Topup GoPay',
    }, follow_redirects=True)
    assert tf_res.status_code == 200

    with client.application.app_context():
        db = get_db()
        tf_leg = db.execute(
            "SELECT id FROM transactions WHERE user_id = ? AND category = 'Transfer' ORDER BY id ASC LIMIT 1",
            (uid,),
        ).fetchone()
        assert tf_leg is not None
        tf_id = tf_leg['id']

    # Verify /transactions/add renders the mobile-safe resize repositioner (not closePortal on resize)
    add_page = client.get('/transactions/add')
    add_html = add_page.data.decode('utf-8')
    assert "window.addEventListener('resize', positionPortal)" in add_html
    assert "window.addEventListener('resize', closePortal)" not in add_html
    assert "syncSplitBillRequirements" in add_html

    # Verify /transactions/edit/<transfer_id> locks Transfer mode cleanly and syncs both legs on update
    edit_get = client.get(f'/transactions/edit/{tf_id}')
    assert edit_get.status_code == 200
    assert b'Transaksi Transfer Antar Akun' in edit_get.data

    edit_post = client.post(f'/transactions/edit/{tf_id}', data={
        'type': 'expense',
        'date': '2026-11-08',
        'amount': '300.000',
        'account_id': str(bca_id),
        'description': 'Topup GoPay Updated',
    }, follow_redirects=True)
    assert edit_post.status_code == 200

    with client.application.app_context():
        db = get_db()
        bca_bal = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()['current_balance']
        gopay_bal = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (gopay_id,)).fetchone()['current_balance']
        assert bca_bal == 1700000
        assert gopay_bal == 800000


def test_smart_balance_recalculation_skips_clean_rows(client):
    uname, _ = _register_and_login(client)
    with client.application.app_context():
        db = get_db()
        uid = db.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone()['id']
        db.execute(
            "INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, 'BCA', 1000000, 0, 'asset')",
            (uid,)
        )
        db.commit()

        # First call heals the drifted current_balance (0 -> 1,000,000)
        recalculate_account_balances(db, uid)
        bal = db.execute("SELECT current_balance FROM accounts WHERE user_id = ? AND name = 'BCA'", (uid,)).fetchone()['current_balance']
        assert bal == 1000000

        # Subsequent call when already synchronized updates 0 rows
        cur = db.execute('''
            UPDATE accounts
            SET current_balance = COALESCE(initial_balance, 0)
            WHERE user_id = ? AND ABS(COALESCE(current_balance, 0) - COALESCE(initial_balance, 0)) > 0.009
        ''', (uid,))
        assert cur.rowcount == 0


def test_category_deduplication_ordering_and_aesthetic_version_ui(client):
    import json
    import re
    from utils import CATEGORIES

    uname, _ = _register_and_login(client)
    with client.application.app_context():
        db = get_db()
        uid = db.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone()['id']
        # Simulate legacy seeded user_categories containing ALL built-in defaults + bare 'Lainnya' + custom
        for c in CATEGORIES['income']:
            db.execute("INSERT INTO user_categories (user_id, type, name) VALUES (?, 'income', ?)", (uid, c))
        for c in CATEGORIES['expense']:
            db.execute("INSERT INTO user_categories (user_id, type, name) VALUES (?, 'expense', ?)", (uid, c))
        db.execute("INSERT INTO user_categories (user_id, type, name) VALUES (?, 'income', 'Lainnya')", (uid,))
        db.execute("INSERT INTO user_categories (user_id, type, name) VALUES (?, 'expense', 'Lainnya')", (uid,))
        db.execute("INSERT INTO user_categories (user_id, type, name) VALUES (?, 'income', 'Bonus Tahunan')", (uid,))
        db.execute("INSERT INTO user_categories (user_id, type, name) VALUES (?, 'expense', 'Kopi & Camilan')", (uid,))
        db.commit()

    # Check /transactions/add deduplicates all built-ins + bare 'Lainnya' and places Lainnya LAST
    add_res = client.get('/transactions/add')
    assert add_res.status_code == 200
    html = add_res.data.decode('utf-8')

    inc_m = re.search(r'const INCOME_CATEGORIES = (\[.*?\]);', html)
    exp_m = re.search(r'const EXPENSE_CATEGORIES = (\[.*?\]);', html)
    assert inc_m and exp_m
    inc_list = json.loads(inc_m.group(1))
    exp_list = json.loads(exp_m.group(1))

    assert len(inc_list) == len(CATEGORIES['income']) + 1
    assert len(exp_list) == len(CATEGORIES['expense']) + 1
    assert inc_list.count('Lainnya (Pemasukan)') == 1
    assert exp_list.count('Lainnya (Pengeluaran)') == 1
    assert 'Lainnya' not in inc_list
    assert 'Lainnya' not in exp_list
    assert inc_list[-1] == 'Lainnya (Pemasukan)'
    assert exp_list[-1] == 'Lainnya (Pengeluaran)'
    assert inc_list[:-1] == sorted(inc_list[:-1], key=str.casefold)
    assert exp_list[:-1] == sorted(exp_list[:-1], key=str.casefold)
    assert 'Bonus Tahunan' in inc_list[:-1]
    assert 'Kopi & Camilan' in exp_list[:-1]

    # Settings rejects adding bare 'Lainnya' and hides legacy default clones from custom table
    rej = client.post('/settings', data={'action': 'add_category', 'type': 'expense', 'name': 'Lainnya'}, follow_redirects=True)
    assert b'bawaan sistem' in rej.data

    set_res = client.get('/settings?tab=categories')
    set_html = set_res.data.decode('utf-8')
    assert 'Rilis Terbaru' in set_html
    assert 'Kategori Bawaan Sistem' in set_html
    assert f"({client.get('/api/version').get_json()['build']})" not in set_html
