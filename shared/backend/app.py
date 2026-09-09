import os

from flask import Flask, jsonify, render_template, request, redirect, session
from flask_cors import CORS
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),
    static_folder=os.path.join(FRONTEND_DIR, "css"),
    static_url_path="/css",
)
CORS(app)

app.secret_key = "kicklab-session-key"

REVIEWS_API = "http://localhost:5001"
PRODUCTS_API = "http://localhost:5002"
CUSTOMERS_API = "http://localhost:5003"
ORDERS_API = "http://localhost:5004"

# used when a teammate's service isn't up yet or the endpoint doesn't exist
FALLBACK_STATS = {
    "total_orders": 0,
    "avg_rating": 0,
    "flagged_reviews": 0,
    "active_products": 0
}


@app.route('/')
def customer_home():
    return render_template('Index.html')

@app.route('/shop')
def shop():
    return render_template('shop.html')

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'GET':
        return render_template('login.html')

    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')

    if not email:
        return render_template(
            'login.html',
            error='Please enter your email address.'
        ), 400

    if not password:
        return render_template(
            'login.html',
            error='Please enter your password.',
            email=email
        ), 400

    try:
        response = requests.post(
            f"{CUSTOMERS_API}/login",
            json={
                'email': email,
                'password': password
            },
            timeout=5
        )

    except requests.exceptions.RequestException:
        return render_template(
            'login.html',
            error='Customer account service is unavailable.',
            email=email
        ), 503

    data = response.json()

    if response.status_code != 200:
        return render_template(
            'login.html',
            error=data.get('error', 'Login failed.'),
            email=email
        ), response.status_code

    customer_id = data['customer_id']

    session['customer_id'] = customer_id

    return redirect(
        f"http://localhost:5003/?customer_id={customer_id}"
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/staff_dashboard')
def staff_dashboard():
    return render_template('staff_dashboard.html')

@app.route('/create-account', methods=['GET', 'POST'])
def create_account():

    if request.method =='GET':
        return render_template('create_account.html')

    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')

    try:
        response = requests.post(
            f"{CUSTOMERS_API}/customers",
            json={
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'password': password
            },
            timeout=5
        )

    except requests.exceptions.RequestException:
        return render_template(
            'create_account.html'
        ), 503

    data = response.json()

    if response.status_code != 201:
        return render_template(
            'create_account.html'
        ), response.status_code

    return redirect('/login')

@app.route('/dashboard/stats', methods=['GET'])
def dashboard_stats():
    stats = dict(FALLBACK_STATS)

    try:
        orders = requests.get(f"{ORDERS_API}/orders/count", timeout=3).json()
        stats["total_orders"] = orders.get("count", stats["total_orders"])
    except requests.exceptions.RequestException:
        pass

    try:
        reviews = requests.get(f"{REVIEWS_API}/reviews/stats", timeout=3).json()
        stats["avg_rating"] = reviews.get("average_rating", stats["avg_rating"])
        stats["flagged_reviews"] = reviews.get("flagged_count", stats["flagged_reviews"])
    except requests.exceptions.RequestException:
        pass

    try:
        products = requests.get(f"{PRODUCTS_API}/products/count", timeout=3).json()
        stats["active_products"] = products.get("count", stats["active_products"])
    except requests.exceptions.RequestException:
        pass

    return jsonify(stats)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
