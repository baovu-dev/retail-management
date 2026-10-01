try:
    from backend.prompt_loader import load_prompt
except ModuleNotFoundError:
    from prompt_loader import load_prompt

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import os

app = Flask(
    __name__,
    template_folder='../frontend/templates',
    static_folder='../frontend/css',
    static_url_path='/static'
)
CORS(app)

DATABASE_URL = os.getenv('DATABASE_URL', 'http://localhost:6003')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1:8b')


def call_ollama(prompt):
    try:
        response = requests.post(
            OLLAMA_URL,
            json={'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False},
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get('response', '').strip()
    except requests.exceptions.RequestException:
        return None


@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception:
        return jsonify({'service': 'student-3-customer-backend', 'status': 'running'})


@app.route('/customers', methods=['GET'])
def get_all_customers():
    try:
        response = requests.get(f'{DATABASE_URL}/customers', timeout=5)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({'error': 'Customer database service is unavailable'}), 503
    except ValueError:
        return jsonify({'error': 'Invalid response from customer database service'}), 502


@app.route('/customers/<int:customer_id>', methods=['GET'])
def get_customer(customer_id):
    try:
        response = requests.get(f'{DATABASE_URL}/customers/{customer_id}', timeout=5)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({'error': 'Customer database service is unavailable'}), 503
    except ValueError:
        return jsonify({'error': 'Invalid response from customer database service'}), 502


@app.route('/customers', methods=['POST'])
def create_customer():
    data = request.get_json(silent=True) or {}


    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not first_name or not last_name or not email:
        return jsonify({
            'error': 'First name, last name and email are required'
        }), 400

    if len(password) < 8:
        return jsonify({
            'error': 'Password must be at least 8 characters'
        }), 400

    password_hash = generate_password_hash(password)

    response = requests.post(
        f"{DATABASE_URL}/customers",
        json={
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone,
            'email': email,
            'password_hash': password_hash,
            'status': 'Active'
        }
    )

    return jsonify(response.json()), response.status_code


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({
            'error': 'Email and password are required'
        }), 400

    response = requests.get(
        f"{DATABASE_URL}/customers/by-email",
        params={
            'email': email
        }
    )

    if response.status_code == 404:
        return jsonify({
            'error': 'Invalid email or password'
        }), 401

    if response.status_code != 200:
        return jsonify({
            'error': 'Unable to authenticate customer'
        }), response.status_code

    customer = response.json()

    if not check_password_hash(
        customer['password_hash'],
        password
    ):
        return jsonify({
            'error': 'Invalid email or password'
        }), 401

    if customer['status'] != 'Active':
        return jsonify({
            'error': 'This account is inactive'
        }), 403

    return jsonify({
        'message': 'Login successful',
        'customer_id': customer['customer_id'],
        'first_name': customer['first_name'],
        'last_name': customer['last_name'],
        'email': customer['email']
    })

@app.route('/customers/<int:customer_id>', methods=['PUT'])
def update_customer(customer_id):
    data = request.get_json(silent=True) or {}
    try:
        response = requests.put(f'{DATABASE_URL}/customers/{customer_id}', json=data, timeout=5)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({'error': 'Customer database service is unavailable'}), 503
    except ValueError:
        return jsonify({'error': 'Invalid response from customer database service'}), 502


@app.route('/customers/<int:customer_id>/password', methods=['PUT'])
def change_password(customer_id):
    data = request.get_json(silent=True) or {}

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password:
        return jsonify({
            'error': 'Current password is required'
        }), 400

    if len(new_password) < 8:
        return jsonify({
            'error': 'New password must be at least 8 characters'
        }), 400

    customer_response = requests.get(
        f"{DATABASE_URL}/customers/{customer_id}/auth"
    )

    if customer_response.status_code != 200:
        return jsonify({
            'error': 'Customer not found'
        }), 404

    customer = customer_response.json()

    if not check_password_hash(
        customer['password_hash'],
        current_password
    ):
        return jsonify({
            'error': 'Current password is incorrect'
        }), 401

    new_password_hash = generate_password_hash(
        new_password
    )

    response = requests.put(
        f"{DATABASE_URL}/customers/{customer_id}/password",
        json={
            'password_hash': new_password_hash
        }
    )

    return jsonify(
        response.json()
    ), response.status_code

@app.route('/customers/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    try:
        response = requests.delete(f'{DATABASE_URL}/customers/{customer_id}', timeout=5)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({'error': 'Customer database service is unavailable'}), 503
    except ValueError:
        return jsonify({'error': 'Invalid response from customer database service'}), 502


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not first_name or not last_name or not email or not password:
        return jsonify({'error': 'First name, last name, email and password are required'}), 400

    payload = {
        'first_name': first_name,
        'last_name': last_name,
        'phone': phone,
        'email': email,
        'password_hash': generate_password_hash(password),
        'status': 'Active',
    }

    try:
        response = requests.post(f'{DATABASE_URL}/auth/register', json=payload, timeout=5)
    except requests.exceptions.RequestException:
        return jsonify({'error': 'Customer database service is unavailable'}), 503

    try:
        result = response.json()
    except ValueError:
        result = {'error': 'Invalid response from customer database service'}

    return jsonify(result), response.status_code


@app.route('/account-assistant', methods=['POST'])
def account_assistant():
    data = request.get_json(silent=True) or {}
    customer_id = data.get('customer_id')
    question = data.get('question', '').strip()

    if not question:
        return jsonify({'error': 'Question is required'}), 400

    customer_context = 'No customer context available.'
    if customer_id is not None:
        try:
            response = requests.get(f'{DATABASE_URL}/customers/{customer_id}', timeout=5)
            if response.status_code == 200:
                customer = response.json()
                customer_context = (
                    f"Customer ID: {customer.get('customer_id')}\n"
                    f"Name: {customer.get('first_name', '')} {customer.get('last_name', '')}\n"
                    f"Email: {customer.get('email', '')}\n"
                    f"Phone: {customer.get('phone', '')}\n"
                    f"Status: {customer.get('status', '')}"
                )
        except requests.exceptions.RequestException:
            pass

    try:
        base_prompt = load_prompt('account_assistant_prompt.txt')
    except Exception:
        base_prompt = 'You are a helpful customer account assistant. Answer using only the supplied customer context.'

    prompt = f'{base_prompt}\n\nCustomer context:\n{customer_context}\n\nQuestion:\n{question}'
    answer = call_ollama(prompt)
    if not answer:
        answer = 'The AI assistant is currently unavailable. Please try again later.'

    return jsonify({'answer': answer})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)
