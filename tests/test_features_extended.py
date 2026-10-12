import pytest
import uuid
from io import BytesIO

def test_transactions_delete_and_bulk_operations(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_bulk_{test_id}"
    password = "Password123!"

    # Register & Login
    client.post('/register', data={
        'fullname': 'Bulk Test User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user_row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user_row['id']

    # Create Bank Account
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'BANK',
        'name_detail': 'Mandiri',
        'initial_balance': '1.000.000'
    }, follow_redirects=True)

    with client.application.app_context():
        db = get_db()
        acc = db.execute("SELECT id FROM accounts WHERE user_id = ? AND name LIKE '%Mandiri%'", (user_id,)).fetchone()
        acc_id = acc['id']

    # Add 3 transactions
    tx_ids = []
    for i in range(1, 4):
        client.post('/transactions/add', data={
            'type': 'expense',
            'date': f'2026-10-0{i}',
            'amount': '50.000',
            'category': 'Belanja',
            'account_id': acc_id,
            'description': f'Item {i}'
        }, follow_redirects=True)

    with client.application.app_context():
        db = get_db()
        acc_check = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_id,)).fetchone()
        # 1,000,000 - 3 * 50,000 = 850,000
        assert acc_check['current_balance'] == 850000.0
        tx_rows = db.execute("SELECT id FROM transactions WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        tx_ids = [str(r['id']) for r in tx_rows]
        assert len(tx_ids) == 3

    # Test Bulk Delete 2 of them
    bulk_del_res = client.post('/transactions/bulk_delete', data={
        'transaction_ids': f"{tx_ids[0]},{tx_ids[1]}"
    }, follow_redirects=True)
    assert bulk_del_res.status_code == 200

    # Verify balance adjusted for the 2 deleted transactions (+100,000)
    with client.application.app_context():
        db = get_db()
        acc_check = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_id,)).fetchone()
        # 850,000 + 100,000 = 950,000
        assert acc_check['current_balance'] == 950000.0
        remaining_tx = db.execute("SELECT id FROM transactions WHERE user_id = ?", (user_id,)).fetchall()
        assert len(remaining_tx) == 1

    # Test Delete All
    del_all_res = client.post('/transactions/delete_all', follow_redirects=True)
    assert del_all_res.status_code == 200

    # Verify reset to initial balance
    with client.application.app_context():
        db = get_db()
        acc_check = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_id,)).fetchone()
        assert acc_check['current_balance'] == 1000000.0
        all_tx = db.execute("SELECT id FROM transactions WHERE user_id = ?", (user_id,)).fetchall()
        assert len(all_tx) == 0

def test_exports(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_exp_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Export User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # Add account and transaction
    client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'CASH',
        'initial_balance': '100.000'
    }, follow_redirects=True)

    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user_row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        user_id = user_row['id']
        acc = db.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,)).fetchone()

    client.post('/transactions/add', data={
        'type': 'expense',
        'date': '2026-10-01',
        'amount': '25.000',
        'category': 'Transportasi',
        'account_id': acc['id'],
        'description': 'Angkot'
    }, follow_redirects=True)

    # Test CSV export
    csv_res = client.get('/transactions/export_csv')
    assert csv_res.status_code == 200
    assert b'Transportasi' in csv_res.data
    assert b'Angkot' in csv_res.data

    # Test PDF export
    pdf_res = client.get('/transactions/export_pdf')
    assert pdf_res.status_code == 200
    assert pdf_res.headers.get('Content-Type') == 'application/pdf'

def test_budgets_and_assets(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_bgt_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Budget User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # 1. Add Budget
    bgt_res = client.post('/manage_budget', data={
        'action': 'add',
        'category_name': 'Makanan & Minuman',
        'limit_amount': '1.500.000'
    }, follow_redirects=True)
    assert bgt_res.status_code == 200

    # 2. Add Asset
    asset_res = client.post('/financial_performance', data={
        'action': 'add_asset',
        'asset_name': 'Emas Antam 5g',
        'category': 'Emas & Logam Mulia',
        'purchase_date': '2026-09-15',
        'purchase_price': '6.500.000',
        'quantity': '1',
        'notes': 'Investasi jangka panjang'
    }, follow_redirects=True)
    assert asset_res.status_code == 200
    assert b'Emas Antam' in asset_res.data

    # 3. Add Financial Goal
    goal_res = client.post('/financial_performance', data={
        'action': 'add_goal',
        'goal_name': 'Dana Darurat',
        'target_amount': '20.000.000',
        'current_amount': '5.000.000',
        'due_date': '2027-12-31'
    }, follow_redirects=True)
    assert goal_res.status_code == 200
    assert b'Dana Darurat' in goal_res.data
