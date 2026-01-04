import os
import logging
from flask import Flask
from .models import db

def create_app():
    """Application Factory Pattern für bessere Testbarkeit"""
    app = Flask(__name__)
    
    # Konfiguration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL',
        'postgresql://user:password@localhost:5432/kickertool_db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,  # Verhindert "Lost Connection" Fehler
    }
    
    # JSON-Config für bessere Lesbarkeit
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    
    # Initialisiere DB
    db.init_app(app)
    
    # Erstelle Tabellen
    with app.app_context():
        db.create_all()
        logging.info("Datenbank-Tabellen erfolgreich initialisiert")
    
    # Registriere Blueprints
    from app.routes import api
    app.register_blueprint(api)
    
    # Basis-Route für Debugging
    @app.route('/')
    def index():
        return {
            "service": "Kickertool API",
            "version": "2.0",
            "status": "running",
            "endpoints": {
                "health": "/health",
                "webhook_prod": "/webhook/kickertool",
                "webhook_test": "/webhook/test",
                "tournament_stats": "/tournaments/<id>/stats"
            }
        }
    
    return app