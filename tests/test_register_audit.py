import re
import uuid

from utils import get_db


def _uid():
    return uuid.uuid4().hex[:8]


def _register(client, username, email, password="Password123!", fullname="Test User", **kw):
    return client.post('/register', data={
        'fullname': fullname,
        'username': username,
        'email': email,
        'password': password,
    }, follow_redirects=True, **kw)


def test_username_charset_and_length(client):
    uid = _uid()
    # '@' in username is rejected (it could shadow another user's email at login)
    res = _register(client, f"a@b{uid}.com", f"x{uid}@example.com")
    assert b'hanya boleh berisi huruf' in res.data

    # Other symbols rejected
    res = _register(client, f"bad-{uid}", f"y{uid}@example.com")
    assert b'hanya boleh berisi huruf' in res.data

    # Tab / inner whitespace counts as a space
    res = _register(client, f"bad\t{uid}", f"z{uid}@example.com")
    assert b'tidak boleh mengandung spasi' in res.data

    # Too long
    res = _register(client, "u" * 31, f"w{uid}@example.com")
    assert b'maksimal 30 karakter' in res.data

    # Dots and underscores are fine
    res = _register(client, f"ok.user_{uid}", f"ok{uid}@example.com")
    assert b'Pendaftaran akun berhasil' in res.data


def test_email_format_edge_cases(client):
    uid = _uid()
    for bad in ["@example.com", "a@@example.com", "a b@example.com", "a@example", "a@example.c"]:
        res = _register(client, f"em_{uid}", bad)
        assert b'Format alamat email tidak valid' in res.data, bad


def test_password_and_fullname_rules(client):
    uid = _uid()
    res = _register(client, f"pw_{uid}", f"pw{uid}@example.com", password="       ")
    assert b'Semua bidang wajib diisi' in res.data

    res = _register(client, f"pw_{uid}", f"pw{uid}@example.com", password="x" * 129)
    assert b'Password maksimal 128 karakter' in res.data

    res = _register(client, f"fn_{uid}", f"fn{uid}@example.com", fullname="A" * 101)
    assert b'Nama lengkap maksimal 100 karakter' in res.data

    # Inner whitespace in full name is collapsed
    res = _register(client, f"fn_{uid}", f"fn{uid}@example.com", fullname="  Budi     Santoso ")
    assert b'Pendaftaran akun berhasil' in res.data
    with client.application.app_context():
        row = get_db().execute("SELECT fullname FROM users WHERE username = ?", (f"fn_{uid}",)).fetchone()
        assert row['fullname'] == "Budi Santoso"


def test_email_cannot_match_legacy_username_and_login_still_works(client):
    """Legacy rows may have a username that looks like an email. A new user must not be able to
    register that email, and if such a collision already exists the real owner can still log in."""
    uid = _uid()
    legacy_name = f"legacy{uid}@example.com"
    with client.application.app_context():
        db = get_db()
        from werkzeug.security import generate_password_hash
        db.execute("INSERT INTO users (fullname, username, email, password) VALUES (?, ?, ?, ?)",
                   ("Legacy", legacy_name, f"legacyreal{uid}@example.com", generate_password_hash("LegacyPass1!")))
        db.commit()

    # Register with that string as email -> blocked
    res = _register(client, f"newbie_{uid}", legacy_name.upper())
    assert b'Alamat email sudah terdaftar' in res.data

    # Simulate pre-existing collision: another user whose EMAIL equals the legacy username
    with client.application.app_context():
        db = get_db()
        from werkzeug.security import generate_password_hash
        db.execute("INSERT INTO users (fullname, username, email, password) VALUES (?, ?, ?, ?)",
                   ("Owner", f"owner_{uid}", legacy_name, generate_password_hash("OwnerPass1!")))
        db.commit()

    # Owner logs in with their email even though an older row has the same string as username
    res = client.post('/login', data={'username': legacy_name, 'password': 'OwnerPass1!'})
    assert res.status_code == 302 and 'dashboard' in res.location
    with client.session_transaction() as sess:
        assert sess['username'] == f"owner_{uid}"


def test_logged_in_user_is_redirected_away_from_register(client):
    uid = _uid()
    _register(client, f"in_{uid}", f"in{uid}@example.com")
    client.post('/login', data={'username': f"in_{uid}", 'password': 'Password123!'})

    res = client.get('/register')
    assert res.status_code == 302 and 'dashboard' in res.location

    res = client.post('/register', data={'fullname': 'X', 'username': f"second_{uid}",
                                         'email': f"second{uid}@example.com", 'password': 'Password123!'})
    assert res.status_code == 302
    with client.application.app_context():
        assert get_db().execute("SELECT id FROM users WHERE username = ?", (f"second_{uid}",)).fetchone() is None


def test_register_with_csrf_enabled(app):
    """Real browser-like flow with CSRF protection on."""
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        client = app.test_client()
        uid = _uid()
        form = {'fullname': 'Csrf User', 'username': f"csrf_{uid}",
                'email': f"csrf{uid}@example.com", 'password': 'Password123!'}

        # Missing/invalid token -> form re-rendered with friendly message and typed values preserved
        res = client.post('/register', data=dict(form, csrf_token='bogus'))
        assert res.status_code == 400
        assert b'Sesi formulir sudah kedaluwarsa' in res.data
        assert f'value="csrf_{uid}"'.encode() in res.data

        # Token from the page -> succeeds
        page = client.get('/register')
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        res = client.post('/register', data=dict(form, csrf_token=token), follow_redirects=True)
        assert b'Pendaftaran akun berhasil' in res.data
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_register_page_has_double_submit_guard(client):
    html = client.get('/register').data
    assert b'submitting' in html and b':disabled="submitting"' in html
    assert b'autocomplete="new-password"' in html
    assert b'autocapitalize="none"' in html
