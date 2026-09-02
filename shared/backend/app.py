from flask import Flask, jsonify, render_template
from flask_cors import CORS
import requests

app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/css', static_url_path='/static')
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
 
 
@app.route('/staff_dashboard')
def staff_dashboard():
    return render_template('staff_dashboard.html')
 
 
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