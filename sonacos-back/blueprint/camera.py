import time
import uuid
import hashlib
import base64
import requests
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, Response
from flask_cors import CORS

camera_bp = Blueprint("camera", __name__)
CORS(camera_bp)

# ─── CONFIG IMOU ──────────────────────────────────────────────────────────────
APP_ID     = "lcea5699cd1d7c4457"
APP_SECRET = "f464f4b27e934bcba36125d953a4c6"
DATACENTER = "fk"
BASE_URL   = f"https://openapi-{DATACENTER}.easy4ip.com"

# ─── CACHES ───────────────────────────────────────────────────────────────────
IMOU_TOKEN_CACHE = {
    "accessToken": None,
    "domain": None,
    "expires_at": 0,
}

KIT_TOKEN_CACHE = {}


# ─── Détection format image ───────────────────────────────────────────────────
def detect_image_type(data: bytes) -> str:
    if data[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    if b'ftyp' in data[:12]:
        return "image/avif"
    return "image/jpeg"


# ─── Helpers ──────────────────────────────────────────────────────────────────
def generate_sign():
    timestamp = int(time.time())
    nonce     = str(uuid.uuid4())
    raw       = f"time:{timestamp},nonce:{nonce},appSecret:{APP_SECRET}"
    sign      = hashlib.md5(raw.encode()).hexdigest()
    return timestamp, nonce, sign


def build_imou_body(params: dict):
    timestamp, nonce, sign = generate_sign()
    return {
        "system": {
            "ver":   "1.0",
            "appId": APP_ID,
            "sign":  sign,
            "time":  timestamp,
            "nonce": nonce,
        },
        "id":     str(uuid.uuid4()),
        "params": params,
    }


def post_to_imou(endpoint: str, params: dict, timeout: int = 15):
    url      = f"{BASE_URL}{endpoint}"
    body     = build_imou_body(params)
    response = requests.post(url, json=body, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if "result" not in result:
        raise Exception("Réponse IMOU invalide : champ 'result' absent")
    return result


def get_access_token():
    now = int(time.time())

    if (
        IMOU_TOKEN_CACHE["accessToken"]
        and IMOU_TOKEN_CACHE["domain"]
        and now < IMOU_TOKEN_CACHE["expires_at"]
    ):
        return IMOU_TOKEN_CACHE["accessToken"], IMOU_TOKEN_CACHE["domain"]

    url  = f"{BASE_URL}/openapi/accessToken"
    body = build_imou_body({})

    try:
        response = requests.post(url, json=body, timeout=15)

        print("=== IMOU accessToken DEBUG ===")
        print("STATUS CODE:", response.status_code)

        result = response.json()

        if "result" not in result or "data" not in result["result"]:
            print("Réponse IMOU invalide pour accessToken")
            return None, None

        data         = result["result"]["data"]
        access_token = data.get("accessToken")
        expire_time  = int(data.get("expireTime", 0))
        domain       = IMOU_TOKEN_CACHE.get("domain") or BASE_URL

        if not access_token:
            print("accessToken absent dans la réponse IMOU")
            return None, None

        IMOU_TOKEN_CACHE.update({
            "accessToken": access_token,
            "domain":      domain,
            "expires_at":  now + expire_time - 60,
        })

        return access_token, domain

    except requests.RequestException as e:
        print("Erreur HTTP get_access_token:", str(e))
        return None, None
    except ValueError as e:
        print("Erreur JSON get_access_token:", str(e))
        return None, None
    except Exception as e:
        print("Erreur get_access_token:", str(e))
        return None, None


def normalize_alarm(alarm: dict):
    type_map = {
        0: "human_infrared",
        1: "motion_detection",
        2: "unknown_alarm",
        3: "low_voltage_alarm",
    }
    raw_type = alarm.get("type")
    return {
        "alarmId":     alarm.get("alarmId"),
        "time":        alarm.get("time"),
        "type":        raw_type,
        "typeLabel":   type_map.get(raw_type, "unknown"),
        "thumbUrl":    alarm.get("thumbUrl"),
        "picurlArray": alarm.get("picurlArray", []),
        "raw":         alarm,
    }


def get_imou_alerts(
    token: str,
    device_id: str,
    channel_id: str = "0",
    begin_time: str = None,
    end_time: str = None,
    count: int = 30,
    next_alarm_id: str = "-1",
):
    if not begin_time or not end_time:
        now   = datetime.now()
        start = now - timedelta(hours=24)
        begin_time = start.strftime("%Y-%m-%d %H:%M:%S")
        end_time   = now.strftime("%Y-%m-%d %H:%M:%S")

    if count < 1 or count > 30:
        raise ValueError("count doit être compris entre 1 et 30")

    params = {
        "token":       token,
        "deviceId":    device_id,
        "channelId":   str(channel_id),
        "beginTime":   begin_time,
        "endTime":     end_time,
        "count":       count,
        "nextAlarmId": str(next_alarm_id),
    }

    result  = post_to_imou("/openapi/getAlarmMessage", params, timeout=20)
    data    = result.get("result", {}).get("data", {})
    alarms  = data.get("alarms", data.get("alarmMessages", []))
    next_id = data.get("nextAlarmId")

    return {
        "beginTime":   begin_time,
        "endTime":     end_time,
        "rawResult":   result,
        "rawData":     data,
        "alarms":      alarms,
        "nextAlarmId": next_id,
    }


# ─── Routes ───────────────────────────────────────────────────────────────────

@camera_bp.route("/sdk-config", methods=["GET"])
def sdk_config():
    token, domain = get_access_token()
    if not token or not domain:
        return jsonify({"error": "Impossible de récupérer la configuration SDK IMOU"}), 500
    return jsonify({"accessToken": token, "domain": domain})


@camera_bp.route("/devices", methods=["GET"])
def devices():
    token, _ = get_access_token()
    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500

    try:
        result = post_to_imou(
            "/openapi/listDeviceDetailsByPage",
            {
                "token":    token,
                "page":     1,
                "pageSize": 50,
                "source":   "bindAndShare",
            },
        )

        if "data" not in result["result"]:
            return jsonify({"error": "Réponse invalide de IMOU", "imou_response": result}), 400

        device_list = result["result"]["data"].get("deviceList", [])

        return jsonify([
            {
                "deviceId":   device.get("deviceId"),
                "deviceName": device.get("deviceName"),
                "status":     device.get("deviceStatus"),
                "channelId":  0,
            }
            for device in device_list
        ])

    except requests.RequestException as e:
        return jsonify({"error": "Erreur HTTP IMOU", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Erreur récupération caméras", "details": str(e)}), 500


@camera_bp.route("/device-online", methods=["POST"])
def device_online():
    data      = request.get_json(silent=True) or {}
    device_id = data.get("deviceId")

    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400

    token, _ = get_access_token()
    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500

    try:
        result = post_to_imou(
            "/openapi/deviceOnline",
            {"token": token, "deviceId": device_id},
        )
        return jsonify(result)

    except requests.RequestException as e:
        return jsonify({"error": "Erreur HTTP IMOU", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Erreur vérification statut caméra", "details": str(e)}), 500


@camera_bp.route("/kit-token", methods=["POST"])
def kit_token():
    data        = request.get_json(silent=True) or {}
    device_id   = data.get("deviceId")
    channel_id  = str(data.get("channelId", 0))
    stream_type = str(data.get("type", 1))
    encrypt_pwd = data.get("encryptPwd")

    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400

    cache_key = f"{device_id}_{channel_id}"
    now       = int(time.time())
    cached    = KIT_TOKEN_CACHE.get(cache_key)
    if cached and now < cached["expires_at"]:
        return jsonify({"kitToken": cached["kitToken"], "domain": cached["domain"]})

    token, domain = get_access_token()
    if not token or not domain:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500

    try:
        params = {
            "token":     token,
            "deviceId":  device_id,
            "channelId": channel_id,
            "type":      stream_type,
        }
        if encrypt_pwd:
            params["encryptPwd"] = encrypt_pwd

        result = post_to_imou("/openapi/getKitToken", params)

        if "data" not in result["result"]:
            return jsonify({"error": "Réponse invalide", "imou_response": result}), 400

        kit_token_value = result["result"]["data"].get("kitToken")

        if not kit_token_value:
            return jsonify({"error": "kitToken absent", "imou_response": result}), 400

        KIT_TOKEN_CACHE[cache_key] = {
            "kitToken":   kit_token_value,
            "domain":     domain,
            "expires_at": now + 300,
        }

        return jsonify({"kitToken": kit_token_value, "domain": domain})

    except requests.RequestException as e:
        return jsonify({"error": "Erreur HTTP IMOU", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Erreur génération kit token", "details": str(e)}), 500


@camera_bp.route("/image-proxy", methods=["GET"])
def image_proxy():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "url manquante"}), 400
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})

        if r.status_code != 200 or len(r.content) < 100:
            return jsonify({"error": "image vide ou expirée"}), 404

        content_type = r.headers.get("Content-Type", "")

        # Rejeter les réponses XML/texte (erreurs Alibaba OSS)
        if "xml" in content_type.lower() or "text" in content_type.lower():
            return jsonify({"error": "pas une image"}), 404

        # Détecter le vrai format depuis les magic bytes
        content_type = detect_image_type(r.content)

        b64      = base64.b64encode(r.content).decode("utf-8")
        data_url = f"data:{content_type};base64,{b64}"
        return jsonify({"dataUrl": data_url})

    except Exception as e:
        return jsonify({"error": str(e)}), 404


@camera_bp.route("/wakeup", methods=["POST"])
def wakeup_device():
    data      = request.get_json(silent=True) or {}
    device_id = data.get("deviceId")

    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400

    token, _ = get_access_token()
    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500

    try:
        result = post_to_imou(
            "/openapi/wakeupDevice",
            {"token": token, "deviceId": device_id},
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@camera_bp.route("/alerts", methods=["GET"])
def alerts():
    device_id     = request.args.get("deviceId")
    channel_id    = request.args.get("channelId", "0")
    begin_time    = request.args.get("beginTime")
    end_time      = request.args.get("endTime")
    next_alarm_id = request.args.get("nextAlarmId", "-1")

    try:
        count = int(request.args.get("count", 30))
    except ValueError:
        return jsonify({"error": "count doit être un entier"}), 400

    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400

    token, _ = get_access_token()
    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500

    try:
        alert_result = get_imou_alerts(
            token=token,
            device_id=device_id,
            channel_id=channel_id,
            begin_time=begin_time,
            end_time=end_time,
            count=count,
            next_alarm_id=next_alarm_id,
        )

        raw_data       = alert_result.get("rawData", {})
        raw_alarms     = alert_result.get("alarms", [])
        next_id        = alert_result.get("nextAlarmId")
        final_begin    = alert_result.get("beginTime")
        final_end      = alert_result.get("endTime")
        cleaned_alarms = [normalize_alarm(alarm) for alarm in raw_alarms]

        return jsonify({
            "success":     True,
            "deviceId":    device_id,
            "channelId":   channel_id,
            "beginTime":   final_begin,
            "endTime":     final_end,
            "count":       len(cleaned_alarms),
            "nextAlarmId": next_id,
            "message":     "Aucune alerte trouvée" if len(cleaned_alarms) == 0 else "Alertes récupérées avec succès",
            "rawData":     raw_data,
            "alarms":      cleaned_alarms,
        }), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except requests.RequestException as e:
        return jsonify({"error": "Erreur HTTP IMOU", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Erreur récupération alertes", "details": str(e)}), 500