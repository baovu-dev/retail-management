import pytest
from unittest.mock import patch, MagicMock
from backend.app import app, analyse_sentiment

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_loads(client):
    response = client.get('/')
    assert response.status_code == 200

def test_submit_page_loads(client):
    response = client.get('/submit')
    assert response.status_code == 200

def test_submit_page_with_product_context(client):
    response = client.get('/submit?product_id=101&customer_id=1')
    assert response.status_code == 200
    assert b'Product #101' in response.data

def test_view_reviews_requires_product_id(client):
    response = client.get('/reviews/view')
    assert b'Enter a product ID' in response.data

def test_delete_review_form_returns_empty_response(client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"deleted": 1}
 
    with patch('app.requests.delete', return_value=mock_response) as mock_delete:
        response = client.delete('/reviews/delete-form/1')
        assert response.status_code == 200
        assert response.data == b''
        mock_delete.assert_called_once()
 
def test_analyse_sentiment_returns_zero_for_empty_comment():
    assert analyse_sentiment("") == 0.0

def test_analyse_sentiment_returns_zero_on_ollama_failure():
    with patch('app.requests.post', side_effect=Exception("connection failed")):
        assert analyse_sentiment("great product") == 0.0
