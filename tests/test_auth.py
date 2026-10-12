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

