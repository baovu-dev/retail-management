import os
from flask import Flask, render_template

app = Flask(__name__, template_folder="templates", static_folder="css", static_url_path="/static")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/multi-agent")
def multi_agent():
    return render_template("multi_agent.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3002, debug=os.environ.get("FLASK_DEBUG") == "1")  # noqa: S104 - must listen on all interfaces inside the container