from flask_cors import CORS

def init_cors(app):

    @app.after_request
    def add_headers(response):
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    CORS(app, resources={
        r"/image-proxy": {"origins": "*"},  # pas de credentials pour les images
        r"/*": {"origins": "http://localhost:5173", "supports_credentials": True}
    })