from flask import Flask, request, jsonify, render_template
import requests
import os

from prompt_loader import load_prompt

app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/css', static_url_path='/static')

DATABASE_URL = os.getenv("DATABASE_URL", "http://localhost:6001")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

def analyse_sentiment(comment_text):
    if not comment_text:
        return 0.0  # Neutral sentiment for empty comments

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

def is_verified_purchase(customer_id, product_id):
    # HAVE TO IMPLEMENT ONCE ORDER IS COMPLETED!!!
    return True

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit')
def submit_page():
    product_id = request.args.get('product_id')
    customer_id = request.args.get('customer_id')
    return render_template('submit.html', product_id=product_id, customer_id=customer_id)

@app.route('/reviews/view', methods=['GET'])
def view_reviews_html():
    product_id = request.args.get('product_id')
 
    if not product_id:
        return "<p>Enter a product ID.</p>"
 
    reviews_response = requests.get(f"{DATABASE_URL}/reviews/{product_id}")
    reviews = reviews_response.json()
 
    summary_response = requests.get(f"{DATABASE_URL}/reviews/summary/{product_id}")
    existing_summary = summary_response.json()
 
    if existing_summary and existing_summary.get('generated_summary_text'):
        summary_text = existing_summary['generated_summary_text']
    else:
        summary_text = generate_summary(product_id)
 
    return render_template('partials/reviews_list.html', reviews=reviews, summary_text=summary_text)

@app.route('/reviews/<int:product_id>', methods=['GET'])
def list_reviews(product_id):
    response = requests.get(f"{DATABASE_URL}/reviews/{product_id}")
    return jsonify(response.json()), response.status_code

@app.route('/reviews', methods=['POST'])
def submit_review():
    data = request.json

    if not is_verified_purchase(data['customer_id'], data['product_id']):
        return jsonify({"error": "Only verified purchases can leave a review."}), 403

    data['sentiment_score'] = analyse_sentiment(data.get('comment', ''))
    data['is_flagged'] = 1 if data['sentiment_score'] < -0.8 else 0 # Flag if sentiment is very negative

    response = requests.post(f"{DATABASE_URL}/reviews", json=data)
    return jsonify(response.json()), response.status_code

@app.route('/reviews/submit-form', methods=['POST'])
def submit_review_form():
    data = {
        "product_id": int(request.form.get('product_id')),
        "customer_id": int(request.form.get('customer_id')),
        "rating": int(request.form.get('rating')),
        "comment": request.form.get('comment', '')
    }
 
    if not is_verified_purchase(data['customer_id'], data['product_id']):
        return "<p style='color: var(--pink);'>Only verified purchases can leave a review.</p>"
 
    existing_reviews_res = requests.get(f"{DATABASE_URL}/reviews/{data['product_id']}")
    existing_reviews = existing_reviews_res.json()
    already_reviewed = any(
        rev['customer_id'] == data['customer_id'] for rev in existing_reviews
    )
    if already_reviewed:
        return "<p style='color: var(--pink);'>You've already reviewed this product.</p>"
 
    data['sentiment_score'] = analyse_sentiment(data['comment'])
    data['is_flagged'] = 1 if data['sentiment_score'] < -0.8 else 0
 
    r = requests.post(f"{DATABASE_URL}/reviews", json=data)
 
    if r.status_code == 201:
        response = app.make_response(
            "<p style='color: var(--purple); font-weight: 600;'>Review submitted. Redirecting…</p>"
        )
        response.headers['HX-Redirect'] = 'http://localhost:5000/'
        return response
    return "<p style='color: var(--pink);'>Something went wrong. Please try again.</p>"

@app.route('/reviews/<int:review_id>', methods=['PUT'])
def edit_review(review_id):
    data = request.json
    response = requests.put(f"{DATABASE_URL}/reviews/{review_id}", json=data)
    return jsonify(response.json()), response.status_code

@app.route('/reviews/<int:review_id>', methods=['DELETE'])
def delete_review(review_id):
    response = requests.delete(f"{DATABASE_URL}/reviews/{review_id}")
    return jsonify(response.json()), response.status_code

def generate_summary(product_id):
    response = requests.get(f"{DATABASE_URL}/reviews/{product_id}")
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
    response = requests.get(f"{DATABASE_URL}/reviews/summary/{product_id}")
    existing_summary = response.json()

    if existing_summary and existing_summary.get('generated_summary_text'):
        return jsonify(existing_summary), response.status_code

    summary_text = generate_summary(product_id)
    return jsonify({"product_id": product_id, "generated_summary_text": summary_text}), 200

@app.route('/reviews/stats', methods=['GET'])
def get_review_stats():
    response = requests.get(f"{DATABASE_URL}/reviews")
    all_reviews = response.json()

    total = len(all_reviews)
    average_rating = round(sum(review['rating'] for review in all_reviews) / total, 1) if total else 0
    flagged_count = sum(1 for review in all_reviews if review['is_flagged'])

    return jsonify({
        "average_rating": average_rating,
        "flagged_count": flagged_count,
        "total_reviews": total,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)