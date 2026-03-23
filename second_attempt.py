import os
import time
import requests
from flask import Flask, render_template_string
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Load from .env
ACCESS_TOKEN = os.getenv("SINRIC_ACCESS_TOKEN")
DEVICE_1_ID = os.getenv("DEVICE_1_ID")
DEVICE_2_ID = os.getenv("DEVICE_2_ID")

SINRIC_URL = "https://api.sinric.pro/api/v1/devices/{}/action"

# In-memory log
LOGS = []

def add_log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    LOGS.insert(0, f"[{timestamp}] {message}")
    if len(LOGS) > 50:
        LOGS.pop()

def send_all(state):
    send_power(DEVICE_1_ID, state)
    send_power(DEVICE_2_ID, state)

def send_power(device_id, state):
    query = {
        "clientId": "android-app",
        "type": "request",
        "createdAt": int(time.time() * 1000),
        "action": "setPowerState",
        "value": f'{{"state":"{state}"}}'
    }

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    url = SINRIC_URL.format(device_id)

    r = requests.get(url, headers=headers, params=query)
    add_log(f"Device {device_id} → {state} | {r.status_code}")

@app.route("/")
def index():
    return render_template_string("""
    <html>
    <head>
        <title>Sinric Device Control</title>
        <style>
            body { font-family: Arial; margin: 40px; }
            button { padding: 10px 20px; margin: 5px; }
            .log { background: #f4f4f4; padding: 10px; margin-top: 20px; height: 300px; overflow-y: scroll; }
        </style>
    </head>
    <body>
        <h2>Device Control</h2>

        <h3>Device 1</h3>
        <a href="/device1/on"><button>ON</button></a>
        <a href="/device1/off"><button>OFF</button></a>

        <h3>Device 2</h3>
        <a href="/device2/on"><button>ON</button></a>
        <a href="/device2/off"><button>OFF</button></a>

        <h3>Logs</h3>
        <div class="log">
            {% for log in logs %}
                {{ log }}<br>
            {% endfor %}
        </div>
    </body>
    </html>
    """, logs=LOGS)

@app.route("/device1/<state>")
def device1(state):
    send_power(DEVICE_1_ID, state.capitalize())
    return "OK <a href='/'>Back</a>"

@app.route("/device2/<state>")
def device2(state):
    send_power(DEVICE_2_ID, state.capitalize())
    return "OK <a href='/'>Back</a>"

@app.route("/all/on")
def all_on():
    send_all("On")
    return "ALL DEVICES ON <a href='/'>Back</a>"


@app.route("/all/off")
def all_off():
    send_all("Off")
    return "ALL DEVICES OFF <a href='/'>Back</a>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5200, debug=True)