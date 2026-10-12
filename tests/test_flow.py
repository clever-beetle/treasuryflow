import pytest
import uuid

def test_complete_user_flow(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_{test_id}"
    email = f"{username}@test.com"
    password = "Password123!"

    # 1. Register a new user
    reg_res = client.post('/register', data={
        'fullname': 'Test User Flow',
        'username': username,
        'email': email,
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)
    assert reg_res.status_code == 200

    # 2. Login
    login_res = client.post('/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)
    assert login_res.status_code == 200

    # Fetch user_id
    from utils import get_db
    with client.application.app_context():
        db = get_db()
        user_row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        assert user_row is not None
        user_id = user_row['id']

    # 3. Create Accounts
    # 3a. Add Cash account
    acc_cash = client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'CASH',
        'initial_balance': '500.000'
    }, follow_redirects=True)
    assert acc_cash.status_code == 200
    assert b'Cash' in acc_cash.data

    # 3b. Add Bank account (BCA)
    acc_bank = client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'BANK',
        'name_detail': 'BCA',
        'initial_balance': '1.000.000'
    }, follow_redirects=True)
    assert acc_bank.status_code == 200
    assert b'BCA' in acc_bank.data

    # 3c. Add Liability account (Kartu Kredit BCA Card)
    acc_cc = client.post('/setup/accounts', data={
        'action': 'add',
        'category_key': 'KARTU KREDIT',
        'name_detail': 'BCA Card',
        'initial_balance': '200.000',
        'limit_amount': '5.000.000',
        'billing_due_day': '15'
    }, follow_redirects=True)
    assert acc_cc.status_code == 200
    assert b'BCA Card' in acc_cc.data

    # 4. View Dashboard
    dash_res = client.get('/', follow_redirects=True)
    assert dash_res.status_code == 200
    assert b'BCA' in dash_res.data
    assert b'Cash' in dash_res.data

    # Extract account IDs for this user
    with client.application.app_context():
        db = get_db()
        accounts = db.execute("SELECT id, name, account_type, initial_balance, current_balance FROM accounts WHERE user_id = ?", (user_id,)).fetchall()
        acc_dict = {a['name']: a for a in accounts}

    bca_id = acc_dict['[BANK] BCA']['id']
    cash_id = acc_dict['Cash']['id']
    cc_id = acc_dict['[KARTU KREDIT] BCA Card']['id']

    # Initial balance check
    # CC liability initial balance is stored as negative (-200000)
    assert acc_dict['[KARTU KREDIT] BCA Card']['current_balance'] == -200000.0
    assert acc_dict['[BANK] BCA']['current_balance'] == 1000000.0
    assert acc_dict['Cash']['current_balance'] == 500000.0

    # 5. Add Transactions
    # 5a. Income transaction
    tx_inc = client.post('/transactions/add', data={
        'type': 'income',
        'date': '2026-10-01',
        'amount': '2.000.000',
        'category': 'Gaji',
        'account_id': bca_id,
        'description': 'Monthly salary'
    }, follow_redirects=True)
    assert tx_inc.status_code == 200

    # 5b. Expense transaction
    tx_exp = client.post('/transactions/add', data={
        'type': 'expense',
        'date': '2026-10-02',
        'amount': '150.000',
        'category': 'Makanan & Minuman',
        'account_id': cash_id,
        'description': 'Lunch with team'
    }, follow_redirects=True)
    assert tx_exp.status_code == 200

    # 5c. Transfer transaction (BCA -> Cash)
    tx_trf = client.post('/transactions/add', data={
        'type': 'transfer',
        'date': '2026-10-03',
        'amount': '300.000',
        'account_id': bca_id,
        'to_account_id': cash_id,
        'description': 'ATM Cash withdrawal'
    }, follow_redirects=True)
    assert tx_trf.status_code == 200

    # Check balances after transactions
    with client.application.app_context():
        db = get_db()
        bca = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()
        cash = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (cash_id,)).fetchone()
        # BCA: 1,000,000 + 2,000,000 (salary) - 300,000 (transfer out) = 2,700,000
        assert bca['current_balance'] == 2700000.0
        # Cash: 500,000 - 150,000 (lunch) + 300,000 (transfer in) = 650,000
        assert cash['current_balance'] == 650000.0

    # 6. View Transactions List
    tx_list = client.get('/transactions/', follow_redirects=True)
    assert tx_list.status_code == 200
    assert b'Monthly salary' in tx_list.data
    assert b'Lunch with team' in tx_list.data
    assert b'ATM Cash withdrawal' in tx_list.data

    # 7. Edit Transaction
    with client.application.app_context():
        db = get_db()
        salary_tx = db.execute("SELECT id FROM transactions WHERE user_id = ? AND description = 'Monthly salary'", (user_id,)).fetchone()
    
    edit_res = client.post(f'/transactions/edit/{salary_tx["id"]}', data={
        'type': 'income',
        'date': '2026-10-01',
        'amount': '2.500.000',
        'category': 'Gaji',
        'account_id': bca_id,
        'description': 'Monthly salary + bonus'
    }, follow_redirects=True)
    assert edit_res.status_code == 200
    assert b'Monthly salary + bonus' in edit_res.data

    # Verify updated balance
    with client.application.app_context():
        db = get_db()
        bca = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()
        # BCA: 1,000,000 + 2,500,000 - 300,000 = 3,200,000
        assert bca['current_balance'] == 3200000.0

    # 8. Financial Performance Operations
    # 8a. Add Debt (Utang)
    perf_add_debt = client.post('/financial_performance', data={
        'action': 'add_debt',
        'person_name': 'Budi',
        'type': 'debt',
        'total_amount': '500.000',
        'due_date': '2026-11-01',
        'notes': 'Pinjam modal usaha'
    }, follow_redirects=True)
    assert perf_add_debt.status_code == 200
    assert b'Budi' in perf_add_debt.data

    # 8b. Pay Debt
    with client.application.app_context():
        db = get_db()
        debt_row = db.execute("SELECT id FROM debts_receivables WHERE user_id = ? AND person_name = 'Budi'", (user_id,)).fetchone()

    perf_pay_debt = client.post('/financial_performance', data={
        'action': 'pay_debt',
        'debt_id': debt_row['id'],
        'account_name': bca_id,
        'amount_paid': '200.000',
        'notes': 'Cicilan 1'
    }, follow_redirects=True)
    assert perf_pay_debt.status_code == 200

    # Verify debt remaining amount and BCA balance
    with client.application.app_context():
        db = get_db()
        debt_updated = db.execute("SELECT remaining_amount, status FROM debts_receivables WHERE id = ?", (debt_row['id'],)).fetchone()
        assert debt_updated['remaining_amount'] == 300000.0
        assert debt_updated['status'] == 'BELUM LUNAS'

        bca = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()
        # BCA: 3,200,000 - 200,000 = 3,000,000
        assert bca['current_balance'] == 3000000.0

    # 8c. Add Installment
    perf_add_inst = client.post('/financial_performance', data={
        'action': 'add_installment',
        'name': 'Netflix 4K',
        'amount_per_cycle': '186.000',
        'due_day_of_month': '10',
        'is_temporary_tenor': '0'
    }, follow_redirects=True)
    assert perf_add_inst.status_code == 200
    assert b'Netflix 4K' in perf_add_inst.data

    # 8d. Pay Installment
    with client.application.app_context():
        db = get_db()
        inst_row = db.execute("SELECT id FROM recurring_installments WHERE user_id = ? AND name = 'Netflix 4K'", (user_id,)).fetchone()

    perf_pay_inst = client.post('/financial_performance', data={
        'action': 'pay_installment',
        'inst_id': inst_row['id'],
        'account_name': bca_id,
        'amount_paid': '186.000',
        'notes': 'Langganan Oktober'
    }, follow_redirects=True)
    assert perf_pay_inst.status_code == 200

    # 9. Performance Page Rendering
    perf_page = client.get('/financial_performance')
    assert perf_page.status_code == 200
    assert b'Netflix 4K' in perf_page.data
    assert b'Budi' in perf_page.data

    # 10. Settings Page Rendering
    settings_page = client.get('/settings')
    assert settings_page.status_code == 200
    assert b'Profile' in settings_page.data

    # 11. Recalculate Balances Consistency Test
    with client.application.app_context():
        db = get_db()
        from routes.dashboard import recalculate_account_balances
        recalculate_account_balances(db, user_id)
        bca_after = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (bca_id,)).fetchone()
        cash_after = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (cash_id,)).fetchone()
        cc_after = db.execute("SELECT current_balance FROM accounts WHERE id = ?", (cc_id,)).fetchone()
        
        # Verify no divergence
        assert bca_after['current_balance'] == 3000000.0 - 186000.0
        assert cash_after['current_balance'] == 650000.0
        assert cc_after['current_balance'] == -200000.0
