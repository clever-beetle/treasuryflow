def test_login_page_status(client):
    response = client.get('/login')
    assert response.status_code == 200

def test_register_page_status(client):
    response = client.get('/register')
    assert response.status_code == 200
