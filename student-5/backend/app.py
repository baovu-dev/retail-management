import os
import re
from collections import defaultdict

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

from catalog import get_all_products, get_product
from prompt_loader import load_prompt

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL", "http://localhost:6005")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


class DbResponse:
    """Fallback response when the database service is unreachable."""

    def __init__(self, status_code=503, data=None):
        self.status_code = status_code
        self._data = data or {
            "error": (
                "Database service unavailable on port 6005. "
                "Run: cd student-5/database && python init_db.py && python app.py"
            )
        }

    def json(self):
        return self._data


def db_get(path, **params):
    try:
        return requests.get(f"{DATABASE_URL}{path}", params=params, timeout=5)
    except requests.RequestException as error:
        print(f"Database error: {error}")
        return DbResponse()


def db_post(path, payload):
    try:
        return requests.post(f"{DATABASE_URL}{path}", json=payload, timeout=5)
    except requests.RequestException as error:
        print(f"Database error: {error}")
        return DbResponse()


def db_put(path, payload):
    try:
        return requests.put(f"{DATABASE_URL}{path}", json=payload, timeout=5)
    except requests.RequestException as error:
        print(f"Database error: {error}")
        return DbResponse()


def db_delete(path):
    try:
        return requests.delete(f"{DATABASE_URL}{path}", timeout=5)
    except requests.RequestException as error:
        print(f"Database error: {error}")
        return DbResponse()


def call_ollama(prompt):
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=25,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except requests.RequestException as error:
        print(f"Ollama error: {error}")
        return None


def parse_csv_field(value):
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def format_catalog_for_prompt():
    lines = []
    for product in get_all_products():
        lines.append(
            f"- {product['name']} (${product['price']}, {product['category']}, {product['brand']})"
        )
    return "\n".join(lines)


def infer_chat_preferences(message, base_preferences=None):
    base = dict(base_preferences or {})
    text = message.lower()

    category_map = {
        "basketball": ["basketball", "court", "jordan", "hoops"],
        "everyday": ["everyday", "daily", "casual", "comfort", "walking", "wear"],
        "street": ["street", "style", "fashion", "hype", "lifestyle"],
        "running": ["running", "run", "jog", "marathon"],
        "active": ["active", "sport", "training", "gym", "workout", "cleats"],
    }
    matched_categories = []
    for category, keywords in category_map.items():
        if any(keyword in text for keyword in keywords):
            matched_categories.append(category)

    brand_map = {
        "nike": "Nike",
        "jordan": "Jordan",
        "adidas": "Adidas",
        "puma": "Puma",
        "new balance": "New Balance",
        "off white": "Off White",
    }
    matched_brands = []
    for keyword, brand in brand_map.items():
        if keyword in text:
            matched_brands.append(brand)

    price_max = float(base.get("price_range_max") or 500)
    price_min = float(base.get("price_range_min") or 0)
    under_match = re.search(r"(?:under|below|max|less than)\s*\$?\s*(\d+)", text)
    if under_match:
        price_max = float(under_match.group(1))
    over_match = re.search(r"(?:over|above|at least|min)\s*\$?\s*(\d+)", text)
    if over_match:
        price_min = float(over_match.group(1))
    budget_match = re.search(r"\$?\s*(\d+)\s*(?:budget|range)", text)
    budget_specified = bool(under_match or over_match or budget_match)
    if budget_match:
        price_max = float(budget_match.group(1))

    existing_categories = parse_csv_field(base.get("product_category_interests", ""))
    existing_brands = [b.strip() for b in (base.get("preferred_brands") or "").split(",") if b.strip()]

    categories = matched_categories or existing_categories or ["everyday", "street"]
    brands = matched_brands or existing_brands or ["Nike", "Adidas"]

    return {
        "product_category_interests": ",".join(dict.fromkeys(categories)),
        "preferred_brands": ",".join(dict.fromkeys(brands)),
        "price_range_min": price_min,
        "price_range_max": price_max,
        "budget_specified": budget_specified,
    }


def product_matches_budget(product, chat_preferences):
    if not chat_preferences.get("budget_specified"):
        return True
    price_min = float(chat_preferences.get("price_range_min", 0) or 0)
    price_max = float(chat_preferences.get("price_range_max", 9999) or 9999)
    return price_min <= product["price"] <= price_max


def preferences_for_db(chat_preferences):
    return {k: v for k, v in chat_preferences.items() if k != "budget_specified"}


def chat_product_score(product, message, reply):
    text = f"{message} {reply}".lower()
    score = 0.2
    name = product["name"].lower()
    brand = product["brand"].lower()
    category = product["category"].lower()
    tags = [tag.lower() for tag in product.get("tags", [])]

    if name in text or any(part in text for part in name.split() if len(part) > 3):
        score += 0.45
    if brand in text:
        score += 0.25
    if category in text or any(tag in text for tag in tags):
        score += 0.25

    for word in message.lower().split():
        if len(word) > 4 and word in name:
            score += 0.15
            break

    return min(score, 1)


PRODUCT_INSIGHTS = {
    101: "Classic Jordan 1 high-top — bold on court and on the street.",
    102: "Retro Puma trainers with soft cushioning for all-day wear.",
    103: "Sport cleats built for traction and quick cuts on the field.",
    104: "New Balance 550 blends vintage style with everyday comfort.",
    105: "Off-White accents give this pair a designer streetwear edge.",
    106: "Yeezy Boost 350 V2 — responsive foam for running and active days.",
    107: "Premium Jordan 4 retro with standout color blocking.",
    108: "Air Force 1 Low — one of Nike's most versatile everyday sneakers.",
}


def build_chat_explanation(product, message, chat_preferences, rank=1):
    reasons = []
    message_lower = message.lower()
    price = product["price"]
    brand = product["brand"]
    name = product["name"]

    reasons.append(
        PRODUCT_INSIGHTS.get(
            product["product_id"],
            f"The {name} is a strong {product['category']} option from {brand}.",
        )
    )

    if chat_preferences.get("budget_specified"):
        price_max = float(chat_preferences.get("price_range_max", 9999))
        price_min = float(chat_preferences.get("price_range_min", 0))
        if price_min <= price <= price_max and any(
            word in message_lower for word in ("under", "below", "less than", "max")
        ):
            reasons.append(
                f"Priced at ${price:.2f}, within your under-${price_max:.0f} budget."
            )

    if brand.lower() in message_lower:
        reasons.append(f"You mentioned {brand} — this model fits that request.")

    categories = parse_csv_field(chat_preferences.get("product_category_interests", ""))
    if product["category"] in categories:
        reasons.append(f"Matches the {product['category']} style you're looking for.")

    if rank == 1:
        reasons.append("Top-ranked pick based on your message.")
    elif rank >= 2:
        reasons.append(f"Ranked #{rank} — a solid alternative worth comparing.")

    return "\n".join(reasons[:3])


def chat_explanation(product, message):
    prefs = infer_chat_preferences(message)
    return build_chat_explanation(product, message, prefs)


def build_recommendations_from_chat(customer_id, message, reply, limit=6):
    preferences, history, viewed_ids = get_customer_context(customer_id)
    chat_preferences = infer_chat_preferences(message, preferences or {})
    db_put(f"/preferences/{customer_id}", preferences_for_db(chat_preferences))

    all_history_response = db_get("/browsing-history")
    all_history = (
        all_history_response.json()
        if all_history_response.status_code == 200
        else history
    )

    scored_products = []
    for product in get_all_products():
        if not product_matches_budget(product, chat_preferences):
            continue

        chat = chat_product_score(product, message, reply)
        content = content_score(product, chat_preferences, viewed_ids)
        collaborative = collaborative_score(product, customer_id, all_history)
        final_score = round((0.55 * chat) + (0.30 * content) + (0.15 * collaborative), 3)
        if final_score >= 0.28:
            scored_products.append((product, final_score))

    scored_products.sort(key=lambda item: item[1], reverse=True)
    top_products = scored_products[:limit]

    if not top_products:
        top_products = [
            (product, 0.4)
            for product in get_all_products()
            if product_matches_budget(product, chat_preferences)
        ][:limit]

    db_delete(f"/recommendations/customer/{customer_id}")

    recommendations = []
    for rank, (product, score) in enumerate(top_products, start=1):
        explanation = build_chat_explanation(product, message, chat_preferences, rank=rank)
        create_response = db_post(
            "/recommendations",
            {
                "customer_id": customer_id,
                "recommended_product_id": product["product_id"],
                "recommendation_score": score,
                "explanation": explanation,
            },
        )
        rec_id = (
            create_response.json().get("recommendation_id")
            if create_response.status_code == 201
            else None
        )
        recommendations.append({
            "recommendation_id": rec_id,
            "customer_id": customer_id,
            "recommended_product_id": product["product_id"],
            "recommendation_score": score,
            "explanation": explanation,
            "product": product,
        })

    if chat_preferences.get("budget_specified"):
        recommendations = [
            rec
            for rec in recommendations
            if product_matches_budget(rec["product"], chat_preferences)
        ]

    return recommendations


def get_customer_context(customer_id):
    preferences = {}
    prefs_response = db_get(f"/preferences/{customer_id}")
    if prefs_response.status_code == 200:
        preferences = prefs_response.json()

    history_response = db_get("/browsing-history", customer_id=customer_id)
    history = history_response.json() if history_response.status_code == 200 else []

    viewed_ids = {entry["product_id"] for entry in history}
    return preferences, history, viewed_ids


def content_score(product, preferences, viewed_ids):
    if product["product_id"] in viewed_ids:
        return 0.15

    categories = parse_csv_field(preferences.get("product_category_interests", ""))
    brands = parse_csv_field(preferences.get("preferred_brands", ""))
    price_min = float(preferences.get("price_range_min", 0) or 0)
    price_max = float(preferences.get("price_range_max", 9999) or 9999)

    score = 0.2
    product_category = product["category"].lower()
    product_brand = product["brand"].lower()
    product_tags = [tag.lower() for tag in product.get("tags", [])]

    if any(cat in product_category or cat in product_tags for cat in categories):
        score += 0.35
    if any(brand in product_brand for brand in brands):
        score += 0.3
    if price_min <= product["price"] <= price_max:
        score += 0.15
    else:
        score -= 0.1

    return min(max(score, 0), 1)


def collaborative_score(product, customer_id, all_history):
    similar_customers = defaultdict(int)
    target_views = {
        entry["product_id"]
        for entry in all_history
        if entry["customer_id"] == customer_id
    }

    for entry in all_history:
        if entry["customer_id"] == customer_id:
            continue
        if entry["product_id"] in target_views:
            similar_customers[entry["customer_id"]] += 1

    if not similar_customers:
        return 0.2

    overlap_score = 0
    for other_customer, overlap in similar_customers.items():
        for entry in all_history:
            if (
                entry["customer_id"] == other_customer
                and entry["product_id"] == product["product_id"]
            ):
                overlap_score += overlap * 0.05

    return min(overlap_score, 1)


def fallback_explanation(product, preferences, score):
    brands = preferences.get("preferred_brands", "your preferred brands")
    categories = preferences.get("product_category_interests", "your interests")
    return (
        f"We think you'll like the {product['name']} because it matches {categories} "
        f"and {brands}, with a {int(score * 100)}% match score."
    )


def generate_explanation(product, preferences, history, score):
    prompt_template = load_prompt("recommendation_explanation_prompt.txt")
    prompt = prompt_template.format(
        category_interests=preferences.get("product_category_interests", "general"),
        preferred_brands=preferences.get("preferred_brands", "any"),
        recent_views=", ".join(str(entry["product_id"]) for entry in history[:5]) or "none",
        product_name=product["name"],
        brand=product["brand"],
        price=product["price"],
        category=product["category"],
        score=f"{score:.2f}",
    )
    explanation = call_ollama(prompt)
    if explanation:
        return explanation
    return fallback_explanation(product, preferences, score)


def build_recommendations(customer_id, limit=6):
    preferences, history, viewed_ids = get_customer_context(customer_id)
    if not preferences:
        return []

    all_history_response = db_get("/browsing-history")
    all_history = (
        all_history_response.json() if all_history_response.status_code == 200 else history
    )

    scored_products = []
    for product in get_all_products():
        content = content_score(product, preferences, viewed_ids)
        collaborative = collaborative_score(product, customer_id, all_history)
        final_score = round((0.6 * content) + (0.4 * collaborative), 3)
        if final_score >= 0.35:
            scored_products.append((product, final_score))

    scored_products.sort(key=lambda item: item[1], reverse=True)
    top_products = scored_products[:limit]

    db_delete(f"/recommendations/customer/{customer_id}")

    recommendations = []
    for product, score in top_products:
        explanation = generate_explanation(product, preferences, history, score)
        create_response = db_post(
            "/recommendations",
            {
                "customer_id": customer_id,
                "recommended_product_id": product["product_id"],
                "recommendation_score": score,
                "explanation": explanation,
            },
        )
        if create_response.status_code == 201:
            rec_id = create_response.json().get("recommendation_id")
        else:
            rec_id = None

        recommendations.append({
            "recommendation_id": rec_id,
            "customer_id": customer_id,
            "recommended_product_id": product["product_id"],
            "recommendation_score": score,
            "explanation": explanation,
            "product": product,
        })

    return recommendations


def enrich_recommendations(raw_recommendations):
    enriched = []
    for rec in raw_recommendations:
        product = get_product(rec["recommended_product_id"])
        if not product:
            continue
        enriched.append({**rec, "product": product})
    return enriched


def similar_products_for_product(product_id, limit=4):
    source = get_product(product_id)
    if not source:
        return []

    results = []
    for product in get_all_products():
        if product["product_id"] == product_id:
            continue
        score = 0
        if product["category"] == source["category"]:
            score += 0.5
        if product["brand"] == source["brand"]:
            score += 0.3
        shared_tags = set(product.get("tags", [])) & set(source.get("tags", []))
        score += min(len(shared_tags) * 0.1, 0.2)
        if score > 0.3:
            results.append({
                "recommended_product_id": product["product_id"],
                "recommendation_score": round(score, 2),
                "explanation": f"Similar {source['category']} style to {source['name']}.",
                "product": product,
            })

    results.sort(key=lambda item: item["recommendation_score"], reverse=True)
    return results[:limit]


# ── Health & status ──

@app.route("/api/health", methods=["GET"])
def health():
    db_response = db_get("/preferences/1")
    db_ok = db_response.status_code == 200
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "frontend_port": 3005,
        "backend_port": 5005,
        "database_port": 6005,
        "database_connected": db_ok,
        "message": (
            "All services running."
            if db_ok
            else "Backend is up but database on port 6005 is not reachable."
        ),
    }), 200 if db_ok else 503


# ── Recommendation REST API ──

@app.route("/api/recommendations/customer/<int:customer_id>", methods=["GET"])
def get_customer_recommendations(customer_id):
    response = db_get("/recommendations", customer_id=customer_id)
    if response.status_code != 200:
        return jsonify({"error": response.json().get("error"), "recommendations": []}), response.status_code
    return jsonify(enrich_recommendations(response.json()))


@app.route("/api/recommendations/product/<int:product_id>", methods=["GET"])
def get_product_recommendations(product_id):
    return jsonify(similar_products_for_product(product_id))


@app.route("/api/recommendations/generate/<int:customer_id>", methods=["POST"])
def generate_customer_recommendations(customer_id):
    prefs = db_get(f"/preferences/{customer_id}")
    if prefs.status_code != 200:
        return jsonify(prefs.json()), prefs.status_code
    recommendations = build_recommendations(customer_id)
    return jsonify(recommendations), 201


@app.route("/api/recommendations/feedback", methods=["POST"])
def submit_recommendation_feedback():
    data = request.json or {}
    response = db_post("/recommendation-feedback", data)
    return jsonify(response.json()), response.status_code


@app.route("/api/recommendations/metrics", methods=["GET"])
def recommendation_metrics():
    response = db_get("/stats/metrics")
    if response.status_code != 200:
        return jsonify(response.json()), response.status_code
    return jsonify(response.json()), response.status_code


# ── Preferences & browsing proxy API ──

@app.route("/api/preferences/<int:customer_id>", methods=["GET", "PUT", "DELETE"])
def preferences_proxy(customer_id):
    if request.method == "GET":
        response = db_get(f"/preferences/{customer_id}")
    elif request.method == "PUT":
        response = db_put(f"/preferences/{customer_id}", request.json or {})
    else:
        response = db_delete(f"/preferences/{customer_id}")
    return jsonify(response.json()), response.status_code


@app.route("/api/preferences", methods=["POST"])
def create_preferences_proxy():
    response = db_post("/preferences", request.json or {})
    return jsonify(response.json()), response.status_code


@app.route("/api/browsing-history", methods=["GET", "POST"])
def browsing_history_proxy():
    if request.method == "GET":
        response = db_get("/browsing-history", **request.args)
    else:
        response = db_post("/browsing-history", request.json or {})
    return jsonify(response.json()), response.status_code


@app.route("/api/browsing-history/<int:history_id>", methods=["DELETE"])
def delete_browsing_proxy(history_id):
    response = db_delete(f"/browsing-history/{history_id}")
    return jsonify(response.json()), response.status_code


@app.route("/api/products", methods=["GET"])
def list_products():
    return jsonify(get_all_products())


@app.route("/api/products/<int:product_id>", methods=["GET"])
def get_product_api(product_id):
    product = get_product(product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(product)


# ── Chatbot ──

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    message = (data.get("message") or "").strip()
    customer_id = int(data.get("customer_id", 1))

    if not message:
        return jsonify({"error": "Message is required"}), 400

    preferences, history, _ = get_customer_context(customer_id)
    if not preferences:
        preferences = {
            "product_category_interests": "everyday,street",
            "preferred_brands": "Nike,Adidas",
            "price_range_min": 50,
            "price_range_max": 200,
        }

    prompt_template = load_prompt("chatbot_system_prompt.txt")
    prompt = prompt_template.format(
        customer_id=customer_id,
        category_interests=preferences.get("product_category_interests", ""),
        preferred_brands=preferences.get("preferred_brands", ""),
        price_min=preferences.get("price_range_min", 0),
        price_max=preferences.get("price_range_max", 500),
        recent_views=", ".join(str(entry["product_id"]) for entry in history[:6]) or "none",
        catalog=format_catalog_for_prompt(),
        message=message,
    )

    reply = call_ollama(prompt)
    if not reply:
        reply = (
            "I can help you find men's sneakers based on what you're looking for. "
            "Tell me your style — everyday, basketball, street — and your budget."
        )

    recommendations = build_recommendations_from_chat(customer_id, message, reply)

    return jsonify({
        "reply": reply,
        "customer_id": customer_id,
        "recommendations": recommendations,
    })


if __name__ == "__main__":
    print("Student 5 API backend running on http://localhost:5005")
    print("Frontend expected at http://localhost:3005")
    print("Database API expected at http://localhost:6005")
    app.run(host="0.0.0.0", port=5005, debug=True)
