from flask import Flask, jsonify, request
from flask_cors import CORS
from mcp_client import call_tool
import requests
from rag_client import call_rag_service, RAG_FEATURE
import os

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "http://localhost:6002"
)

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.1:8b"
)

@app.route('/products', methods=['GET'])
def get_products():
    response = requests.get(f"{DATABASE_URL}/products")
    return jsonify(response.json()), response.status_code

@app.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    response = requests.get(
        f"{DATABASE_URL}/products/{product_id}"
    )
    return jsonify(response.json()), response.status_code

@app.route("/products", methods=["POST"])
def create_product():
    data = request.get_json()


    response = requests.post(
        f"{DATABASE_URL}/products",
        json=data
    )

    return jsonify(response.json()), response.status_code

@app.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    data = request.get_json()

    response = requests.put(
        f"{DATABASE_URL}/products/{product_id}",
        json=data
    )

    return jsonify(response.json()), response.status_code

@app.route("/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    response = requests.delete(
        f"{DATABASE_URL}/products/{product_id}"
    )

    return jsonify(response.json()), response.status_code

@app.route("/products/count", methods=["GET"])
def get_product_count():
    response = requests.get(f"{DATABASE_URL}/products")
    products = response.json()

    return jsonify({
        "count": len(products)
    })

@app.route("/products/<int:product_id>/generate-description", methods=["POST"])
def generate_product_description(product_id):
    product_response = requests.get(
        f"{DATABASE_URL}/products/{product_id}"
    )

    if product_response.status_code != 200:
        return jsonify({"error": "Product not found"}), 404

    product = product_response.json()

    prompt = f"""
Generate a short product description for this product.

Name: {product["name"]}
Category: {product["category"]}
Brand: {product["brand"]}
Price: ${product["price"]}

Use only the information provided.
Do not invent specifications or features.
Return only the product description.
"""

    ollama_response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        }
    )

    result = ollama_response.json()

    return jsonify({
        "product_id": product_id,
        "description": result["response"]
    })

@app.route("/mcp/product/<int:product_id>", methods=["GET"])
def mcp_get_product(product_id):
    try:
        result = call_tool(
            "product_by_id", 
            {"product_id": product_id}
        )
        if "error" in result:
          return jsonify(result), 400

        return jsonify(result), 200

    except Exception as exc:
        return jsonify({
        "error": "Shared MCP server unreachable",
        "detail": str(exc)
    }), 503

@app.route("/rag/ask", methods=["POST"])
def rag_ask():
    data = request.get_json() or {}
    query = data.get("query", "").strip()

    if not query:
        return jsonify({
            "status": "error",
            "error": "query is required"
            }), 400

    try:
        result = call_rag_service(
            "/answer", 
            {
                "query": query,
                "feature": RAG_FEATURE,
                "k": 5
            }
        )
        return jsonify(result), 200
    
    except Exception as exc:
        return jsonify({
            "status": "error",
            "error": "Shared RAG server unreachable",
            "detail": str(exc)
        }), 503

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)