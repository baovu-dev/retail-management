from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import requests
import os

app = Flask(
    __name__,
    template_folder='../frontend/templates',
    static_folder='../frontend/css',
    static_url_path='/static'
)

CORS(app)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "http://localhost:6003"
)

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.1:8b"
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/customers', methods=['GET'])
def get_all_customers():
    response = requests.get(
        f"{DATABASE_URL}/customers"
    )

    return jsonify(response.json()), response.status_code

@app.route('/customers/<int:customer_id>', methods=['GET'])
def get_customer(customer_id):
    response = requests.get(
        f"{DATABASE_URL}/customers/{customer_id}"
    )

    return jsonify(response.json()), response.status_code

@app.route('/customers', methods=['POST'])
def create_customer():
    data = request.json

    response = requests.post(
        f"{DATABASE_URL}/customers",
        json=data
    )

    return jsonify(response.json()), response.status_code

@app.route('/customers/<int:customer_id>', methods=['PUT'])
def update_customer(customer_id):
    data = request.json

    response = requests.put(
        f"{DATABASE_URL}/customers/{customer_id}",
        json=data
    )

    return jsonify(response.json()), response.status_code

@app.route('/customers/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    response = requests.delete(
        f"{DATABASE_URL}/customers/{customer_id}"
    )

    return jsonify(response.json()), response.status_code

@app.route('/account-assistant', methods=['POST'])
def account_assistant():
    data = request.json

    customer_id = data.get('customer_id')
    question = data.get('question')

    if not customer_id or not question:
        return jsonify({
            'error': 'Customer ID and question are required'
        }), 400

    customer_response = requests.get(
        f"{DATABASE_URL}/customers/{customer_id}"
    )

    if customer_response.status_code != 200:
        return jsonify({
            'error': 'Customer not found'
        }), 404

    customer = customer_response.json()

    prompt = f"""
    You are the Customer Account Assistant.

    Help customers with questions about managing their account.

    Customer information:
    Name: {customer['first_name']} {customer['last_name']}
    Email: {customer['email']}
    Phone: {customer['phone']}
    Status: {customer['status']}

    The account page currently allows customers to:
    - View their account details
    - Edit their first name
    - Edit their last name
    - Edit their email
    - Edit their phone number
    - Delete their account

    Customer question:
    {question}

    Instructions:
    - Give a short and clear answer.
    - Only describe features listed above.
    - Do not invent buttons, pages, menus, contact details or functionality.
    - Do not treat the customer's personal information as KICKLAB contact information.
    - If the requested feature is unavailable, clearly say that it is not available.
    """

    ollama_response = requests.post(
        OLLAMA_URL,
        json={
            'model': OLLAMA_MODEL,
            'prompt': prompt,
            'stream': False
        }
    )

    result = ollama_response.json()

    return jsonify({
        'response': result['response']
    })

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5003,
        debug=True
    )