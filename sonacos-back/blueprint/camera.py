import time
import uuid
import hashlib
import requests
from flask import Blueprint, jsonify, request, current_app
from flask_cors import CORS

camera_bp = Blueprint("camera", __name__)
CORS(camera_bp)
# CONFIG IMOU pour la connexion au compte dev
APP_ID = "lcea5699cd1d7c4457"
APP_SECRET = "f464f4b27e934bcba36125d953a4c6"
DATACENTER = "fk"

IMOU_TOKEN_CACHE = {
    "accessToken": None,
    "domain": None,
    "expires_at": 0
}
# gérer le token d’accès
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

@camera_bp.route("/sdk-config")
def sdk_config():
    token, domain = get_access_token()
    return jsonify({
        "accessToken": token,
        "domain": domain
    })

# lister les caméras
@camera_bp.route("/devices", methods=["GET"])
def devices():
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

    return jsonify([
        {
            "deviceId": d["deviceId"],
            "deviceName": d["deviceName"],
            "status": d["deviceStatus"],
            "channelId": 0
        } for d in r["result"]["data"]["deviceList"]
    ])

# générer un kitToken pour le streaming
@camera_bp.route("/kit-token", methods=["POST"])
def kit_token():
    data = request.json
    device_id = data["deviceId"]

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
            "channelId": "0",
            "type": "1"
        }
    }

    url = f"https://openapi-{DATACENTER}.easy4ip.com/openapi/getKitToken"
    r = requests.post(url, json=body).json()

    return jsonify({
        "kitToken": r["result"]["data"]["kitToken"],
        "domain": domain
    })