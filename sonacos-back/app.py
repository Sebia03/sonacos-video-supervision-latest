import os
from flask import Flask
from flask_jwt_extended import JWTManager
from extension.cors import init_cors
from extension.logging import init_logging
from utils.register import register_routes
from dotenv import load_dotenv
from database import init_db

load_dotenv()

def create_app(test_config=None):
    app = Flask(__name__)

    # JWT config
    app.config["JWT_SECRET_KEY"]           = os.getenv("JWT_SECRET_KEY", "fallback-secret-key")
    app.config["JWT_TOKEN_LOCATION"]       = ["cookies"]
    app.config["JWT_COOKIE_SECURE"]        = False   # True en production HTTPS
    app.config["JWT_COOKIE_CSRF_PROTECT"]  = False   # Simplifier pour le dev local
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 7200    # 2 heures
    app.config["JWT_COOKIE_SAMESITE"]      = "Lax"   # Autoriser les cookies cross-origin

    JWTManager(app)

    init_db()  # Initialise la base de données SQLite

    init_logging(app)
    init_cors(app)
    register_routes(app)

    if test_config is not None:
        app.config.update(test_config)

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))