import os
from flask import Flask
from extension.cors import init_cors
from extension.logging import init_logging
from utils.register import register_routes

def create_app(test_config=None):
    app = Flask(__name__)
    init_logging(app)
    init_cors(app)
    register_routes(app)

    if test_config is not None:
        app.config.update(test_config)

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT")))
