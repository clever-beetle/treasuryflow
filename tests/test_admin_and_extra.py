import pytest
import uuid
import os

def test_admin_and_extra_routes(client):
    test_id = uuid.uuid4().hex[:8]
    username = f"user_adm_{test_id}"
    password = "Password123!"

    client.post('/register', data={
        'fullname': 'Admin Extra User',
        'username': username,
        'email': f"{username}@test.com",
        'password': password,
        'confirm_password': password
    }, follow_redirects=True)

    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # 1. Dev Console without secret key should return 403
    os.environ['DEV_SECRET_KEY'] = 'supersecretkey123'
    dev_fail = client.get('/dev-console?key=wrongkey')
    assert dev_fail.status_code == 403

    # 2. Dev Console with secret key should return 200
    dev_ok = client.get('/dev-console?key=supersecretkey123')
    assert dev_ok.status_code == 200
    assert b'users' in dev_ok.data

    # 3. Leaderboard route (removed - should return 404)
    lb_res = client.get('/leaderboard')
    assert lb_res.status_code == 404

    # 4. Tools route
    tools_res = client.get('/tools')
    assert tools_res.status_code == 200

    # 5. Kiosk route
    kiosk_res = client.get('/kiosk')
    assert kiosk_res.status_code == 200

    # 6. Notifications mark as read
    notif_res = client.post('/notifications/read')
    assert notif_res.status_code == 200
    assert notif_res.json == {'status': 'success'}

    # 7. AI Chat API
    chat_res = client.post('/api/chat', json={'message': 'berapa saldo saya?'})
    assert chat_res.status_code == 200
    assert 'reply' in chat_res.json

    # 8. Calendar route and API
    cal_res = client.get('/calendar')
    assert cal_res.status_code == 200
    assert b'Kalender Finansial' in cal_res.data

    # Add a recurring installment to test calendar projection
    client.post('/financial_performance', data={
        'action': 'add_installment',
        'name': 'Netflix Subscription',
        'amount_per_cycle': '186.000',
        'due_day_of_month': '15',
        'is_temporary_tenor': '0'
    }, follow_redirects=True)

    cal_api = client.get('/api/calendar_events')
    assert cal_api.status_code == 200
    events = cal_api.json
    assert any('Netflix Subscription' in e['title'] for e in events)
