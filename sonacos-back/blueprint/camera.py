import time
import uuid
import hashlib
import requests
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_cors import CORS

camera_bp = Blueprint("camera", __name__)
CORS(camera_bp)

# CONFIG IMOU pour la connexion au compte dev
APP_ID = "lcea5699cd1d7c4457"
APP_SECRET = "f464f4b27e934bcba36125d953a4c6"
DATACENTER = "fk"

BASE_URL = f"https://openapi-{DATACENTER}.easy4ip.com"

IMOU_TOKEN_CACHE = {
    "accessToken": None,
    "domain": None,
    "expires_at": 0,
}


def generate_sign():
    timestamp = int(time.time())
    nonce = str(uuid.uuid4())
    raw = f"time:{timestamp},nonce:{nonce},appSecret:{APP_SECRET}"
    sign = hashlib.md5(raw.encode()).hexdigest()
    return timestamp, nonce, sign


def build_imou_body(params: dict):
    timestamp, nonce, sign = generate_sign()

    return {
        "system": {
            "ver": "1.0",
            "appId": APP_ID,
            "sign": sign,
            "time": timestamp,
            "nonce": nonce,
        },
        "id": str(uuid.uuid4()),
        "params": params,
    }


def post_to_imou(endpoint: str, params: dict, timeout: int = 15):
    url = f"{BASE_URL}{endpoint}"
    body = build_imou_body(params)

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

    url = f"{BASE_URL}/openapi/accessToken"
    body = build_imou_body({})

    try:
        response = requests.post(url, json=body, timeout=15)

        print("=== IMOU accessToken DEBUG ===")
        print("URL:", url)
        print("STATUS CODE:", response.status_code)
        print("RAW TEXT:", response.text)

        result = response.json()
        print("JSON PARSE:", result)

        if "result" not in result or "data" not in result["result"]:
            print("Réponse IMOU invalide pour accessToken")
            return None, None

        data = result["result"]["data"]

        access_token = data.get("accessToken")
        expire_time = int(data.get("expireTime", 0))
        domain = IMOU_TOKEN_CACHE.get("domain") or BASE_URL

        if not access_token:
            print("accessToken absent dans la réponse IMOU")
            return None, None

        IMOU_TOKEN_CACHE.update(
            {
                "accessToken": access_token,
                "domain": domain,
                "expires_at": now + expire_time - 60,
            }
        )

        return access_token, domain

    except requests.RequestException as e:
        print("Erreur HTTP get_access_token:", str(e))
        return None, None
    except ValueError as e:
        print("Erreur JSON get_access_token:", str(e))
        print("RAW TEXT non JSON:", response.text if "response" in locals() else "pas de réponse")
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
        "alarmId": alarm.get("alarmId"),
        "time": alarm.get("time"),
        "type": raw_type,
        "typeLabel": type_map.get(raw_type, "unknown"),
        "thumbUrl": alarm.get("thumbUrl"),
        "picurlArray": alarm.get("picurlArray", []),
        "raw": alarm,
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
        now = datetime.now()
        start = now - timedelta(hours=24)
        begin_time = start.strftime("%Y-%m-%d %H:%M:%S")
        end_time = now.strftime("%Y-%m-%d %H:%M:%S")

    if count < 1 or count > 30:
        raise ValueError("count doit être compris entre 1 et 30")

    params = {
        "token": token,
        "deviceId": device_id,
        "channelId": str(channel_id),
        "beginTime": begin_time,
        "endTime": end_time,
        "count": count,
        "nextAlarmId": str(next_alarm_id),
    }

    result = post_to_imou("/openapi/getAlarmMessage", params, timeout=20)

    print("\n===== REPONSE BRUTE IMOU ALERTS =====")
    print(result)
    print("=====================================\n")

    data = result.get("result", {}).get("data", {})

    # Certaines réponses IMOU utilisent "alarms" au lieu de "alarmMessages"
    alarms = data.get("alarms", data.get("alarmMessages", []))

    next_id = data.get("nextAlarmId")

    # Debug supplémentaire si la structure diffère
    print("===== DEBUG DATA ALERTS =====")
    print("Clés disponibles dans data :", list(data.keys()) if isinstance(data, dict) else data)
    print("Valeur de alarmMessages :", alarms)
    print("Valeur de nextAlarmId :", data.get("nextAlarmId"))
    print("=============================\n")



    return {
        "beginTime": begin_time,
        "endTime": end_time,
        "rawResult": result,
        "rawData": data,
        "alarms": alarms,
        "nextAlarmId": next_id,
    }


@camera_bp.route("/sdk-config", methods=["GET"])
def sdk_config():
    token, domain = get_access_token()

    if not token or not domain:
        return jsonify({"error": "Impossible de récupérer la configuration SDK IMOU"}), 500

    return jsonify(
        {
            "accessToken": token,
            "domain": domain,
        }
    )


@camera_bp.route("/devices", methods=["GET"])
def devices():
    token, _ = get_access_token()

    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500

    try:
        result = post_to_imou(
            "/openapi/listDeviceDetailsByPage",
            {
                "token": token,
                "page": 1,
                "pageSize": 50,
                "source": "bindAndShare",
            },
        )

        print("IMOU devices response:", result)

        if "data" not in result["result"]:
            return jsonify(
                {
                    "error": "Réponse invalide de IMOU pour la liste des caméras",
                    "imou_response": result,
                }
            ), 400

        device_list = result["result"]["data"].get("deviceList", [])

        return jsonify(
            [
                {
                    "deviceId": device.get("deviceId"),
                    "deviceName": device.get("deviceName"),
                    "status": device.get("deviceStatus"),
                    "channelId": 0,
                }
                for device in device_list
            ]
        )

    except requests.RequestException as e:
        return jsonify({"error": "Erreur HTTP IMOU", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Erreur récupération caméras", "details": str(e)}), 500


@camera_bp.route("/device-online", methods=["POST"])
def device_online():
    data = request.get_json(silent=True) or {}
    device_id = data.get("deviceId")

    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400

    token, _ = get_access_token()

    if not token:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500

    try:
        result = post_to_imou(
            "/openapi/deviceOnline",
            {
                "token": token,
                "deviceId": device_id,
            },
        )

        print("IMOU deviceOnline response:", result)
        return jsonify(result)

    except requests.RequestException as e:
        return jsonify({"error": "Erreur HTTP IMOU", "details": str(e)}), 500
    except Exception as e:
        return jsonify(
            {"error": "Erreur lors de la vérification du statut caméra", "details": str(e)}
        ), 500


@camera_bp.route("/kit-token", methods=["POST"])
def kit_token():
    data = request.get_json(silent=True) or {}
    device_id = data.get("deviceId")
    channel_id = str(data.get("channelId", 0))
    stream_type = str(data.get("type", 1))

    if not device_id:
        return jsonify({"error": "deviceId manquant"}), 400

    token, domain = get_access_token()

    if not token or not domain:
        return jsonify({"error": "Impossible de récupérer le token IMOU"}), 500

    try:
        result = post_to_imou(
            "/openapi/getKitToken",
            {
                "token": token,
                "deviceId": device_id,
                "channelId": channel_id,
                "type": stream_type,
            },
        )

        print("IMOU kit-token response:", result)

        if "data" not in result["result"]:
            return jsonify(
                {
                    "error": "Réponse invalide de IMOU pour le kit token",
                    "imou_response": result,
                }
            ), 400

        kit_token_value = result["result"]["data"].get("kitToken")

        if not kit_token_value:
            return jsonify(
                {
                    "error": "kitToken absent dans la réponse IMOU",
                    "imou_response": result,
                }
            ), 400

        return jsonify(
            {
                "kitToken": kit_token_value,
                "domain": domain,
            }
        )

    except requests.RequestException as e:
        return jsonify({"error": "Erreur HTTP IMOU", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Erreur génération kit token", "details": str(e)}), 500


@camera_bp.route("/alerts", methods=["GET"])
def alerts():
    """
    Exemples :
    GET /alerts?deviceId=4909BBDPSF5AED4
    GET /alerts?deviceId=4909BBDPSF5AED4&channelId=0
    GET /alerts?deviceId=4909BBDPSF5AED4&count=10
    GET /alerts?deviceId=4909BBDPSF5AED4&beginTime=2026-04-01 00:00:00&endTime=2026-04-08 23:59:59
    """

    device_id = request.args.get("deviceId")
    channel_id = request.args.get("channelId", "0")
    begin_time = request.args.get("beginTime")
    end_time = request.args.get("endTime")
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

        raw_data = alert_result.get("rawData", {})
        raw_alarms = alert_result.get("alarms", [])
        next_id = alert_result.get("nextAlarmId")
        final_begin_time = alert_result.get("beginTime")
        final_end_time = alert_result.get("endTime")

        cleaned_alarms = [normalize_alarm(alarm) for alarm in raw_alarms]

        print("\n===== ALERTES IMOU =====")
        print("deviceId:", device_id)
        print("channelId:", channel_id)
        print("beginTime:", final_begin_time)
        print("endTime:", final_end_time)
        print("count demandé:", count)
        print("nombre d'alertes:", len(cleaned_alarms))
        print("nextAlarmId:", next_id)

        for alert in cleaned_alarms:
            print(alert)

        print("========================\n")

        return jsonify(
            {
                "success": True,
                "deviceId": device_id,
                "channelId": channel_id,
                "beginTime": final_begin_time,
                "endTime": final_end_time,
                "count": len(cleaned_alarms),
                "nextAlarmId": next_id,
                "message": "Aucune alerte trouvée sur cette période" if len(cleaned_alarms) == 0 else "Alertes récupérées avec succès",
                "rawData": raw_data,
                "alarms": cleaned_alarms,
            }
        ), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except requests.RequestException as e:
        return jsonify({"error": "Erreur HTTP IMOU", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Erreur récupération alertes", "details": str(e)}), 500