def test_login_page_status(client):
    response = client.get('/login')
    assert response.status_code == 200

def test_register_page_status(client):
    response = client.get('/register')
    assert response.status_code == 200

def test_register_validation_and_edge_cases(client):
    import uuid
    uid = uuid.uuid4().hex[:6]
    base_user = f"reguser_{uid}"
    base_email = f"{base_user}@example.com"

    # 1. Valid registration with spaces around fields
    res = client.post('/register', data={
        'fullname': '  Budi Santoso  ',
        'username': f'  {base_user}  ',
        'email': f'  {base_email}  ',
        'password': 'Password123!'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Pendaftaran akun berhasil' in res.data or b'login' in res.request.path

    # 2. Duplicate username (case-insensitive)
    dup_user_res = client.post('/register', data={
        'fullname': 'Another Name',
        'username': base_user.upper(),
        'email': f"other_{uid}@example.com",
        'password': 'Password123!'
    }, follow_redirects=True)
    assert b'Username sudah digunakan' in dup_user_res.data

    # 3. Duplicate email (case-insensitive)
    dup_email_res = client.post('/register', data={
        'fullname': 'Another Name',
        'username': f"unique_{uid}",
        'email': base_email.upper(),
        'password': 'Password123!'
    }, follow_redirects=True)
    assert b'Alamat email sudah terdaftar' in dup_email_res.data

    # 4. Username with spaces
    space_user_res = client.post('/register', data={
        'fullname': 'Name',
        'username': 'user name with space',
        'email': f"space_{uid}@example.com",
        'password': 'Password123!'
    }, follow_redirects=True)
    assert b'tidak boleh mengandung spasi' in space_user_res.data

    # 5. Invalid email format
    bad_email_res = client.post('/register', data={
        'fullname': 'Name',
        'username': f"bademail_{uid}",
        'email': 'not-an-email',
        'password': 'Password123!'
    }, follow_redirects=True)
    assert b'Format alamat email tidak valid' in bad_email_res.data

    # 6. Password too short (< 6)
    short_pw_res = client.post('/register', data={
        'fullname': 'Name',
        'username': f"shortpw_{uid}",
        'email': f"short_{uid}@example.com",
        'password': '123'
    }, follow_redirects=True)
    assert b'Password minimal harus 6 karakter' in short_pw_res.data


def test_login_validation_and_features(client):
    import uuid
    uid = uuid.uuid4().hex[:6]
    username = f"loguser_{uid}"
    email = f"{username}@example.com"
    password = "SecretPassword123!"

    # Register user first
    reg_res = client.post('/register', data={
        'fullname': 'Login Tester',
        'username': username,
        'email': email,
        'password': password
    }, follow_redirects=True)
    assert reg_res.status_code == 200

    # 1. Login with normal username
    res1 = client.post('/login', data={'username': username, 'password': password})
    assert res1.status_code == 302
    assert res1.location == '/dashboard' or res1.location.endswith('/dashboard')

    # 2. Login with uppercase username (case-insensitive)
    res2 = client.post('/login', data={'username': username.upper(), 'password': password})
    assert res2.status_code == 302

    # 3. Login with email (uppercase) and surrounding spaces
    res3 = client.post('/login', data={'username': f"  {email.upper()}  ", 'password': password})
    assert res3.status_code == 302

    # 4. Login with wrong password
    res_wrong = client.post('/login', data={'username': username, 'password': 'wrongpassword'}, follow_redirects=True)
    assert res_wrong.status_code == 200
    assert b'Username/email atau password salah' in res_wrong.data

    # 5. Login with empty credentials
    res_empty = client.post('/login', data={'username': '', 'password': ''}, follow_redirects=True)
    assert res_empty.status_code == 200
    assert b'Username/email dan password wajib diisi' in res_empty.data

    # 6. Login with safe next redirect
    res_next = client.post('/login?next=/settings', data={'username': username, 'password': password})
    assert res_next.status_code == 302
    assert res_next.location == '/settings'

    # 7. Login with open redirect attack should fallback to dashboard
    res_open_red = client.post('/login?next=//malicious-site.com', data={'username': username, 'password': password})
    assert res_open_red.status_code == 302
    assert res_open_red.location != '//malicious-site.com'
    assert 'dashboard' in res_open_red.location


def test_logout_flow(client):
    import uuid
    uid = uuid.uuid4().hex[:6]
    username = f"logoutuser_{uid}"
    email = f"{username}@example.com"
    password = "SecretPassword123!"

    # Register and login
    client.post('/register', data={
        'fullname': 'Logout Tester',
        'username': username,
        'email': email,
        'password': password
    }, follow_redirects=True)
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

    # Verify session active by accessing settings
    set_res = client.get('/settings')
    assert set_res.status_code == 200

    # Logout
    logout_res = client.get('/logout', follow_redirects=True)
    assert logout_res.status_code == 200
    assert b'berhasil keluar' in logout_res.data or b'login' in logout_res.request.path

    # Verify session is dead: accessing settings now redirects to login
    protected_res = client.get('/settings')
    assert protected_res.status_code == 302
    assert 'login' in protected_res.location


