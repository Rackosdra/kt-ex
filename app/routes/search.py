"""
Search-Endpoints
Verantwortlich für: Suche nach Teams, Spielern und Gruppen
"""
from flask import Blueprint, jsonify, request
from app.models import db, Entry, Standing, Group, Stage, Discipline

search_bp = Blueprint('search', __name__)


@search_bp.route('/tournaments/<tournament_id>/search', methods=['GET'])
def search_tournament(tournament_id: str):
    """Suche nach Teams/Spielern"""
    query = request.args.get('q', '').lower()
    
    if not query or len(query) < 2:
        return jsonify({
            "error": "Query muss mindestens 2 Zeichen haben"
        }), 400
    
    # Suche in Entries
    entries = Entry.query.filter(
        Entry.tournament_id == tournament_id,
        Entry.name.ilike(f'%{query}%')
    ).limit(20).all()
    
    # Suche in Standings
    standings = db.session.query(Standing).join(
        Group
    ).join(
        Stage
    ).join(
        Discipline
    ).filter(
        Discipline.tournament_id == tournament_id,
        Standing.team_name.ilike(f'%{query}%')
    ).limit(20).all()
    
    return jsonify({
        "entries": [{
            "id": e.id,
            "name": e.name,
            "type": "entry"
        } for e in entries],
        "standings": [{
            "group_id": s.group_id,
            "team_name": s.team_name,
            "rank": s.rank,
            "points": s.points,
            "type": "standing"
        } for s in standings]
    }), 200