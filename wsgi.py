from flask import Flask
from app import app as app1
from app_gemini_new import app as app2

application = Flask(__name__)

# Registra os dois apps em rotas diferentes
application.register_blueprint(app1, url_prefix='/app1')
application.register_blueprint(app2, url_prefix='/app2')
