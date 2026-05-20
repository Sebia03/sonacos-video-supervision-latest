import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    set_access_cookies,
    unset_jwt_cookies,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from datetime import timedelta
from database import get_user_by_email, verify_password

auth_bp = Blueprint("auth", __name__)


# ==========================
# 🔑 LOGIN
# ==========================
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    email    = data.get("email") or data.get("username")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email et mot de passe requis"}), 400

    user = get_user_by_email(email)

    if not user or not verify_password(password, user["password"]):
        return jsonify({"error": "Identifiants invalides"}), 401

    # Token avec role et site dans les claims
    additional_claims = {
        "role": user["role"],
        "site": user["site"],
        "email": user["email"],
    }

    access_token = create_access_token(
        identity=str(user["id"]),
        additional_claims=additional_claims,
        expires_delta=timedelta(hours=2),
    )

    response = jsonify({
        "message": "Login successful",
        "user": {
            "id":    user["id"],
            "email": user["email"],
            "role":  user["role"],
            "site":  user["site"],
        }
    })
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


# ==========================
# 👤 MOI (profil connecté)
# ==========================
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    claims = get_jwt()
    return jsonify({
        "id":    get_jwt_identity(),
        "email": claims.get("email"),
        "role":  claims.get("role"),
        "site":  claims.get("site"),
    })