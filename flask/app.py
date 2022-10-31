from flask import Flask
app = Flask(__name__)

@app.route("/")
#@app.route("/1")
def home():
    return "Hello, Flask!"