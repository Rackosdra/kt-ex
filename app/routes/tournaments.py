"""
Tournament-Endpoints
Implementiert alle Tournament-Operationen aus API-Dokumentation
"""
from flask import Blueprint, jsonify, request
from app.models import db, Tournament, Entry, Discipline, Stage, Match, Court
from app.services.sync_service import (
    fetch_tournaments_list,
    fetch_tournament_entries,
    sync_tournament_data
)
import logging

tournaments_bp = Blueprint('tournaments', __name__, url_prefix='/tournaments')
logger = logging.getLogger('sync')


def format_tournament_response(tournament: Tournament, include_full_structure: bool = False) -> dict:
    """
    Formatiert Tournament-Objekt gemäß API-Spec
    
    Basic Response (für Listen):
    {
        "id": "tio:...",
        "name": "...",
        "state": "running",
        "date": "...",
        "numPlayers": 20
    }
    
    Full Response (für Details):
    + disciplines mit vollständiger Stage→Group Struktur
    """
    response = {
        "id": tournament.id,
        "name": tournament.name,
        "description": tournament.description,
        "state": tournament.state,
        "start_time": tournament.start_time.isoformat() if tournament.start_time else None,
        "end_time": tournament.end_time.isoformat() if tournament.end_time else None,
        "courts_count": tournament.courts_count,
        "last_synced": tournament.last_synced_at.isoformat() if tournament.last_synced_at else None
    }
    
    if include_full_structure:
        # Füge vollständige Disciplines-Struktur hinzu
        disciplines = Discipline.query.filter_by(tournament_id=tournament.id).all()
        response["disciplines"] = [
            format_discipline_structure(d) for d in disciplines
        ]
    
    return response


def format_discipline_structure(discipline: Discipline) -> dict:
    """
    Formatiert Discipline mit vollständiger Hierarchie:
    Discipline → Stages → Groups
    """
    from app.models import Group
    
    stages = Stage.query.filter_by(discipline_id=discipline.id).all()
    
    return {
        "id": discipline.id,
        "name": discipline.name,
        "short_name": discipline.short_name,
        "entry_type": discipline.entry_type,
        "stages": [{
            "id": s.id,
            "name": s.name,
            "state": s.state,
            "groups": [{
                "id": g.id,
                "name": g.name,
                "tournament_mode": g.tournament_mode,
                "state": g.state,
                "options": g.options
            } for g in Group.query.filter_by(stage_id=s.id).all()]
        } for s in stages]
    }


@tournaments_bp.route('', methods=['GET'])
def list_tournaments():
    """
    GET /tournaments?limit=25&offset=0&state=running
    
    Gibt Liste aller Turniere zurück
    
    Parameter:
    - limit: int (default: 25) - Max. Anzahl Ergebnisse
    - offset: int (default: 0) - Pagination Offset
    - state: str (optional) - Filtert nach Status
    
    Valid states:
    - planned, pre-registration, check-in, ready, running, finished, cancelled
    """
    limit = request.args.get('limit', 25, type=int)
    offset = request.args.get('offset', 0, type=int)
    state = request.args.get('state', None)
    
    # Begrenze Limit auf sinnvolle Werte
    limit = min(limit, 100)
    
    # Aus lokaler DB oder API
    query = Tournament.query
    
    if state:
        query = query.filter_by(state=state)
    
    tournaments = query.order_by(
        Tournament.start_time.desc()
    ).limit(limit).offset(offset).all()
    
    return jsonify([
        format_tournament_response(t, include_full_structure=False) 
        for t in tournaments
    ]), 200


@tournaments_bp.route('/<tournament_id>', methods=['GET'])
def get_tournament(tournament_id: str):
    """
    GET /tournaments/:id
    
    Gibt vollständige Turnierdaten mit Disciplines→Stages→Groups Struktur zurück
    
    Gemäß API-Doku enthält Response:
    - Tournament Metadaten
    - Disciplines mit EntryType
    - Stages mit State
    - Groups mit tournamentMode, state und options
    """
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        return jsonify({"error": "Turnier nicht gefunden"}), 404
    
    return jsonify(format_tournament_response(tournament, include_full_structure=True)), 200


@tournaments_bp.route('/<tournament_id>/stats', methods=['GET'])
def get_tournament_stats(tournament_id: str):
    """
    GET /tournaments/:id/stats
    
    Gibt Statistiken eines Turniers zurück (Custom Endpoint)
    """
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        return jsonify({"error": "Turnier nicht gefunden"}), 404
    
    stats = {
        "tournament": {
            "id": tournament.id,
            "name": tournament.name,
            "state": tournament.state,
            "courts_count": tournament.courts_count,
            "last_synced": tournament.last_synced_at.isoformat() if tournament.last_synced_at else None
        },
        "counts": {
            "entries": Entry.query.filter_by(tournament_id=tournament_id).count(),
            "disciplines": Discipline.query.filter_by(tournament_id=tournament_id).count(),
            "courts": Court.query.filter_by(tournament_id=tournament_id).count(),
            "total_matches": db.session.query(Match).join(
                'group'
            ).join(
                'stage'
            ).join(
                'discipline'
            ).filter(
                Discipline.tournament_id == tournament_id
            ).count(),
            "finished_matches": db.session.query(Match).join(
                'group'
            ).join(
                'stage'
            ).join(
                'discipline'
            ).filter(
                Discipline.tournament_id == tournament_id,
                Match.state == 'played'
            ).count(),
            "running_matches": db.session.query(Match).join(
                'group'
            ).join(
                'stage'
            ).join(
                'discipline'
            ).filter(
                Discipline.tournament_id == tournament_id,
                Match.state == 'running'
            ).count()
        }
    }
    
    return jsonify(stats), 200


@tournaments_bp.route('/<tournament_id>/entries', methods=['GET'])
def get_entries(tournament_id: str):
    """
    GET /tournaments/:id/entries
    
    Gibt alle Teilnehmer/Entries eines Turniers zurück
    
    Response-Format:
    [
        {"id": "05-9012_05-9876", "name": "Player1 / Player2"},
        ...
    ]
    """
    entries = Entry.query.filter_by(
        tournament_id=tournament_id
    ).order_by(Entry.name).all()
    
    return jsonify([{
        "id": e.id,
        "name": e.name,
        "entry_type": e.entry_type
    } for e in entries]), 200


@tournaments_bp.route('/<tournament_id>/disciplines/<discipline_id>/entries', methods=['GET'])
def get_discipline_entries(tournament_id: str, discipline_id: str):
    """
    GET /tournaments/:id/discipline/:disciplineId/entries
    
    Gibt alle Entries einer spezifischen Disziplin zurück
    """
    # Prüfe ob Discipline zum Tournament gehört
    discipline = Discipline.query.filter_by(
        id=discipline_id,
        tournament_id=tournament_id
    ).first()
    
    if not discipline:
        return jsonify({"error": "Disziplin nicht gefunden"}), 404
    
    # In der aktuellen DB-Struktur sind Entries nicht direkt Disciplines zugeordnet
    # Daher alle Tournament-Entries zurückgeben (API macht das auch so)
    entries = Entry.query.filter_by(
        tournament_id=tournament_id
    ).order_by(Entry.name).all()
    
    return jsonify([{
        "id": e.id,
        "name": e.name
    } for e in entries]), 200


@tournaments_bp.route('/<tournament_id>/disciplines', methods=['GET'])
def get_disciplines(tournament_id: str):
    """
    GET /tournaments/:id/disciplines
    
    Gibt alle Disziplinen eines Turniers zurück (Custom Endpoint)
    """
    disciplines = Discipline.query.filter_by(tournament_id=tournament_id).all()
    
    return jsonify([{
        "id": d.id,
        "name": d.name,
        "short_name": d.short_name,
        "entry_type": d.entry_type,
        "stages_count": Stage.query.filter_by(discipline_id=d.id).count()
    } for d in disciplines]), 200


@tournaments_bp.route('/<tournament_id>/sync', methods=['POST'])
def force_sync(tournament_id: str):
    """
    POST /tournaments/:id/sync
    
    Erzwingt manuellen Sync eines Turniers (Custom Endpoint)
    Nützlich für Testing und manuelles Refresh
    """
    from app.services.sync_service import fetch_tournament_data
    
    success, api_data, error_msg = fetch_tournament_data(tournament_id)
    if not success:
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 500
    
    sync_success, sync_msg = sync_tournament_data(tournament_id, api_data)
    
    if not sync_success:
        return jsonify({
            "status": "error",
            "message": sync_msg
        }), 500
    
    logger.info(f"🔄 Manueller Sync ausgeführt für Tournament {tournament_id}")
    
    return jsonify({
        "status": "ok",
        "message": "Tournament erfolgreich synchronisiert",
        "tournament_id": tournament_id
    }), 200