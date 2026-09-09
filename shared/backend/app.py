import os

from flask import Flask, jsonify, render_template, request, redirect, url_for, session
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

app.secret_key = os.getenv("SECRET_KEY", "kicklab-dev-secret-key")
CORS(app)


REVIEWS_API = os.getenv("REVIEWS_API", "http://localhost:5001")
PRODUCTS_API = os.getenv("PRODUCTS_API", "http://localhost:5002")
CUSTOMERS_API = os.getenv("CUSTOMERS_API", "http://localhost:5003")
ORDERS_API = os.getenv("ORDERS_API", "http://localhost:5004")


STAFF_EMAIL = os.getenv("STAFF_EMAIL", "admin@kicklab.com")
STAFF_PASSWORD = os.getenv("STAFF_PASSWORD", "Admin1234")


FALLBACK_STATS = {
    "total_orders": 0,
    "avg_rating": 0,
    "flagged_reviews": 0,
    "active_products": 0
}


@app.route("/")
def customer_home():
    return render_template(
        "Index.html",
        customer=session.get("customer")
    )

@app.route("/shop")
def shop():
    products = []
    error = None

    try:
        response = requests.get(
            f"{PRODUCTS_API}/products",
            timeout=5
        )

        if response.ok:
            products = response.json()
        else:
            error = "Unable to load products."

    except (requests.exceptions.RequestException, ValueError):
        error = "Product service is currently unavailable."

    return render_template(
        "shop.html",
        products=products,
        customer=session.get("customer"),
        error=error
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email:
        return render_template(
            "login.html",
            error="Please enter your email address."
        ), 400

    if not password:
        return render_template(
            "login.html",
            error="Please enter your password.",
            email=email
        ), 400

    if email.lower() == STAFF_EMAIL.lower():
        if password != STAFF_PASSWORD:
            return render_template(
                "login.html",
                error="Invalid email or password.",
                email=email
            ), 401

        session.clear()
        session["is_staff"] = True
        session["staff_email"] = email

        return redirect(url_for("staff_dashboard"))

    try:
        response = requests.post(
            f"{CUSTOMERS_API}/login",
            json={
                "email": email,
                "password": password
            },
            timeout=5
        )

    except requests.exceptions.RequestException:
        return render_template(
            "login.html",
            error="Customer account service is currently unavailable.",
            email=email
        ), 503

    try:
        result = response.json()

    except ValueError:
        return render_template(
            "login.html",
            error="Invalid response from customer account service.",
            email=email
        ), 502

    if response.status_code != 200:
        return render_template(
            "login.html",
            error=result.get("error", "Invalid email or password."),
            email=email
        ), response.status_code

    customer = result.get("customer")

    if not customer:
        return render_template(
            "login.html",
            error="Customer account information was not returned.",
            email=email
        ), 502

    session.clear()
    session["customer"] = customer

    return redirect(url_for("customer_home"))

@app.route("/order/<int:product_id>")
def order_product(product_id):
    customer = session.get("customer")

    if not customer:
        return redirect(url_for("login"))

    try:
        response = requests.get(
            f"{PRODUCTS_API}/products/{product_id}",
            timeout=5
        )

        if not response.ok:
            return redirect(url_for("shop"))

        product = response.json()

    except (requests.exceptions.RequestException, ValueError):
        return redirect(url_for("shop"))

    return render_template(
        "place_order.html",
        product=product,
        customer=customer
    )


@app.route("/order/<int:product_id>/place", methods=["POST"])
def place_order(product_id):
    customer = session.get("customer")

    if not customer:
        return redirect(url_for("login"))

    try:
        quantity = int(request.form.get("quantity", 1))

        if quantity < 1:
            quantity = 1

    except ValueError:
        quantity = 1

    try:
        product_response = requests.get(
            f"{PRODUCTS_API}/products/{product_id}",
            timeout=5
        )

        if not product_response.ok:
            return render_template(
                "place_order.html",
                product=None,
                customer=customer,
                error="Product could not be found."
            ), 404

        product = product_response.json()

        order_response = requests.post(
            f"{ORDERS_API}/api/orders",
            json={
                "customer_id": customer["customer_id"],
                "items": [
                    {
                        "product_id": product["product_id"],
                        "quantity": quantity,
                        "unit_price": product["price"]
                    }
                ]
            },
            timeout=5
        )

        result = order_response.json()

        if order_response.status_code != 201:
            return render_template(
                "place_order.html",
                product=product,
                customer=customer,
                error=result.get(
                    "error",
                    "Unable to place order."
                )
            ), order_response.status_code

    except (requests.exceptions.RequestException, ValueError, KeyError):
        return render_template(
            "place_order.html",
            product=locals().get("product"),
            customer=customer,
            error="Order service is currently unavailable."
        ), 503

    return redirect(
        url_for(
            "order_success",
            order_id=result["order_id"]
        )
    )


@app.route("/order-success/<int:order_id>")
def order_success(order_id):
    customer = session.get("customer")

    if not customer:
        return redirect(url_for("login"))

    try:
        response = requests.get(
            f"{ORDERS_API}/api/orders/{order_id}",
            timeout=5
        )

        order = (
            response.json()
            if response.ok
            else None
        )

    except (requests.exceptions.RequestException, ValueError):
        order = None

    return render_template(
        "order_success.html",
        order=order,
        customer=customer
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("customer_home"))


@app.route("/create-account", methods=["GET", "POST"])
def create_account():
    if request.method == "GET":
        return render_template("create_account.html")

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "email": email
    }

    if not first_name or not last_name or not email or not password:
        return render_template(
            "create_account.html",
            error="First name, last name, email and password are required.",
            form_data=form_data
        ), 400

    if confirm_password and password != confirm_password:
        return render_template(
            "create_account.html",
            error="Passwords do not match.",
            form_data=form_data
        ), 400

    try:
        response = requests.post(
            f"{CUSTOMERS_API}/register",
            json={
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "email": email,
                "password": password
            },
            timeout=5
        )

    except requests.exceptions.RequestException:
        return render_template(
            "create_account.html",
            error="Customer account service is currently unavailable.",
            form_data=form_data
        ), 503

    try:
        result = response.json()

    except ValueError:
        return render_template(
            "create_account.html",
            error="Invalid response from customer account service.",
            form_data=form_data
        ), 502

    if response.status_code not in (200, 201):
        return render_template(
            "create_account.html",
            error=result.get("error", "Unable to create account."),
            form_data=form_data
        ), response.status_code

    customer = result.get("customer")

    if not customer:
        try:
            login_response = requests.post(
                f"{CUSTOMERS_API}/login",
                json={
                    "email": email,
                    "password": password
                },
                timeout=5
            )

            login_result = login_response.json()

            if login_response.status_code != 200:
                return render_template(
                    "login.html",
                    message="Account created successfully. Please log in.",
                    email=email
                )

            customer = login_result.get("customer")

        except (requests.exceptions.RequestException, ValueError):
            return render_template(
                "login.html",
                message="Account created successfully. Please log in.",
                email=email
            )

    if not customer:
        return render_template(
            "login.html",
            message="Account created successfully. Please log in.",
            email=email
        )

    session.clear()
    session["customer"] = customer

    return redirect(url_for("customer_home"))


@app.route("/staff-login", methods=["GET", "POST"])
def staff_login():
    if request.method == "GET":
        if session.get("is_staff"):
            return redirect(url_for("staff_dashboard"))

        return render_template("staff_login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template(
            "staff_login.html",
            error="Please enter both email and password.",
            email=email
        ), 400

    if email != STAFF_EMAIL or password != STAFF_PASSWORD:
        return render_template(
            "staff_login.html",
            error="Invalid staff email or password.",
            email=email
        ), 401

    session.clear()
    session["is_staff"] = True
    session["staff_email"] = email

    return redirect(url_for("staff_dashboard"))


@app.route("/staff-logout")
def staff_logout():
    session.clear()
    return redirect(url_for("staff_login"))


@app.route("/staff_dashboard")
def staff_dashboard():
    if not session.get("is_staff"):
        return redirect(url_for("staff_login"))

    return render_template(
        "staff_dashboard.html",
        staff_email=session.get("staff_email")
    )


@app.route("/dashboard/stats", methods=["GET"])
def dashboard_stats():
    if not session.get("is_staff"):
        return jsonify({
            "error": "Staff authentication required."
        }), 401

    stats = dict(FALLBACK_STATS)

    try:
        response = requests.get(
            f"{ORDERS_API}/api/orders/count",
            timeout=3
        )

        if response.ok:
            orders = response.json()
            stats["total_orders"] = orders.get(
                "count",
                stats["total_orders"]
            )

    except (requests.exceptions.RequestException, ValueError):
        pass

    try:
        response = requests.get(
            f"{REVIEWS_API}/reviews/stats",
            timeout=3
        )

        if response.ok:
            reviews = response.json()

            stats["avg_rating"] = reviews.get(
                "average_rating",
                stats["avg_rating"]
            )

            stats["flagged_reviews"] = reviews.get(
                "flagged_count",
                stats["flagged_reviews"]
            )

    except (requests.exceptions.RequestException, ValueError):
        pass

    try:
        response = requests.get(
            f"{PRODUCTS_API}/products/count",
            timeout=3
        )

        if response.ok:
            products = response.json()

            stats["active_products"] = products.get(
                "count",
                stats["active_products"]
            )

    except (requests.exceptions.RequestException, ValueError):
        pass

    return jsonify(stats)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )