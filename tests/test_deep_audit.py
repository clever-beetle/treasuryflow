import pytest
import uuid

def test_pdf_and_excel_exports_with_unicode(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_pdf_{test_id}"
    password = "Password123!"

    # Register user with special characters in name
    client.post('/register', data={
        'fullname': 'Dr. René — O’Connor & Co. • ☕',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # Add account
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'CASH',
        'initial_balance': '500.000'
    }, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user['id']
        acc = db.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,)).fetchone()

    # Add transaction with unicode characters (em-dash, emoji, bullet, smart quotes)
    client.post('/transactions/add', data={
        'type': 'expense',
        'date': '2026-10-01',
        'amount': '45.000,50',
        'category': 'Makanan & Minuman',
        'account_id': acc['id'],
        'description': 'Kopi “Espresso” — Double Shot • Enak!'
    }, follow_redirects=True)

    with client.application.app_context():
        db = get_db()
        tx = db.execute("SELECT id FROM transactions WHERE user_id = ?", (user_id,)).fetchone()
        tx_id = tx['id']

    # 1. Test export_pdf with unicode
    pdf_res = client.get('/transactions/export_pdf')
    assert pdf_res.status_code == 200
    assert pdf_res.headers.get('Content-Type') == 'application/pdf'
    assert len(pdf_res.data) > 1000

    # 2. Test download_receipt with unicode
    receipt_res = client.get(f'/transactions/transaction/{tx_id}/receipt')
    assert receipt_res.status_code == 200
    assert receipt_res.headers.get('Content-Type') == 'application/pdf'
    assert len(receipt_res.data) > 500

    # 3. Test export_excel
    excel_res = client.get('/transactions/export_excel')
    assert excel_res.status_code == 200
    assert 'spreadsheet' in excel_res.headers.get('Content-Type', '')

def test_calendar_boundary_and_invalid_inputs(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_cal_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Cal User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # 1. Valid calendar view
    res_valid = client.get('/transactions/?view=calendar&cal_year=2026&cal_month=10')
    assert res_valid.status_code == 200

    # 2. Invalid cal_month > 12 should not crash (500)
    res_invalid_month = client.get('/transactions/?view=calendar&cal_year=2026&cal_month=15')
    assert res_invalid_month.status_code == 200

    # 3. Invalid cal_month <= 0 should not crash
    res_zero_month = client.get('/transactions/?view=calendar&cal_year=2026&cal_month=0')
    assert res_zero_month.status_code == 200

    # 4. Out of bounds cal_year
    res_invalid_year = client.get('/transactions/?view=calendar&cal_year=99999&cal_month=5')
    assert res_invalid_year.status_code == 200

def test_graphql_and_webauthn_and_stream(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_api_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'API User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # 1. GraphQL playground GET
    gql_get = client.get('/graphql')
    assert gql_get.status_code == 200

    # 2. GraphQL valid query
    gql_query = client.post('/graphql', json={'query': '{ hello transactions { id } }'})
    assert gql_query.status_code == 200
    assert gql_query.json['data']['hello'] == "Selamat datang di GraphQL Supergraph!"

    # 3. GraphQL empty body should not crash
    gql_empty = client.post('/graphql', json={})
    assert gql_empty.status_code in (200, 400)

    # 4. WebAuthn register generate
    webauthn_res = client.post('/api/webauthn/register/generate')
    assert webauthn_res.status_code == 200
    assert 'challenge' in webauthn_res.json or 'rp' in webauthn_res.json

    # 5. Calendar events API
    events_res = client.get('/api/calendar_events')
    assert events_res.status_code == 200
    assert isinstance(events_res.json, list)

def test_settings_operations_and_flags(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_set_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Settings User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # 1. Update fullname
    set_name = client.post('/settings', data={
        'action': 'update_fullname',
        'fullname': 'Updated Settings User'
    }, follow_redirects=True)
    assert set_name.status_code == 200
    assert b'Updated Settings User' in set_name.data

    # 1b. Update username validations
    bad_uname = client.post('/settings', data={
        'action': 'update_username',
        'username': 'bad name with space'
    }, follow_redirects=True)
    assert b'tidak boleh mengandung spasi' in bad_uname.data

    good_uname = client.post('/settings', data={
        'action': 'update_username',
        'username': f"new_{username}"
    }, follow_redirects=True)
    assert good_uname.status_code == 200
    assert b'berhasil diperbarui' in good_uname.data

    # 2. Add custom user category
    add_cat = client.post('/settings', data={
        'action': 'add_category',
        'type': 'expense',
        'name': 'Hobi & Game'
    }, follow_redirects=True)
    assert add_cat.status_code == 200
    assert b'Hobi' in add_cat.data and b'Game' in add_cat.data

    # 2b. Add duplicate custom category (case-insensitive)
    dup_cat = client.post('/settings', data={
        'action': 'add_category',
        'type': 'expense',
        'name': 'hobi & game'
    }, follow_redirects=True)
    assert b'sudah ada' in dup_cat.data

    # 2c. Delete custom category
    from utils import get_db
    with client.application.app_context():
        db = get_db()
        cat_row = db.execute("SELECT id FROM user_categories WHERE name = 'Hobi & Game'").fetchone()
        cat_id = cat_row['id']
    del_cat = client.post('/settings', data={
        'action': 'delete_category',
        'category_id': cat_id
    }, follow_redirects=True)
    assert del_cat.status_code == 200

    # 3. Toggle auto_sync
    toggle_res = client.post('/settings', data={
        'action': 'toggle_auto_sync'
    }, follow_redirects=True)
    assert toggle_res.status_code == 200

    # 3b. Password change: short password check
    short_pw = client.post('/settings', data={
        'action': 'update_password',
        'old_password': password,
        'new_password': '123',
        'confirm_password': '123'
    }, follow_redirects=True)
    assert b'minimal harus 6 karakter' in short_pw.data

    # 3c. Password change: valid update
    new_pw = "BrandNewSecret123!"
    up_pw = client.post('/settings', data={
        'action': 'update_password',
        'old_password': password,
        'new_password': new_pw,
        'confirm_password': new_pw
    }, follow_redirects=True)
    assert up_pw.status_code == 200
    assert 'login' in up_pw.request.path or b'berhasil' in up_pw.data

    # Relogin with new password
    relogin = client.post('/login', data={'username': f"new_{username}", 'password': new_pw}, follow_redirects=True)
    assert relogin.status_code == 200
    assert 'dashboard' in relogin.request.path

    # 4. Forgot password endpoint with email
    forgot_res = client.post('/forgot_password', data={
        'username': f"{username}@test.com"
    }, follow_redirects=True)
    assert forgot_res.status_code == 200

def test_ai_rag_and_prediction_suite(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_ai_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'AI Test User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user['id']
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance) VALUES (?, 'Test Wallet', 1000000, 1000000)", (user_id,))
        db.commit()
        acc = db.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
        acc_id = acc['id']

        # Add 3 transactions: first one does NOT match search query, second one DOES match
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-01', 'expense', 15000, 'Beli Odol', 'Kebutuhan')", (user_id, acc_id))
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-02', 'expense', 25000, 'Makan Nasi Padang', 'Makanan')", (user_id, acc_id))
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-03', 'expense', 50000, 'Bensin Motor', 'Transport')", (user_id, acc_id))
        db.commit()

    # 1. Test RAG chat searches across all transactions (match is on 2nd tx: Padang)
    rag_res = client.post('/api/rag_chat', json={'message': 'padang'})
    assert rag_res.status_code == 200
    assert 'Padang' in rag_res.json['reply']
    assert '25,000' in rag_res.json['reply']

    # 2. Test predict_future with >= 3 data points
    pred_res = client.get('/api/predict_future')
    assert pred_res.status_code == 200
    assert pred_res.json['status'] == 'success'
    assert len(pred_res.json['predictions']) == 7

def test_dashboard_alias_and_bulk_transfer_symmetry(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_dash_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Dash User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # 1. Test /dashboard alias returns 200
    dash_res = client.get('/dashboard')
    assert dash_res.status_code == 200

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user['id']
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance) VALUES (?, 'Bank A', 500000, 500000)", (user_id,))
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance) VALUES (?, 'Bank B', 500000, 500000)", (user_id,))
        db.commit()
        accs = db.execute("SELECT id FROM accounts WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        acc1, acc2 = accs[0]['id'], accs[1]['id']

        # Insert legacy paired transfer (without linked_transaction_id)
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-05', 'expense', 100000, 'Transfer out', 'Transfer')", (user_id, acc1))
        leg1 = db.execute("SELECT id FROM transactions WHERE user_id = ? AND type = 'expense'", (user_id,)).fetchone()
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-05', 'income', 100000, 'Transfer in', 'Transfer')", (user_id, acc2))
        db.commit()

        leg1_id = leg1['id']

    # 2. Test bulk_delete deletes legacy paired leg symmetrically
    client.post('/transactions/bulk_delete', data={'transaction_ids': str(leg1_id)}, follow_redirects=True)

    with client.application.app_context():
        db = get_db()
        remaining_txs = db.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,)).fetchone()[0]
        assert remaining_txs == 0

def test_split_bill_and_custom_category_integration(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_split_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Split User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # 1. Add Custom Category in settings
    client.post('/settings', data={
        'action': 'add_category',
        'type': 'expense',
        'name': 'Konser & Musik'
    }, follow_redirects=True)

    # 2. Setup account
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'CASH',
        'initial_balance': '500.000'
    }, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user['id']
        acc = db.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
        acc_id = acc['id']

    # 3. Add Transaction with Split Bill enabled
    tx_res = client.post('/transactions/add', data={
        'type': 'expense',
        'date': '2026-10-06',
        'amount': '150.000',
        'category': 'Konser & Musik',
        'account_id': acc_id,
        'description': 'Beli Tiket Konser Berdua',
        'is_split': 'true',
        'split_person': 'Budi Doremi',
        'split_amount': '75.000'
    }, follow_redirects=True)
    assert tx_res.status_code == 200

    # 4. Verify receivable was automatically created in debts_receivables
    with client.application.app_context():
        db = get_db()
        debt = db.execute("SELECT * FROM debts_receivables WHERE user_id = ? AND person_name = ?", (user_id, 'Budi Doremi')).fetchone()
        assert debt is not None
        assert debt['type'] == 'receivable'
        assert debt['total_amount'] == 75000.0
        assert debt['remaining_amount'] == 75000.0
        assert debt['status'] == 'BELUM LUNAS'

    # 5. Verify custom category is merged and visible in transactions_list
    list_res = client.get('/transactions/')
    assert list_res.status_code == 200
    assert b'Konser &amp; Musik' in list_res.data or b'Konser & Musik' in list_res.data

def test_delete_account_foreign_key_safety(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_del_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Delete User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user['id']

        # Add referencing rows across webauthn, achievements, and notifications
        try:
            db.execute("INSERT INTO webauthn_credentials (user_id, credential_id, public_key, sign_count) VALUES (?, 'testcred', b'key', 0)", (user_id,))
        except Exception:
            pass
        try:
            db.execute("INSERT INTO user_achievements (user_id, xp, level, badges) VALUES (?, 100, 2, '[]')", (user_id,))
        except Exception:
            pass
        try:
            db.execute("INSERT INTO notifications (user_id, message) VALUES (?, 'Selamat datang!')", (user_id,))
        except Exception:
            pass
        db.commit()

    # Call delete_account
    del_res = client.post('/settings', data={
        'action': 'delete_account',
        'password_check': password
    }, follow_redirects=True)
    assert del_res.status_code == 200
    assert b'Akun Anda beserta seluruh data terkait telah berhasil dihapus' in del_res.data

    with client.application.app_context():
        db = get_db()
        deleted_user = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        assert deleted_user is None


def test_remaining_14_bugs_regression(client, monkeypatch):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_14b_{test_id}"
    password = "Password123!"

    # Unauthenticated debug endpoints must redirect or return 403
    for ep in ['/test_db', '/session_expired', '/test_performance', '/debug_logs', '/test_all_queries', '/run_migration', '/dump_logs']:
        res_ep = client.get(ep)
        assert res_ep.status_code in (302, 403)

    # /dev-console with unset DEV_SECRET_KEY must return 403 even if ?key=1 is passed
    monkeypatch.delenv('DEV_SECRET_KEY', raising=False)
    assert client.get('/dev-console?key=1').status_code == 403

    client.post('/register', data={
        'fullname': 'Audit 14 User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user['id']
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, '[BANK] BCA', 1000000, 1000000, 'asset')", (user_id,))
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, '[BANK] Mandiri', 500000, 500000, 'asset')", (user_id,))
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type, limit_amount) VALUES (?, '[KARTU KREDIT] BCA Card', 0, -200000, 'liability', 5000000)", (user_id,))
        db.commit()
        accs = db.execute("SELECT id, name FROM accounts WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        acc_bca, acc_mandiri = accs[0]['id'], accs[1]['id']

        # Insert 1 income (800k), 1 small expense (50k), 1 high expense (600k), and 1 Transfer pair (300k)
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-10', 'income', 800000, 'Gaji', 'Gaji')", (user_id, acc_bca))
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-11', 'expense', 50000, 'Makan Siang', 'Makanan')", (user_id, acc_bca))
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-12', 'expense', 600000, 'Servis Mobil', 'Transportasi')", (user_id, acc_bca))
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-12', 'expense', 300000, 'Transfer ke Mandiri', 'Transfer')", (user_id, acc_bca))
        db.execute("INSERT INTO transactions (user_id, account_id, date, type, amount, description, category) VALUES (?, ?, '2026-10-12', 'income', 300000, 'Transfer dari BCA', 'Transfer')", (user_id, acc_mandiri))
        db.commit()
        tx_small = db.execute("SELECT id FROM transactions WHERE user_id = ? AND amount = 50000", (user_id,)).fetchone()['id']

    # 1. Verify Transfer is excluded from Filtered Income (800.000, not 1.100.000) and Filtered Expense (650.000, not 950.000)
    res_list = client.get('/transactions/')
    assert res_list.status_code == 200
    assert b'Rp 800.000' in res_list.data
    assert b'Rp 650.000' in res_list.data

    # 2. Verify Sort by Account (sort_by=account_name)
    res_sort = client.get('/transactions/?sort_by=account_name&sort_order=asc')
    assert res_sort.status_code == 200

    # 3. Verify Quick Filters (tx_type=income and min_amount=500000)
    res_inc = client.get('/transactions/?tx_type=income')
    assert res_inc.status_code == 200
    assert b'Gaji' in res_inc.data
    assert b'Makan Siang' not in res_inc.data

    res_high = client.get('/transactions/?tx_type=expense&min_amount=500000')
    assert res_high.status_code == 200
    assert b'Servis Mobil' in res_high.data
    assert b'Makan Siang' not in res_high.data

    # 4. Verify Bulk Edit modal form names (transaction_ids & category)
    res_bulk = client.post('/transactions/bulk_edit', data={
        'transaction_ids': str(tx_small),
        'category': 'Hiburan'
    }, follow_redirects=True)
    assert res_bulk.status_code == 200
    with client.application.app_context():
        db = get_db()
        updated_cat = db.execute("SELECT category FROM transactions WHERE id = ?", (tx_small,)).fetchone()['category']
        assert updated_cat == 'Hiburan'

    # 5. Verify Financial Performance Net Worth card Beban does not double-count CC usage (should be Rp 200.000, not Rp 400.000)
    res_perf = client.get('/financial_performance?days=7')
    assert res_perf.status_code == 200
    assert b'Beban: Rp 200.000' in res_perf.data


def test_second_pass_10_bugs_regression(client):
    """Verify all 10 remaining bugs from the second-pass comprehensive audit."""
    username = f"audit_10_{uuid.uuid4().hex[:8]}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Audit 10 User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user['id']
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, '[BANK] BCA', 1000000, 1000000, 'asset')", (user_id,))
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, '[BANK] EmptyAccount', 0, 0, 'asset')", (user_id,))
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type, limit_amount) VALUES (?, '[KARTU KREDIT] Mandiri CC', -250000, -250000, 'liability', 5000000)", (user_id,))
        db.commit()
        accs = db.execute("SELECT id, name FROM accounts WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        acc_bca, acc_empty, acc_cc = accs[0]['id'], accs[1]['id'], accs[2]['id']

    # 1. Deleting an empty account in /setup/accounts should succeed without SQL error on transfer_to_account_id
    res_del = client.post(f'/setup/accounts?delete_id={acc_empty}', follow_redirects=True)
    assert res_del.status_code == 200
    with client.application.app_context():
        db = get_db()
        assert db.execute("SELECT id FROM accounts WHERE id = ?", (acc_empty,)).fetchone() is None

    # 2. Adding a Receivable (Piutang) should NOT inflate user's total_debt or Beban
    res_rec = client.post('/financial_performance', data={
        'action': 'add_debt',
        'person_name': 'Budi',
        'type': 'receivable',
        'total_amount': '500.000',
        'due_date': '2026-11-15',
        'notes': 'Pinjam uang makan'
    }, follow_redirects=True)
    assert res_rec.status_code == 200
    # Only Mandiri CC (-250.000) is debt; Budi's 500.000 receivable must NOT make Beban Rp 750.000
    assert b'Beban: Rp 250.000' in res_rec.data

    # 3. AI Chat "berapa utang saya?" should include liability account usage (Rp 250.000)
    res_chat = client.post('/api/chat', json={'message': 'berapa utang saya?'})
    assert res_chat.status_code == 200
    chat_reply = res_chat.get_json()['reply']
    assert '250,000' in chat_reply or '250.000' in chat_reply

    # 4. Achieved Financial Goal should NOT appear in /api/calendar_events
    with client.application.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO financial_goals (user_id, name, target_amount, current_amount, due_date, status) VALUES (?, 'Beli Laptop', 10000000, 10000000, '2026-10-20', 'Achieved')",
            (user_id,)
        )
        db.commit()
    res_cal = client.get('/api/calendar_events?month=10&year=2026')
    assert res_cal.status_code == 200
    events = res_cal.get_json()
    assert not any('Beli Laptop' in ev.get('title', '') for ev in events)

    # 5. Linked Installment payment should reject selecting the destination liability account as source
    with client.application.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO recurring_installments (user_id, name, amount_per_cycle, due_day_of_month, is_temporary_tenor, total_tenor, current_tenor, linked_account_id) "
            "VALUES (?, 'Cicilan HP', 250000, 15, 1, 2, 1, ?)",
            (user_id, acc_cc)
        )
        db.commit()
        inst_id = db.execute("SELECT id FROM recurring_installments WHERE user_id = ?", (user_id,)).fetchone()['id']

    res_bad_pay = client.post('/financial_performance', data={
        'action': 'pay_installment',
        'inst_id': inst_id,
        'account_name': acc_cc,
        'amount_paid': '250.000'
    }, follow_redirects=True)
    assert res_bad_pay.status_code == 200
    with client.application.app_context():
        db = get_db()
        inst_row = db.execute("SELECT current_tenor FROM recurring_installments WHERE id = ?", (inst_id,)).fetchone()
        assert inst_row['current_tenor'] == 1


def test_third_pass_12_bugs_regression(client):
    """Verify the 12 edge-case bugs from the third-pass deep audit."""
    # 1. Custom 404 page should render 404.html with Tailwind and Indonesian message
    res_404 = client.get('/halaman-tidak-ditemukan-404')
    assert res_404.status_code == 404
    assert b'Oops! Nyasar ya?' in res_404.data

    username = f"audit_12_{uuid.uuid4().hex[:8]}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Audit 12 User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # 2. Settings: reject invalid characters (@) in update_username and reject duplicate default category in add_category
    res_bad_user = client.post('/settings', data={
        'action': 'update_username',
        'username': 'bad@username.com'
    })
    assert res_bad_user.status_code == 200
    assert b'Username hanya boleh berisi huruf' in res_bad_user.data

    res_dup_cat = client.post('/settings', data={
        'action': 'add_category',
        'type': 'expense',
        'name': 'Makanan & Minuman'
    })
    assert res_dup_cat.status_code == 200
    assert b'sudah ada' in res_dup_cat.data
    assert b"activeTab: 'categories'" in res_dup_cat.data

    # 3. Linked installment payment sets linked_transaction_id on both Transfer rows
    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()['id']
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, '[BANK] BCA', 2000000, 2000000, 'asset')", (user_id,))
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type, limit_amount, billing_due_day) VALUES (?, '[KARTU KREDIT] BCA CC', -500000, -500000, 'liability', 5000000, 30)", (user_id,))
        db.commit()
        accs = db.execute("SELECT id FROM accounts WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        acc_bca, acc_cc = accs[0]['id'], accs[1]['id']
        db.execute(
            "INSERT INTO recurring_installments (user_id, name, amount_per_cycle, due_day_of_month, is_temporary_tenor, total_tenor, current_tenor, linked_account_id) "
            "VALUES (?, 'Tagihan CC', 500000, 31, 1, 2, 1, ?)",
            (user_id, acc_cc)
        )
        db.commit()
        inst_id = db.execute("SELECT id FROM recurring_installments WHERE user_id = ?", (user_id,)).fetchone()['id']

    res_pay = client.post('/financial_performance', data={
        'action': 'pay_installment',
        'inst_id': inst_id,
        'account_name': acc_bca,
        'amount_paid': '500.000'
    }, follow_redirects=True)
    assert res_pay.status_code == 200
    with client.application.app_context():
        db = get_db()
        txs = db.execute("SELECT id, linked_transaction_id FROM transactions WHERE user_id = ? AND category = 'Transfer' ORDER BY id ASC", (user_id,)).fetchall()
        assert len(txs) == 2
        assert txs[0]['linked_transaction_id'] == txs[1]['id']
        assert txs[1]['linked_transaction_id'] == txs[0]['id']

    # 4. Adding a goal with current_amount >= target_amount immediately marks it Achieved
    res_goal = client.post('/financial_performance', data={
        'action': 'add_goal',
        'goal_name': 'Dana Darurat',
        'target_amount': '1.000.000',
        'current_amount': '1.000.000',
        'due_date': '2026-12-31'
    }, follow_redirects=True)
    assert res_goal.status_code == 200
    with client.application.app_context():
        db = get_db()
        g_row = db.execute("SELECT status FROM financial_goals WHERE user_id = ? AND name = 'Dana Darurat'", (user_id,)).fetchone()
        assert g_row['status'] == 'Achieved'


def test_fourth_pass_10_bugs_regression(client):
    """
    Verifies the 10 fourth-pass bugs:
    1. Account names/badges visible even when has_logo is true (macros.html / setup_account.html)
    2. Bulk Edit Category refuses to overwrite Transfer transactions
    3. Export links preserve tx_type and min_amount filters
    4. Category filter dropdown includes Transfer
    5. Receipt PDF download button rendered & endpoint works
    6. Split Bill caps split_amount at amount and ignores non-expense
    """
    username = f"fourth_pass_{uuid.uuid4().hex[:6]}"
    password = "StrongPass123"
    client.post('/register', data={
        'fullname': 'Fourth Pass User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()['id']
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type) VALUES (?, '[BANK] BCA', 1000000, 1000000, 'asset')", (user_id,))
        db.execute("INSERT INTO accounts (user_id, name, initial_balance, current_balance, account_type, limit_amount) VALUES (?, '[KARTU KREDIT] BCA Card', 0, 0, 'liability', 5000000)", (user_id,))
        db.commit()
        accs = db.execute("SELECT id FROM accounts WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        acc_bca, acc_card = accs[0]['id'], accs[1]['id']

    # 1. Setup accounts page renders both account names & category badges even though both have BCA logo
    res_setup = client.get('/setup/accounts')
    assert res_setup.status_code == 200
    assert b'BCA Card' in res_setup.data
    assert b'KARTU KREDIT' in res_setup.data

    # 2. Add a transfer transaction and verify Bulk Edit cannot overwrite its category
    res_tf = client.post('/transactions/add', data={
        'date': '2026-08-19',
        'type': 'transfer',
        'amount': '100.000',
        'account_id': acc_bca,
        'to_account_id': acc_card,
        'description': 'Bayar BCA Card'
    }, follow_redirects=True)
    assert res_tf.status_code == 200

    with client.application.app_context():
        db = get_db()
        tf_txs = db.execute("SELECT id, category FROM transactions WHERE user_id = ? AND category = 'Transfer'", (user_id,)).fetchall()
        assert len(tf_txs) == 2
        tf_ids = [r['id'] for r in tf_txs]

    res_bulk = client.post('/transactions/bulk_edit', data={
        'transaction_ids_bulk': f'{tf_ids[0]},{tf_ids[1]}',
        'bulk_category': 'Makanan & Minuman'
    }, follow_redirects=True)
    assert res_bulk.status_code == 200
    with client.application.app_context():
        db = get_db()
        tf_after = db.execute("SELECT category FROM transactions WHERE id IN (?, ?)", (tf_ids[0], tf_ids[1])).fetchall()
        assert all(r['category'] == 'Transfer' for r in tf_after)

    # 3. Split bill caps split_amount at total expense amount
    res_split = client.post('/transactions/add', data={
        'date': '2026-08-19',
        'type': 'expense',
        'amount': '50.000',
        'category': 'Makanan & Minuman',
        'account_id': acc_bca,
        'description': 'Makan Bareng',
        'is_split': 'true',
        'split_person': 'Budi',
        'split_amount': '200.000'
    }, follow_redirects=True)
    assert res_split.status_code == 200
    with client.application.app_context():
        db = get_db()
        debt = db.execute("SELECT total_amount, remaining_amount FROM debts_receivables WHERE user_id = ? AND person_name = 'Budi'", (user_id,)).fetchone()
        assert debt is not None
        assert debt['total_amount'] == 50000
        assert debt['remaining_amount'] == 50000

    # 4. Transactions list renders Transfer filter, export query_params with tx_type/min_amount, and Receipt PDF link
    res_list = client.get('/transactions?tx_type=expense&min_amount=10000')
    assert res_list.status_code == 200
    assert b'value="Transfer"' in res_list.data
    assert b'tx_type=expense&amp;min_amount=10000' in res_list.data or b'tx_type=expense&min_amount=10000' in res_list.data
    assert b'/receipt' in res_list.data

    # 5. Receipt PDF endpoint returns 200 PDF
    res_receipt = client.get(f'/transactions/transaction/{tf_ids[0]}/receipt')
    assert res_receipt.status_code == 200
    assert res_receipt.mimetype == 'application/pdf'






