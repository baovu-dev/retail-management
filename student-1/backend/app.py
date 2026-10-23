from flask import Flask, request, jsonify, render_template
import requests
import os

from prompt_loader import load_prompt
from purchase_auth import verify_purchase_proof
from routes.mcp_mode import mcp_bp
from routes.rag_mode import rag_bp
from routes.multi_agent_mode import multi_agent_bp

app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/css', static_url_path='/static')

app.register_blueprint(mcp_bp)

app.register_blueprint(rag_bp)

app.register_blueprint(multi_agent_bp)

DATABASE_URL = os.getenv("DATABASE_URL", "http://localhost:6001")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
REQUEST_TIMEOUT = 10  # seconds; stops a slow service from hanging the backend

# Other KICKLAB services: defaults match local Docker, the cloud deployment overrides them
ORDERS_API_URL = os.getenv("ORDERS_API_URL", "http://host.docker.internal:5004")
SHARED_URL = os.getenv("SHARED_URL", "http://localhost:5000")
PRODUCTS_URL = os.getenv("PRODUCTS_URL", "http://localhost:3002")
ORDERS_UI_URL = os.getenv("ORDERS_UI_URL", "http://localhost:3004")
CHATBOT_URL = os.getenv("CHATBOT_URL", "http://localhost:3005")

# Release 2: AI-Mode is disabled in the cloud deployment (no Ollama there)
AI_MODE_ENABLED = os.getenv("AI_MODE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
AI_DISABLED_MESSAGE = "AI features are disabled in this deployment."

def analyse_sentiment(comment_text):
    if not comment_text:
        return 0.0  # Neutral sentiment for empty comments

    if not AI_MODE_ENABLED:
        return 0.0  # AI-Mode off: store a neutral score, so the review is not auto-flagged

    prompt_template = load_prompt("sentiment_analysis_prompt.txt")
    prompt = prompt_template.format(comment_text=comment_text)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=20
        )
        result = response.json()
        return float(result['response'].strip())
    except Exception as e:
        print(f"Error during sentiment analysis: {e}")
        return 0.0  # Default to neutral sentiment on error

def is_verified_purchase(proof, product_id):
    """Return a boolean only; no list/detail calls and no credential-bearing exception logs."""
    from urllib.parse import urlsplit
    try:
        target = urlsplit(ORDERS_API_URL)
        if (target.scheme not in {"http", "https"} or not target.hostname or target.username or target.password
                or target.query or target.fragment or target.path not in ("", "/")
                or os.getenv("APP_ENV", "local") == "cloud" and target.scheme != "https"):
            return None
        response = requests.post(ORDERS_API_URL.rstrip("/") + "/api/orders/verified-purchase",
                                 json={"product_id": product_id}, headers={"Authorization": "Bearer " + proof},
                                 timeout=5, allow_redirects=False)
        data = response.json()
        if response.status_code != 200 or not isinstance(data, dict) or type(data.get("verified_purchase")) is not bool:
            return None
        return data["verified_purchase"]
    except (requests.RequestException, ValueError, TypeError):
        return None


def review_submission(data, form=False):
    if not isinstance(data, dict):
        return jsonify(error="Review input required.", code="invalid_input"), 400
    try:
        product_id = int(data.get("product_id")) if form else data.get("product_id")
        rating = int(data.get("rating")) if form else data.get("rating")
    except (TypeError, ValueError):
        return jsonify(error="Valid product and rating required.", code="invalid_input"), 400
    scheme, _, proof = request.headers.get("Authorization", "").partition(" ")
    claims, error = verify_purchase_proof(proof if scheme.lower() == "bearer" else "", product_id)
    if error:
        return jsonify(error[0]), error[1]
    if "customer_id" in data:
        supplied = str(data["customer_id"])
        if supplied != str(claims["customer_id"]):
            return jsonify(error="Customer identity mismatch.", code="forbidden"), 403
    comment = data.get("comment", "")
    if (type(rating) is not int or not 1 <= rating <= 5 or not isinstance(comment, str) or len(comment) > 3000):
        return jsonify(error="Rating or comment is invalid.", code="invalid_input"), 400
    verified = is_verified_purchase(proof, product_id)
    if verified is None:
        return jsonify(error="Purchase verification unavailable.", code="unavailable"), 503
    if not verified:
        return jsonify(error="Only confirmed purchases can leave a review.", code="forbidden"), 403
    payload = {"customer_id": claims["customer_id"], "product_id": product_id, "rating": rating, "comment": comment}
    try:
        if form:
            existing = requests.get(f"{DATABASE_URL}/reviews/{product_id}", timeout=REQUEST_TIMEOUT)
            rows = existing.json()
            if existing.status_code != 200 or not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Invalid review response")
            if any(row.get("customer_id") == claims["customer_id"] for row in rows):
                return jsonify(error="You have already reviewed this product.", code="duplicate"), 409
        payload["sentiment_score"] = analyse_sentiment(comment)
        payload["is_flagged"] = int(payload["sentiment_score"] < -0.8)
        response = requests.post(f"{DATABASE_URL}/reviews", json=payload, timeout=REQUEST_TIMEOUT)
        if response.status_code != 201:
            raise ValueError("Review write failed")
        if form:
            result = jsonify(message="Review submitted.")
            result.headers["HX-Redirect"] = SHARED_URL.rstrip("/") + "/"
            return result, 201
        return jsonify(response.json()), 201
    except (requests.RequestException, ValueError, TypeError):
        return jsonify(error="Review service unavailable.", code="unavailable"), 503


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit')
def submit_page():
    product_id = request.args.get('product_id')
    return render_template('submit.html', product_id=product_id)

@app.route('/reviews/view', methods=['GET'])
def view_reviews_html():
    product_id = request.args.get('product_id')
 
    if not product_id:
        return "<p>Enter a product ID.</p>"
 
    reviews_response = requests.get(f"{DATABASE_URL}/reviews/{product_id}", timeout=REQUEST_TIMEOUT)
    reviews = reviews_response.json()
 
    summary_response = requests.get(f"{DATABASE_URL}/reviews/summary/{product_id}", timeout=REQUEST_TIMEOUT)
    existing_summary = summary_response.json()
 
    if existing_summary and existing_summary.get('generated_summary_text'):
        summary_text = existing_summary['generated_summary_text']
    else:
        summary_text = generate_summary(product_id)
 
    return render_template('partials/reviews_list.html', reviews=reviews, summary_text=summary_text)

@app.route('/reviews/<int:product_id>', methods=['GET'])
def list_reviews(product_id):
    response = requests.get(f"{DATABASE_URL}/reviews/{product_id}", timeout=REQUEST_TIMEOUT)
    return jsonify(response.json()), response.status_code

@app.route('/reviews', methods=['POST'])
def submit_review():
    return review_submission(request.get_json(silent=True))


@app.route('/reviews/submit-form', methods=['POST'])
def submit_review_form():
    return review_submission(request.form.to_dict(), form=True)


@app.route('/reviews/<int:review_id>', methods=['PUT'])
def edit_review(review_id):
    data = request.json
    response = requests.put(f"{DATABASE_URL}/reviews/{review_id}", json=data, timeout=REQUEST_TIMEOUT)
    return jsonify(response.json()), response.status_code

@app.route('/reviews/<int:review_id>', methods=['DELETE'])
def delete_review(review_id):
    response = requests.delete(f"{DATABASE_URL}/reviews/{review_id}", timeout=REQUEST_TIMEOUT)
    return jsonify(response.json()), response.status_code

@app.route('/reviews/delete-form/<int:review_id>', methods=['DELETE'])
def remove_review_form(review_id):
    requests.delete(f"{DATABASE_URL}/reviews/{review_id}", timeout=REQUEST_TIMEOUT)
    return ''

def generate_summary(product_id):
    if not AI_MODE_ENABLED:
        return AI_DISABLED_MESSAGE
    
    response = requests.get(f"{DATABASE_URL}/reviews/{product_id}", timeout=REQUEST_TIMEOUT)
    reviews = response.json()

    if not reviews:
        return "No reviews available to generate a summary."

    comments = [review['comment'] for review in reviews if review['comment']]
    combined_comments = " ".join(comments)

    prompt_template = load_prompt("review_summary_prompt.txt")
    prompt = prompt_template.format(comments=combined_comments)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=20
        )
        result = response.json()
        return result['response'].strip()
    except Exception as e:
        print(f"Error during summary generation: {e}")
        return "Error generating summary."

@app.route('/reviews/summary/<int:product_id>', methods=['GET'])
def get_review_summary(product_id):
    response = requests.get(f"{DATABASE_URL}/reviews/summary/{product_id}", timeout=REQUEST_TIMEOUT)
    existing_summary = response.json()

    if existing_summary and existing_summary.get('generated_summary_text'):
        return jsonify(existing_summary), response.status_code

    summary_text = generate_summary(product_id)
    return jsonify({"product_id": product_id, "generated_summary_text": summary_text}), 200

@app.route('/moderate')
def moderate_page():
    return render_template('moderate.html')

@app.route('/reviews/flagged', methods=['GET'])
def view_flagged_reviews():
    r = requests.get(f"{DATABASE_URL}/reviews", timeout=REQUEST_TIMEOUT)
    all_reviews = r.json()

    flagged_reviews = [rev for rev in all_reviews if rev['is_flagged']]

    return render_template('partials/flagged_list.html', reviews=flagged_reviews)

@app.route('/reviews/stats', methods=['GET'])
def get_review_stats():
    response = requests.get(f"{DATABASE_URL}/reviews", timeout=REQUEST_TIMEOUT)
    all_reviews = response.json()

    total = len(all_reviews)
    average_rating = round(sum(review['rating'] for review in all_reviews) / total, 1) if total else 0
    flagged_count = sum(1 for review in all_reviews if review['is_flagged'])

    return jsonify({
        "average_rating": average_rating,
        "flagged_count": flagged_count,
        "total_reviews": total,
    })

@app.context_processor
def inject_links():
    """Cross-feature link addresses, available in every template as {{ links.<name> }}."""
    return {
        "links": {
            "shared": SHARED_URL,
            "products": PRODUCTS_URL,
            "orders": ORDERS_UI_URL,
            "chatbot": CHATBOT_URL,
        }
    }

if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    # noqa: S104 - the container must listen on all interfaces to be reachable
    app.run(host="0.0.0.0", port=5001, debug=debug_mode)  # noqa: S104