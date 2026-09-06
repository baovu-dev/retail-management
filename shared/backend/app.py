import os

from flask import Flask, jsonify, render_template, request, redirect, url_for
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

REVIEWS_API = "http://localhost:5001"
PRODUCTS_API = "http://localhost:5002"
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')

    if not email:
        return render_template('login.html', error='Please enter your email address.'), 400
    if not password:
        return render_template('login.html', error='Please enter your password.', email=email), 400

    return redirect(url_for('customer_home'))

@app.route('/staff_dashboard')
def staff_dashboard():
    return render_template('staff_dashboard.html')

@app.route('/create-account')
def create_account():
    return render_template('create_account.html')

@app.route('/dashboard/stats', methods=['GET'])
def dashboard_stats():
    stats = dict(FALLBACK_STATS)

    try:
        orders = requests.get(f"{ORDERS_API}/api/orders/count", timeout=3).json()
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
