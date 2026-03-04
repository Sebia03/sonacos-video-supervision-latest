import os
import time
import uuid
import hashlib
import requests
from datetime import timedelta

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    set_access_cookies,
    unset_jwt_cookies,
    jwt_required,
)

# ==========================
# 🔧 CONFIG APP
# ==========================

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = "super-secret-key"
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
app.config["JWT_COOKIE_SECURE"] = False  # True en production HTTPS
app.config["JWT_COOKIE_SAMESITE"] = "Lax"
app.config["JWT_COOKIE_CSRF_PROTECT"] = False
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)

jwt = JWTManager(app)

CORS(
    app,
    supports_credentials=True,
    origins=["http://localhost:5173"],
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"]
)

# ==========================
# 🔐 AUTH CONFIG
# ==========================

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

@app.post("/login")
def login():
    data = request.get_json()

    if (
        data.get("username") == ADMIN_USERNAME and
        data.get("password") == ADMIN_PASSWORD
    ):
        access_token = create_access_token(identity="admin")
        response = jsonify({"message": "Login successful"})
        set_access_cookies(response, access_token)
        return response

    return jsonify({"error": "Invalid credentials"}), 401


@app.post("/logout")
def logout():
    response = jsonify({"message": "Logout successful"})
    unset_jwt_cookies(response)
    return response


# ==========================
# 📷 IMOU CONFIG
# ==========================

APP_ID = "lcea5699cd1d7c4457"
APP_SECRET = "f464f4b27e934bcba36125d953a4c6"
DATACENTER = "fk"

IMOU_TOKEN_CACHE = {
    "accessToken": None,
    "domain": None,
    "expires_at": 0
}

def generate_sign():
    timestamp = int(time.time())
    nonce = str(uuid.uuid4())
    raw = f"time:{timestamp},nonce:{nonce},appSecret:{APP_SECRET}"
    sign = hashlib.md5(raw.encode()).hexdigest()
    return timestamp, nonce, sign


def get_access_token():
    now = int(time.time())

    if IMOU_TOKEN_CACHE["accessToken"] and now < IMOU_TOKEN_CACHE["expires_at"]:
        return IMOU_TOKEN_CACHE["accessToken"], IMOU_TOKEN_CACHE["domain"]

    timestamp, nonce, sign = generate_sign()

    body = {
        "system": {
            "ver": "1.0",
            "appId": APP_ID,
            "sign": sign,
            "time": timestamp,
            "nonce": nonce
        },
        "id": str(uuid.uuid4()),
        "params": {}
    }

    url = f"https://openapi-{DATACENTER}.easy4ip.com/openapi/accessToken"
    r = requests.post(url, json=body).json()

    data = r["result"]["data"]

    IMOU_TOKEN_CACHE.update({
        "accessToken": data["accessToken"],
        "domain": data["currentDomain"],
        "expires_at": now + int(data["expireTime"]) - 60
    })

    return data["accessToken"], data["currentDomain"]


# ==========================
# 📷 GET DEVICES IMOU
# ==========================

@app.get("/devices")
@jwt_required()
def get_devices():

    token, _ = get_access_token()
    timestamp, nonce, sign = generate_sign()

    body = {
        "system": {
            "ver": "1.0",
            "appId": APP_ID,
            "sign": sign,
            "time": timestamp,
            "nonce": nonce
        },
        "id": str(uuid.uuid4()),
        "params": {
            "token": token,
            "page": 1,
            "pageSize": 50,
            "source": "bindAndShare"
        }
    }

    url = f"https://openapi-{DATACENTER}.easy4ip.com/openapi/listDeviceDetailsByPage"
    r = requests.post(url, json=body).json()
    print("========== KIT TOKEN RESPONSE ==========")
    print(r)

    device_list = r["result"]["data"]["deviceList"]

    return jsonify([
        {
            "deviceId": d["deviceId"],
            "deviceName": d["deviceName"],
            "status": d["deviceStatus"],
            "channelId": 0
        }
        for d in device_list
    ])

@app.post("/kit-token")
@jwt_required()
def kit_token():
    data = request.get_json()
    device_id = data.get("deviceId")

    token, domain = get_access_token()
    timestamp, nonce, sign = generate_sign()

    body = {
        "system": {
            "ver": "1.0",
            "appId": APP_ID,
            "sign": sign,
            "time": timestamp,
            "nonce": nonce
        },
        "id": str(uuid.uuid4()),
        "params": {
            "token": token,
            "deviceId": device_id,
            "channelId": 0,
            "type": 1
        }
    }

    url = f"https://openapi-{DATACENTER}.easy4ip.com/openapi/getKitToken"
    r = requests.post(url, json=body).json()

    print("========== KIT TOKEN RESPONSE ==========")
    print(r)

    kit_token = r["result"]["data"]["kitToken"]

    return jsonify({
        "kitToken": kit_token,
        "domain": domain
    })

@app.post("/records")
@jwt_required()
def get_records():
    data = request.get_json()

    device_id = data.get("deviceId")
    start_time = data.get("startTime")  # format: 20240301000000
    end_time = data.get("endTime")      # format: 20240301235959

    token, _ = get_access_token()
    timestamp, nonce, sign = generate_sign()

    body = {
        "system": {
            "ver": "1.0",
            "appId": APP_ID,
            "sign": sign,
            "time": timestamp,
            "nonce": nonce
        },
        "id": str(uuid.uuid4()),
        "params": {
            "token": token,
            "deviceId": device_id,
            "channelId": 0,
            "startTime": start_time,
            "endTime": end_time
        }
    }

    url = f"https://openapi-{DATACENTER}.easy4ip.com/openapi/queryRecordFile"
    r = requests.post(url, json=body).json()

    return jsonify(r)

    @app.post("/playback-token")
    @jwt_required()
def playback_token():
    data = request.get_json()
    device_id = data.get("deviceId")

    token, domain = get_access_token()
    timestamp, nonce, sign = generate_sign()

    body = {
        "system": {
            "ver": "1.0",
            "appId": APP_ID,
            "sign": sign,
            "time": timestamp,
            "nonce": nonce
        },
        "id": str(uuid.uuid4()),
        "params": {
            "token": token,
            "deviceId": device_id,
            "channelId": 0,
            "type": "2"  # ⚠️ type 2 = playback
        }
    }

    url = f"https://openapi-{DATACENTER}.easy4ip.com/openapi/getKitToken"
    r = requests.post(url, json=body).json()

    return jsonify({
        "kitToken": r["result"]["data"]["kitToken"],
        "domain": domain
    })

# ==========================
# 🚀 RUN
# ==========================

if __name__ == "__main__":
    app.run(debug=True, port=5000)