from flask_cors import CORS

def init_cors(app):
    from flask import Flask, jsonify, request
    # ... imports existants ...

    # Créez votre app Flask principale si ce n'est pas déjà fait
    # app = Flask(__name__)

    # Ajoutez ce bloc pour forcer les en-têtes COOP/COEP sur toutes les réponses
    @app.after_request
    def add_cors_headers(response):
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
        # La ligne CORS suivante est peut-être déjà gérée par flask_cors, mais c'est un filet de sécurité
        # response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    # ... le reste de votre code (blueprints, routes, etc.) ...

    CORS(app, resources={r"/*": {"origins": "*"}})