"""
Application Factory
Erstellt und konfiguriert die Flask-App mit allen Features aus API-Dokumentation
"""
import os
import logging
from flask import Flask, jsonify
from .models import db
from .utils.logger import setup_all_loggers


def create_app():
    """Application Factory Pattern für bessere Testbarkeit"""
    app = Flask(__name__)
    
    # Logger initialisieren (vor allem anderen)
    setup_all_loggers()
    
    # Konfiguration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL',
        'postgresql://user:password@localhost:5432/kickertool_db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }
    
    # JSON-Config
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    
    # Initialisiere DB
    db.init_app(app)
    
    # Erstelle Tabellen
    with app.app_context():
        db.create_all()
        logging.info("✅ Datenbank-Tabellen erfolgreich initialisiert")
    
    # Registriere Blueprints
    from app.routes.health import health_bp
    from app.routes.webhooks import webhook_bp
    from app.routes.tournaments import tournaments_bp
    from app.routes.matches import matches_bp
    from app.routes.standings import standings_bp
    from app.routes.groups import groups_bp
    from app.routes.courts import courts_bp
    from app.routes.search import search_bp
    
    app.register_blueprint(health_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(tournaments_bp)
    app.register_blueprint(matches_bp)
    app.register_blueprint(standings_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(courts_bp)
    app.register_blueprint(search_bp)
    
    # Error Handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "error": "Not Found",
            "message": "Der angeforderte Endpoint existiert nicht"
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            "error": "Internal Server Error",
            "message": "Ein interner Fehler ist aufgetreten"
        }), 500
    
    # Root-Route mit API-Dokumentation
    @app.route('/')
    def index():
        return {
            "service": "Kickertool API",
            "version": "2.1",
            "status": "running",
            "documentation": "https://api.tournament.io/v1/public/docs",
            "endpoints": {
                "health": {
                    "path": "/health",
                    "method": "GET",
                    "description": "Health Check"
                },
                "webhooks": {
                    "prod": {
                        "path": "/webhook/kickertool",
                        "method": "POST",
                        "description": "Produktions-Webhook für Kickertool Events"
                    },
                    "test": {
                        "path": "/webhook/test",
                        "method": "POST",
                        "description": "Test-Webhook für Debugging"
                    }
                },
                "tournaments": {
                    "list": {
                        "path": "/tournaments?limit=25&offset=0&state=running",
                        "method": "GET",
                        "description": "Liste aller Turniere"
                    },
                    "get": {
                        "path": "/tournaments/<id>",
                        "method": "GET",
                        "description": "Tournament mit vollständiger Struktur"
                    },
                    "stats": {
                        "path": "/tournaments/<id>/stats",
                        "method": "GET",
                        "description": "Tournament-Statistiken"
                    },
                    "sync": {
                        "path": "/tournaments/<id>/sync",
                        "method": "POST",
                        "description": "Manueller Sync"
                    }
                },
                "entries": {
                    "tournament": {
                        "path": "/tournaments/<id>/entries",
                        "method": "GET",
                        "description": "Alle Tournament-Entries"
                    },
                    "discipline": {
                        "path": "/tournaments/<id>/disciplines/<discipline_id>/entries",
                        "method": "GET",
                        "description": "Discipline-Entries"
                    },
                    "group": {
                        "path": "/tournaments/<id>/groups/<group_id>/entries",
                        "method": "GET",
                        "description": "Group-Entries"
                    }
                },
                "courts": {
                    "list": {
                        "path": "/tournaments/<id>/courts?includeMatchDetails=true",
                        "method": "GET",
                        "description": "Alle Courts"
                    },
                    "get": {
                        "path": "/tournaments/<id>/courts/<court_id>",
                        "method": "GET",
                        "description": "Einzelner Court"
                    },
                    "active": {
                        "path": "/tournaments/<id>/courts/active",
                        "method": "GET",
                        "description": "Courts mit zugewiesenem Match"
                    },
                    "free": {
                        "path": "/tournaments/<id>/courts/free",
                        "method": "GET",
                        "description": "Freie Courts"
                    }
                },
                "matches": {
                    "get": {
                        "path": "/tournaments/<id>/matches/<match_id>",
                        "method": "GET",
                        "description": "Einzelnes Match"
                    },
                    "set_result": {
                        "path": "/tournaments/<id>/matches/<match_id>/result",
                        "method": "PUT",
                        "description": "Match-Ergebnis setzen (beendet Match)"
                    },
                    "set_live_result": {
                        "path": "/tournaments/<id>/matches/<match_id>/live-result",
                        "method": "PUT",
                        "description": "Live-Score aktualisieren (Match läuft weiter)"
                    },
                    "running": {
                        "path": "/tournaments/<id>/matches/running",
                        "method": "GET",
                        "description": "Alle laufenden Matches"
                    },
                    "by_state": {
                        "path": "/tournaments/<id>/matches/by-state?state=played",
                        "method": "GET",
                        "description": "Matches nach Status"
                    },
                    "group": {
                        "path": "/tournaments/<id>/groups/<group_id>/matches?state=running",
                        "method": "GET",
                        "description": "Alle Matches einer Gruppe"
                    }
                },
                "standings": {
                    "group": {
                        "path": "/tournaments/<id>/groups/<group_id>/standings",
                        "method": "GET",
                        "description": "Rangliste einer Gruppe"
                    },
                    "discipline": {
                        "path": "/tournaments/<id>/disciplines/<discipline_id>/standings",
                        "method": "GET",
                        "description": "Aggregierte Standings einer Disziplin"
                    }
                },
                "groups": {
                    "discipline": {
                        "path": "/tournaments/<id>/disciplines/<discipline_id>/groups",
                        "method": "GET",
                        "description": "Alle Gruppen einer Disziplin"
                    },
                    "get": {
                        "path": "/tournaments/<id>/groups/<group_id>",
                        "method": "GET",
                        "description": "Einzelne Gruppe"
                    },
                    "by_mode": {
                        "path": "/tournaments/<id>/groups/by-mode?mode=swiss",
                        "method": "GET",
                        "description": "Gruppen nach Tournament-Mode"
                    }
                },
                "disciplines": {
                    "list": {
                        "path": "/tournaments/<id>/disciplines",
                        "method": "GET",
                        "description": "Alle Disziplinen"
                    }
                },
                "search": {
                    "path": "/tournaments/<id>/search?q=<query>",
                    "method": "GET",
                    "description": "Suche nach Teams/Spielern"
                }
            },
            "webhook_events": [
                "TournamentAdded",
                "TournamentUpdated",
                "MatchUpdated",
                "CourtMatchChanged",
                "EntryListUpdated",
                "StandingsUpdated"
            ],
            "tournament_modes": [
                "swiss",
                "round_robin",
                "elimination",
                "double_elimination",
                "monster_dyp",
                "last_one_standing",
                "lord_have_mercy",
                "rounds",
                "snake_draw",
                "dutch_system",
                "whist"
            ],
            "match_states": [
                "open",
                "paused",
                "skipped",
                "running",
                "played",
                "planned",
                "incomplete",
                "bye"
            ],
            "tournament_states": [
                "planned",
                "pre-registration",
                "check-in",
                "ready",
                "running",
                "finished",
                "cancelled"
            ]
        }
    
    return app