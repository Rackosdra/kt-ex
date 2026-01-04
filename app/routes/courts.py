"""
Courts-Endpoints
Implementiert Court-Verwaltung gemäß API-Dokumentation
"""
from flask import Blueprint, jsonify, request
from app.models import Court, Match
from app.services.sync_service import fetch_courts

courts_bp = Blueprint('courts', __name__)


def format_court_response(court: Court, include_match_details: bool = False) -> dict:
    """
    Formatiert Court-Objekt gemäß API-Spec
    
    Basic Response:
    {
        "id": "tio:...",
        "number": 1,
        "name": "Table 1",
        "currentMatchId": "tio:..." (optional)
    }
    
    With includeMatchDetails=true:
    + "currentMatch": { ... vollständige Match-Daten ... }
    """
    response = {
        "id": court.id,
        "number": court.number,
        "name": court.name
    }
    
    if court.current_match_id:
        response["current_match_id"] = court.current_match_id
        
        # Füge Match-Details hinzu wenn angefordert
        if include_match_details:
            match = Match.query.get(court.current_match_id)
            if match:
                response["current_match"] = {
                    "id": match.id,
                    "team1_name": match.team1_name,
                    "team2_name": match.team2_name,
                    "score1": match.score1,
                    "score2": match.score2,
                    "display_score": match.display_score,
                    "state": match.state,
                    "discipline_name": match.discipline_name,
                    "round_name": match.round_name,
                    "group_name": match.group_name,
                    "start_time": match.start_time.isoformat() if match.start_time else None,
                    "is_live_result": match.is_live_result
                }
    
    return response


@courts_bp.route('/tournaments/<tournament_id>/courts', methods=['GET'])
def get_courts(tournament_id: str):
    """
    GET /tournaments/:id/courts?includeMatchDetails=true
    
    Gibt alle Courts/Tische eines Turniers zurück
    
    Parameter:
    - includeMatchDetails: Boolean (default: false)
      Wenn true, werden vollständige Match-Details für currentMatch inkludiert
    """
    include_match_details = request.args.get('includeMatchDetails', 'false').lower() == 'true'
    
    courts = Court.query.filter_by(
        tournament_id=tournament_id
    ).order_by(Court.number).all()
    
    return jsonify([
        format_court_response(c, include_match_details) 
        for c in courts
    ]), 200


@courts_bp.route('/tournaments/<tournament_id>/courts/<court_id>', methods=['GET'])
def get_single_court(tournament_id: str, court_id: str):
    """
    GET /tournaments/:id/courts/:courtId?includeMatchDetails=true
    
    Gibt einen einzelnen Court zurück
    """
    include_match_details = request.args.get('includeMatchDetails', 'false').lower() == 'true'
    
    court = Court.query.get(court_id)
    if not court or court.tournament_id != tournament_id:
        return jsonify({"error": "Court nicht gefunden"}), 404
    
    return jsonify(format_court_response(court, include_match_details)), 200


@courts_bp.route('/tournaments/<tournament_id>/courts/active', methods=['GET'])
def get_active_courts(tournament_id: str):
    """
    GET /tournaments/:id/courts/active
    
    Gibt alle Courts zurück die aktuell ein Match zugewiesen haben
    """
    courts = Court.query.filter(
        Court.tournament_id == tournament_id,
        Court.current_match_id.isnot(None)
    ).order_by(Court.number).all()
    
    # Immer mit Match-Details bei aktiven Courts
    return jsonify([
        format_court_response(c, include_match_details=True) 
        for c in courts
    ]), 200


@courts_bp.route('/tournaments/<tournament_id>/courts/free', methods=['GET'])
def get_free_courts(tournament_id: str):
    """
    GET /tournaments/:id/courts/free
    
    Gibt alle freien Courts zurück (ohne zugewiesenes Match)
    """
    courts = Court.query.filter(
        Court.tournament_id == tournament_id,
        Court.current_match_id.is_(None)
    ).order_by(Court.number).all()
    
    return jsonify([
        format_court_response(c, include_match_details=False) 
        for c in courts
    ]), 200