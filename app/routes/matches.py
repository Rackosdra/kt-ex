"""
Match-Endpoints
Implementiert alle Match-bezogenen Endpoints aus API-Dokumentation
"""
from flask import Blueprint, jsonify, request
from app.models import db, Match, Group, Stage, Discipline
from app.services.sync_service import (
    fetch_single_match,
    update_match_result,
    update_match_live_result
)
import logging

matches_bp = Blueprint('matches', __name__)
logger = logging.getLogger('sync')


def format_match_response(match: Match, include_encounters: bool = True) -> dict:
    """
    Formatiert Match-Objekt gemäß API-Spec
    
    Berücksichtigt alle Match-Stati:
    - open: Wartet auf Ankündigung
    - paused: Pausiert
    - skipped: Übersprungen
    - running: Läuft
    - played: Beendet
    - planned: Geplant
    - incomplete: Wartet auf Team-Zuweisung
    - bye: Freilos
    """
    response = {
        "id": match.id,
        "team1_name": match.team1_name,
        "team2_name": match.team2_name,
        "state": match.state,
        "discipline_id": match.discipline_id,
        "discipline_name": match.discipline_name,
        "round_id": match.round_id,
        "round_name": match.round_name,
        "group_id": match.group_id,
        "group_name": match.group_name
    }
    
    # Scores nur bei fertigen oder laufenden Matches
    if match.state in ['running', 'played'] and match.display_score:
        response["display_score"] = match.display_score
        response["score1"] = match.score1
        response["score2"] = match.score2
    
    # Encounters nur wenn verfügbar und angefordert
    if include_encounters and match.encounters:
        response["encounters"] = match.encounters
    
    # Live-Result Flag
    if match.is_live_result:
        response["is_live_result"] = True
    
    # Zeitstempel
    if match.start_time:
        response["start_time"] = match.start_time.isoformat()
    if match.end_time:
        response["end_time"] = match.end_time.isoformat()
    
    # Court-Zuordnung
    if match.court_id:
        response["court_id"] = match.court_id
    
    return response


@matches_bp.route('/tournaments/<tournament_id>/matches/<match_id>', methods=['GET'])
def get_match(tournament_id: str, match_id: str):
    """
    GET /tournaments/:id/matches/:matchId
    
    Gibt detaillierte Match-Informationen zurück
    """
    match = Match.query.get(match_id)
    if not match:
        return jsonify({"error": "Match nicht gefunden"}), 404
    
    return jsonify(format_match_response(match)), 200


@matches_bp.route('/tournaments/<tournament_id>/matches/<match_id>/result', methods=['PUT'])
def set_match_result(tournament_id: str, match_id: str):
    """
    PUT /tournaments/:id/matches/:matchId/result
    
    Setzt finales Match-Ergebnis und beendet das Match
    
    Body-Format:
    {
        "result": [[[7, 5]]]  // Encounters → Sets → Scores
    }
    
    Beispiele:
    - Einfach (1 Set):        [[[7, 5]]]
    - Best of 3:              [[[7,5], [6,7], [7,2]]]
    - 3 Encounters, BO3:      [[[7,5],[6,7],[2,7]], [[7,2]], [[6,7],[7,5],[2,7],[7,5],[2,7]]]
    - Quick Entry (0/1):      [[[1, 0]]]
    """
    try:
        data = request.get_json()
        result = data.get('result')
        
        if not result or not isinstance(result, list):
            return jsonify({
                "error": "Invalid result format",
                "expected": "[[[score1, score2]]]"
            }), 400
        
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
    
    # Prüfe ob Match lokal existiert und im richtigen Status ist
    match = Match.query.get(match_id)
    if not match:
        return jsonify({
            "error": "Match nicht gefunden",
            "message": "Match existiert nicht in der lokalen DB"
        }), 404
    
    if match.state != 'running':
        return jsonify({
            "error": "Precondition Failed",
            "message": "Match is not running",
            "current_state": match.state
        }), 412
    
    # API-Call zum Setzen des Ergebnisses
    success, updated_match, error_msg = update_match_result(tournament_id, match_id, result)
    
    if not success:
        logger.error(f"❌ Fehler beim Setzen des Match-Ergebnisses: {error_msg}")
        
        if "not running" in error_msg.lower():
            return jsonify({
                "error": "Precondition Failed",
                "message": error_msg
            }), 412
        
        return jsonify({
            "error": "API Error",
            "message": error_msg
        }), 500
    
    # Aktualisiere lokale DB mit API-Response
    if updated_match:
        match.state = updated_match.get('state', 'played')
        match.encounters = updated_match.get('encounters')
        match.display_score = updated_match.get('displayScore')
        match.is_live_result = False
        
        db.session.commit()
        logger.info(f"✅ Match {match_id} Ergebnis gesetzt: {result}")
    
    return jsonify(format_match_response(match)), 200


@matches_bp.route('/tournaments/<tournament_id>/matches/<match_id>/live-result', methods=['PUT'])
def set_match_live_result(tournament_id: str, match_id: str):
    """
    PUT /tournaments/:id/matches/:matchId/live-result
    
    Aktualisiert Live-Score während Match läuft, ohne es zu beenden
    Nützlich für Live-Ticker und Echtzeit-Updates
    
    Body-Format: Identisch zu /result
    """
    try:
        data = request.get_json()
        result = data.get('result')
        
        if not result or not isinstance(result, list):
            return jsonify({
                "error": "Invalid result format",
                "expected": "[[[score1, score2]]]"
            }), 400
        
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
    
    match = Match.query.get(match_id)
    if not match:
        return jsonify({"error": "Match nicht gefunden"}), 404
    
    if match.state != 'running':
        return jsonify({
            "error": "Precondition Failed",
            "message": "Match is not running"
        }), 412
    
    success, updated_match, error_msg = update_match_live_result(tournament_id, match_id, result)
    
    if not success:
        logger.error(f"❌ Fehler beim Live-Result Update: {error_msg}")
        
        if "not running" in error_msg.lower():
            return jsonify({
                "error": "Precondition Failed",
                "message": error_msg
            }), 412
        
        return jsonify({
            "error": "API Error",
            "message": error_msg
        }), 500
    
    # Aktualisiere lokale DB
    if updated_match:
        match.encounters = updated_match.get('encounters')
        match.display_score = updated_match.get('displayScore')
        match.is_live_result = True
        
        db.session.commit()
        logger.info(f"📊 Match {match_id} Live-Score aktualisiert: {result}")
    
    return jsonify(format_match_response(match)), 200


@matches_bp.route('/tournaments/<tournament_id>/matches/running', methods=['GET'])
def get_running_matches(tournament_id: str):
    """
    GET /tournaments/:id/matches/running
    
    Gibt alle laufenden Matches eines Turniers zurück
    """
    matches = db.session.query(Match).join(
        Group
    ).join(
        Stage
    ).join(
        Discipline
    ).filter(
        Discipline.tournament_id == tournament_id,
        Match.state == 'running'
    ).all()
    
    return jsonify([format_match_response(m, include_encounters=False) for m in matches]), 200


@matches_bp.route('/tournaments/<tournament_id>/matches/by-state', methods=['GET'])
def get_matches_by_state(tournament_id: str):
    """
    GET /tournaments/:id/matches/by-state?state=played
    
    Filtert Matches nach Status
    
    Valid states:
    - open, paused, skipped, running, played, planned, incomplete, bye
    """
    state = request.args.get('state')
    
    if not state:
        return jsonify({
            "error": "Missing parameter 'state'",
            "valid_states": ["open", "paused", "skipped", "running", "played", "planned", "incomplete", "bye"]
        }), 400
    
    matches = db.session.query(Match).join(
        Group
    ).join(
        Stage
    ).join(
        Discipline
    ).filter(
        Discipline.tournament_id == tournament_id,
        Match.state == state
    ).all()
    
    return jsonify([format_match_response(m, include_encounters=False) for m in matches]), 200


@matches_bp.route('/tournaments/<tournament_id>/groups/<group_id>/matches', methods=['GET'])
def get_group_matches(tournament_id: str, group_id: str):
    """
    GET /tournaments/:id/groups/:groupId/matches?state=running
    
    Gibt alle Matches einer Gruppe zurück, optional gefiltert nach State
    """
    state_filter = request.args.get('state')
    
    query = Match.query.filter_by(group_id=group_id)
    if state_filter:
        query = query.filter_by(state=state_filter)
    
    matches = query.order_by(Match.start_time.desc()).all()
    
    return jsonify([format_match_response(m) for m in matches]), 200