from flask import Flask
from flask_login import LoginManager
import os.path

app = Flask(__name__)
app.config.from_pyfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.cfg"))
login_manager = LoginManager()
import login
login_manager.setup_app(app)
import endpoints
