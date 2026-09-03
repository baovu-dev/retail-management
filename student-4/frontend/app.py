import os

from flask import Flask, render_template

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_BASE = os.getenv("API_BASE", "http://localhost:5004")

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "css"),
    static_url_path="/css",
)


@app.route("/")
def index():
    return render_template("index.html", api_base=API_BASE)


if __name__ == "__main__":
    print("Order Frontend running on http://localhost:3004")
    print("Order Backend expected at http://localhost:5004")
    app.run(host="0.0.0.0", port=3004, debug=True)