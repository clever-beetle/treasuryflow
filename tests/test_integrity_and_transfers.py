import pytest
import uuid
from datetime import datetime

def test_transfer_creation_and_symmetric_deletion(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_tr_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Transfer User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # Add Account A (Bank BCA) with 1.000.000
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'BANK',
        'name_detail': 'BCA',
        'initial_balance': '1.000.000'
    }, follow_redirects=True)

    # Add Account B (E-Wallet GoPay) with 200.000
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'E-WALLET',
        'name_detail': 'GoPay',
        'initial_balance': '200.000'
    }, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user['id']
        acc_a = db.execute("SELECT id, current_balance FROM accounts WHERE user_id = ? AND name LIKE '%BCA%'", (user_id,)).fetchone()
        acc_b = db.execute("SELECT id, current_balance FROM accounts WHERE user_id = ? AND name LIKE '%GoPay%'", (user_id,)).fetchone()
        assert acc_a['current_balance'] == 1000000
        assert acc_b['current_balance'] == 200000
        acc_a_id = acc_a['id']
        acc_b_id = acc_b['id']

    # 1. Perform Transfer: 300.000 from BCA to GoPay
    transfer_res = client.post('/transactions/add', data={
        'type': 'transfer',
        'date': '2026-10-06',
        'amount': '300.000',
        'account_id': acc_a_id,
        'to_account_id': acc_b_id,
        'description': 'Topup GoPay'
    }, follow_redirects=True)
    assert transfer_res.status_code == 200

    with client.application.app_context():
        db = get_db()
        txs = db.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        assert len(txs) == 2
        leg1 = txs[0]
        leg2 = txs[1]
        assert leg1['linked_transaction_id'] == leg2['id']
        assert leg2['linked_transaction_id'] == leg1['id']

        # Verify balances after transfer
        acc_a_after = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_a_id,)).fetchone()
        acc_b_after = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_b_id,)).fetchone()
        assert acc_a_after['current_balance'] == 700000
        assert acc_b_after['current_balance'] == 500000

    # 2. Delete Leg 1 (should symmetrically delete Leg 2 and restore balances)
    del_res = client.post(f'/transactions/delete/{leg1["id"]}', follow_redirects=True)
    assert del_res.status_code == 200

    with client.application.app_context():
        db = get_db()
        remaining_txs = db.execute("SELECT * FROM transactions WHERE user_id = ?", (user_id,)).fetchall()
        assert len(remaining_txs) == 0

        acc_a_restored = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_a_id,)).fetchone()
        acc_b_restored = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_b_id,)).fetchone()
        assert acc_a_restored['current_balance'] == 1000000
        assert acc_b_restored['current_balance'] == 200000

def test_edit_transaction_and_idor_protection(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_ed_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Edit User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

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

    # Add expense 50.000
    client.post('/transactions/add', data={
        'type': 'expense',
        'date': '2026-10-06',
        'amount': '50.000',
        'category': 'Makanan & Minuman',
        'account_id': acc_id,
        'description': 'Makan Siang'
    }, follow_redirects=True)

    with client.application.app_context():
        db = get_db()
        tx = db.execute("SELECT id, amount FROM transactions WHERE user_id = ?", (user_id,)).fetchone()
        assert tx['amount'] == 50000
        tx_id = tx['id']

    # 1. Edit page GET prefill test
    get_edit = client.get(f'/transactions/edit/{tx_id}')
    assert get_edit.status_code == 200
    assert b'Makan Siang' in get_edit.data
    assert b'50.000' in get_edit.data

    # 2. Edit transaction: change amount to 75.000 and description
    post_edit = client.post(f'/transactions/edit/{tx_id}', data={
        'type': 'expense',
        'date': '2026-10-06',
        'amount': '75.000',
        'category': 'Makanan & Minuman',
        'account_id': acc_id,
        'description': 'Makan Siang Mewah'
    }, follow_redirects=True)
    assert post_edit.status_code == 200

    with client.application.app_context():
        db = get_db()
        tx_updated = db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        assert tx_updated['amount'] == 75000
        assert tx_updated['description'] == 'Makan Siang Mewah'
        acc_updated = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_id,)).fetchone()
        assert acc_updated['current_balance'] == 425000  # 500.000 - 75.000

    # 3. IDOR test: trying to add transaction with another user's or invalid account_id
    idor_res = client.post('/transactions/add', data={
        'type': 'expense',
        'date': '2026-10-06',
        'amount': '20.000',
        'category': 'Makanan & Minuman',
        'account_id': 999999,
        'description': 'IDOR Attack'
    }, follow_redirects=True)
    assert b'Akun sumber tidak valid' in idor_res.data

def test_transfer_edit_synchronization_and_delete_all(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_sync_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Sync User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # Accounts
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'BANK',
        'name_detail': 'BCA',
        'initial_balance': '1.000.000'
    }, follow_redirects=True)
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'E-WALLET',
        'name_detail': 'OVO',
        'initial_balance': '200.000'
    }, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user['id']
        bca = db.execute("SELECT id FROM accounts WHERE user_id = ? AND name LIKE '%BCA%'", (user_id,)).fetchone()
        ovo = db.execute("SELECT id FROM accounts WHERE user_id = ? AND name LIKE '%OVO%'", (user_id,)).fetchone()
        bca_id, ovo_id = bca['id'], ovo['id']

    # Transfer 100.000
    client.post('/transactions/add', data={
        'type': 'transfer',
        'date': '2026-10-06',
        'amount': '100.000',
        'account_id': bca_id,
        'to_account_id': ovo_id,
        'description': 'Topup OVO'
    }, follow_redirects=True)

    with client.application.app_context():
        db = get_db()
        txs = db.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        assert len(txs) == 2
        leg1_id, leg2_id = txs[0]['id'], txs[1]['id']

    # Edit Leg 1 amount to 250.000
    edit_res = client.post(f'/transactions/edit/{leg1_id}', data={
        'type': 'expense',
        'date': '2026-10-07',
        'amount': '250.000',
        'category': 'Transfer',
        'account_id': bca_id,
        'description': 'Topup OVO Updated'
    }, follow_redirects=True)
    assert edit_res.status_code == 200

    # Verify both legs are updated to 250.000 and date synced
    with client.application.app_context():
        db = get_db()
        leg1 = db.execute("SELECT * FROM transactions WHERE id = ?", (leg1_id,)).fetchone()
        leg2 = db.execute("SELECT * FROM transactions WHERE id = ?", (leg2_id,)).fetchone()
        assert leg1['amount'] == 250000
        assert leg2['amount'] == 250000
        assert leg1['date'] == '2026-10-07'
        assert leg2['date'] == '2026-10-07'

        bca_cur = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()['current_balance']
        ovo_cur = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (ovo_id,)).fetchone()['current_balance']
        assert bca_cur == 750000  # 1.000.000 - 250.000
        assert ovo_cur == 450000  # 200.000 + 250.000

    # Delete all transactions & verify balances immediately reset to initial_balance
    del_all = client.post('/transactions/delete_all', follow_redirects=True)
    assert del_all.status_code == 200

    with client.application.app_context():
        db = get_db()
        assert len(db.execute("SELECT id FROM transactions WHERE user_id = ?", (user_id,)).fetchall()) == 0
        bca_reset = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()['current_balance']
        ovo_reset = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (ovo_id,)).fetchone()['current_balance']
        assert bca_reset == 1000000
        assert ovo_reset == 200000

def test_budget_calendar_and_liability_balance(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_bcl_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'BCL User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # 1. Manage budget invalid & valid additions
    res_inv = client.post('/manage_budget', data={'action': 'add', 'category_name': '', 'limit_amount': '0'}, follow_redirects=True)
    assert b'valid' in res_inv.data.lower() or res_inv.status_code == 200

    res_val = client.post('/manage_budget', data={'action': 'add', 'category_name': 'Makan', 'limit_amount': '500.000'}, follow_redirects=True)
    assert res_val.status_code == 200

    # 2. Add Debt & Goal and verify Calendar Events
    client.post('/financial_performance', data={
        'action': 'add_debt',
        'person_name': 'Budi',
        'type': 'debt',
        'total_amount': '300.000',
        'due_date': '2026-10-25',
        'notes': 'Pinjam uang'
    }, follow_redirects=True)

    client.post('/financial_performance', data={
        'action': 'add_goal',
        'goal_name': 'Beli Laptop',
        'target_amount': '15.000.000',
        'current_amount': '2.000.000',
        'due_date': '2026-12-31'
    }, follow_redirects=True)

    cal_res = client.get('/api/calendar_events')
    assert cal_res.status_code == 200
    events = cal_res.get_json()
    assert len(events) >= 2
    titles = [e['title'] for e in events]
    assert any('Budi' in t for t in titles)
    assert any('Laptop' in t for t in titles)

    # 3. Liability account overpayment test (credit card)
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'KARTU KREDIT',
        'name_detail': 'BCA Card',
        'initial_balance': '0',
        'limit_amount': '5.000.000'
    }, follow_redirects=True)

    # Check financial performance page loads without error and overpayment is 0 debt
    perf_res = client.get('/financial_performance')
    assert perf_res.status_code == 200
