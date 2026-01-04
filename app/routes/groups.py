"""
Groups-Endpoints
Implementiert Group-Operationen gemäß API-Dokumentation
"""
from flask import Blueprint, jsonify, request
from app.models import db, Group, Stage, Standing, Match, Entry

groups_bp = Blueprint('groups', __name__)


def format_group_response(group: Group, include_stats: bool = False) -> dict:
    """
    Formatiert Group-Objekt gemäß API-Spec
    
    Basic Response:
    {
        "id": "...",
        "name": "...",
        "tournament_mode": "swiss",
        "state": "running",
        "options": {...}
    }
    
    Options-Struktur (aus API-Doku):
    {
        "matchConfigurations": [
            {
                "name": "Encounter 1",
                "draw": false,
                "numPoints": 7,
                "numSets": 1,
                "twoAhead": false,
                "quickEntry": false
            }
        ],
        "eliminationThirdPlace": true (nur bei Elimination)
    }
    """
    response = {
        "id": group.id,
        "name": group.name,
        "tournament_mode": group.tournament_mode,
        "state": group.state,
        "options": group.options or {}
    }
    
    if include_stats:
        response["standings_count"] = Standing.query.filter_by(group_id=group.id).count()
        response["matches_count"] = Match.query.filter_by(group_id=group.id).count()
        response["matches_played"] = Match.query.filter_by(group_id=group.id, state='played').count()
        response["matches_running"] = Match.query.filter_by(group_id=group.id, state='running').count()
    
    return response


@groups_bp.route('/tournaments/<tournament_id>/disciplines/<discipline_id>/groups', methods=['GET'])
def get_discipline_groups(tournament_id: str, discipline_id: str):
    """
    GET /tournaments/:id/disciplines/:disciplineId/groups
    
    Gibt alle Gruppen einer Disziplin zurück
    
    Tournament Modes (aus API-Doku):
    - swiss: Schweizer System
    - round_robin: Jeder gegen Jeden
    - elimination: K.O.-System
    - double_elimination: Doppel-K.O.
    - monster_dyp: Wechselnde Teams pro Runde
    - last_one_standing: Leben-basiertes System
    - lord_have_mercy: Mit Gnadensystem
    - rounds: Feste Runden
    - snake_draw: Schlangen-Auslosung
    - dutch_system: Holländisches System
    - whist: Whist-Modus
    """
    groups = db.session.query(Group).join(Stage).filter(
        Stage.discipline_id == discipline_id
    ).all()
    
    return jsonify([
        format_group_response(g, include_stats=True) 
        for g in groups
    ]), 200


@groups_bp.route('/tournaments/<tournament_id>/groups/<group_id>', methods=['GET'])
def get_single_group(tournament_id: str, group_id: str):
    """
    GET /tournaments/:id/groups/:groupId
    
    Gibt detaillierte Informationen zu einer Group zurück
    """
    group = Group.query.get(group_id)
    if not group:
        return jsonify({"error": "Gruppe nicht gefunden"}), 404
    
    return jsonify(format_group_response(group, include_stats=True)), 200


@groups_bp.route('/tournaments/<tournament_id>/groups/<group_id>/entries', methods=['GET'])
def get_group_entries(tournament_id: str, group_id: str):
    """
    GET /tournaments/:id/groups/:groupId/entries
    
    Gibt alle Entries (Teilnehmer) einer Gruppe zurück
    
    Dies sind die Entries die in dieser Gruppe spielen.
    """
    # Hole alle Standings der Gruppe (jedes Standing repräsentiert einen Entry)
    standings = Standing.query.filter_by(group_id=group_id).all()
    
    # Extrahiere unique Entry-IDs
    entry_ids = list(set([s.entry_id for s in standings if s.entry_id]))
    
    # Hole Entry-Details
    entries = Entry.query.filter(Entry.id.in_(entry_ids)).all()
    
    return jsonify([{
        "id": e.id,
        "name": e.name
    } for e in entries]), 200


@groups_bp.route('/tournaments/<tournament_id>/groups/by-mode', methods=['GET'])
def get_groups_by_mode(tournament_id: str):
    """
    GET /tournaments/:id/groups/by-mode?mode=swiss
    
    Filtert Groups nach Tournament Mode (Custom Endpoint)
    """
    mode = request.args.get('mode')
    
    if not mode:
        return jsonify({
            "error": "Missing parameter 'mode'",
            "valid_modes": [
                "swiss", "round_robin", "elimination", "double_elimination",
                "monster_dyp", "last_one_standing", "lord_have_mercy",
                "rounds", "snake_draw", "dutch_system", "whist"
            ]
        }), 400
    
    from app.models import Discipline
    
    groups = db.session.query(Group).join(
        Stage
    ).join(
        Discipline
    ).filter(
        Discipline.tournament_id == tournament_id,
        Group.tournament_mode == mode
    ).all()
    
    return jsonify([
        format_group_response(g, include_stats=True) 
        for g in groups
    ]), 200