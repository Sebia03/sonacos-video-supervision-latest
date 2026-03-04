from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    set_access_cookies,
    unset_jwt_cookies,
)
from datetime import timedelta
import os

auth_bp = Blueprint("auth", __name__)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


# ==========================
# 🔑 LOGIN
# ==========================
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    # Vérification des identifiants admin
    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        return jsonify({"error": "Invalid credentials"}), 401

    # Création du token (expire en 2h)
    access_token = create_access_token(
        identity="admin",
        expires_delta=timedelta(hours=2),
    )

    # Réponse avec cookie HTTP-only
    response = jsonify({"message": "Login successful"})
    set_access_cookies(response, access_token)

    return response, 200


# ==========================
# 🚪 LOGOUT
# ==========================
@auth_bp.route("/logout", methods=["POST"])
def logout():
    response = jsonify({"message": "Logout successful"})
    unset_jwt_cookies(response)
    return response, 200