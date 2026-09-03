import pytest
from backend.app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_loads(client):
    response = client.get('/')
    assert response.status_code == 200

def test_customer_loads(client):
    response = client.get('/customers/1')
    assert response.status_code == 200

def test_customers_load(client):
    response = client.get('/customers')
    assert response.status_code == 200

def test_account_assistant_requires_question(client):
    response = client.post(
        '/account-assistant',
        json={'customer_id': 1}
    )
    assert response.status_code == 400