import os

from flask import Flask, render_template

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_BASE = os.getenv("API_BASE", "http://localhost:5005")
STORE_HOME = os.getenv("STORE_HOME", "http://localhost:5000/")

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "css"),
    static_url_path="/css",
)


@app.route("/")
def index():
    return render_template("index.html", api_base=API_BASE, store_home=STORE_HOME)


if __name__ == "__main__":
    print("Student 5 frontend running on http://localhost:3005")
    print("API backend expected at http://localhost:5005")
    app.run(host="0.0.0.0", port=3005, debug=True)
