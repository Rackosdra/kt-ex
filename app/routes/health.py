"""
Health-Endpoints
Verantwortlich für: System-Health-Checks und Monitoring
"""
from flask import Blueprint, jsonify
from datetime import datetime
from app.models import db

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health-Check Endpoint für Monitoring"""
    try:
        # Test DB-Verbindung
        db.session.execute(db.text('SELECT 1'))
        
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 503