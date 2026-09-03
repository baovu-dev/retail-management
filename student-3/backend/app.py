try:
    from backend.prompt_loader import load_prompt
except ModuleNotFoundError:
    from prompt_loader import load_prompt
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

def call_ollama(prompt):
    response = requests.post(
        OLLAMA_URL,
        json={
            'model': OLLAMA_MODEL,
            'prompt': prompt,
            'stream': False
        }
    )

    return response.json()['response']

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

    prompt_template = load_prompt(
    'account_assistant_prompt.txt'
    )

    prompt = prompt_template.format(
    first_name=customer['first_name'],
    last_name=customer['last_name'],
    email=customer['email'],
    phone=customer['phone'],
    status=customer['status'],
    question=question
    )


    print("PLAN: Prepare an account-management answer.")

    answer = call_ollama(prompt)
    print("ACT: Generated initial AI response.")

    if answer and len(answer.strip()) > 10:
        print("OBSERVE: Response is valid.")
    else:
        print("OBSERVE: Response is too short or empty.")

        adapted_prompt = prompt + """

The previous response was not useful.
Answer the customer's question clearly and directly.
Only use functionality that exists in KICKLAB.
"""

        answer = call_ollama(adapted_prompt)
        print("ADAPT: Generated an improved response.")

    return jsonify({
        'response': answer
    })

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5003,
        debug=True
    )