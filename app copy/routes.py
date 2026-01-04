import os
import requests
import json
import logging
from typing import Tuple, Optional, Dict, Any
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from datetime import datetime
from logging.handlers import RotatingFileHandler

from app.models import (
    db, Tournament, Entry, Discipline, Stage, Group, 
    Standing, Match, Court, WebhookLog
)

api = Blueprint('api', __name__)
API_BASE = "https://api.tournament.io/v1/public/tournaments"

# Logger Setup
def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = RotatingFileHandler(f'logs/{log_file}', maxBytes=5_000_000, backupCount=5)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

sync_logger = setup_logger('sync', 'sync.log')
webhook_logger = setup_logger('webhooks', 'webhooks.log')
error_logger = setup_logger('errors', 'errors.log', logging.ERROR)


def validate_webhook_payload(data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[int]]:
    if not isinstance(data, dict):
        return False, None, None
    payload = data.get('body', data)
    tournament_id = payload.get('tournamentId')
    webhook_id = payload.get('id')
    if not tournament_id:
        error_logger.error(f"Webhook ohne tournamentId: {data}")
        return False, None, None
    return True, tournament_id, webhook_id


def check_webhook_already_processed(webhook_id: Optional[int]) -> bool:
    if webhook_id is None:
        return False
    exists = WebhookLog.query.filter_by(webhook_id=webhook_id).first()
    return exists is not None


def fetch_tournament_data(t_id: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        return False, None, "KICKERTOOL_API_KEY nicht konfiguriert"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        response = requests.get(
            f"{API_BASE}/{t_id}?includeMatches=true&includeStandings=true&includeCourts=true",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 404:
            return False, None, f"Turnier {t_id} nicht gefunden"
        if response.status_code == 403:
            return False, None, "API-Authentifizierung fehlgeschlagen"
        if response.status_code != 200:
            return False, None, f"API-Fehler: HTTP {response.status_code}"
        
        return True, response.json(), None
        
    except requests.Timeout:
        return False, None, "API-Timeout nach 10s"
    except requests.RequestException as e:
        return False, None, f"Request-Fehler: {str(e)}"
    except json.JSONDecodeError:
        return False, None, "Ungültige JSON-Antwort von API"


def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parst ISO-DateTime String zu Python datetime"""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except:
        return None


def sync_tournament_data(t_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
    """Synchronisiert ALLE Turnierdaten in DB"""
    try:
        # 1. TOURNAMENT
        tournament = Tournament(
            id=t_id,
            name=data.get('name', 'Unbekannt'),
            description=data.get('description', ''),
            state=data.get('state', 'unknown'),
            start_time=parse_datetime(data.get('startTime')),
            end_time=parse_datetime(data.get('endTime')),
            courts_count=len(data.get('courts', [])),
            raw_snapshot=data,
            last_synced_at=datetime.utcnow()
        )
        db.session.merge(tournament)
        sync_logger.info(f"Synced Tournament: {t_id} - {tournament.name} ({tournament.state})")
        
        # 2. COURTS
        courts = data.get('courts', [])
        for c in courts:
            if not c.get('id'):
                continue
            court = Court(
                id=c['id'],
                tournament_id=t_id,
                number=c.get('number', 0),
                name=c.get('name', str(c.get('number', ''))),
                current_match_id=c.get('currentMatchId')
            )
            db.session.merge(court)
        sync_logger.info(f"Synced {len(courts)} Courts")
        
        # 3. ENTRIES
        entries = data.get('entries', [])
        for e in entries:
            if not e.get('id'):
                continue
            entry = Entry(
                id=e['id'],
                tournament_id=t_id,
                name=e.get('name', 'N/A')
            )
            db.session.merge(entry)
        sync_logger.info(f"Synced {len(entries)} Entries")
        
        # 4. DISCIPLINES → STAGES → GROUPS → STANDINGS/MATCHES
        disciplines = data.get('disciplines', [])
        for d in disciplines:
            if not d.get('id'):
                continue
            
            discipline = Discipline(
                id=d['id'],
                tournament_id=t_id,
                name=d.get('name', 'N/A'),
                short_name=d.get('shortName'),
                entry_type=d.get('entryType')
            )
            db.session.merge(discipline)
            
            # STAGES
            stages = d.get('stages', [])
            for s in stages:
                if not s.get('id'):
                    continue
                
                stage = Stage(
                    id=s['id'],
                    discipline_id=d['id'],
                    state=s.get('state', 'planned')
                )
                db.session.merge(stage)
                
                # GROUPS
                groups = s.get('groups', [])
                for g in groups:
                    if not g.get('id'):
                        continue
                    
                    group = Group(
                        id=g['id'],
                        stage_id=s['id'],
                        name=g.get('name', 'N/A'),
                        tournament_mode=g.get('tournamentMode'),
                        state=g.get('state', 'planned'),
                        options=g.get('options', {})
                    )
                    db.session.merge(group)
                    
                    # STANDINGS
                    standings = g.get('standings', [])
                    for st in standings:
                        entry_obj = st.get('entry', {})
                        entry_id = entry_obj.get('id')
                        team_name = entry_obj.get('name', 'TBD')
                        
                        standing = Standing(
                            id=f"{g['id']}_{entry_id or team_name}",
                            group_id=g['id'],
                            entry_id=entry_id,
                            rank=st.get('rank', 999),
                            team_name=team_name,
                            points=st.get('points'),
                            matches=st.get('matches'),
                            points_per_match=st.get('pointsPerMatch'),
                            corrected_points_per_match=st.get('correctedPointsPerMatch'),
                            matches_won=st.get('matchesWon'),
                            matches_lost=st.get('matchesLost'),
                            matches_draw=st.get('matchesDraw'),
                            matches_diff=st.get('matchesDiff'),
                            sets_won=st.get('setsWon'),
                            sets_lost=st.get('setsLost'),
                            sets_diff=st.get('setsDiff'),
                            goals=st.get('goals'),
                            goals_in=st.get('goalsIn'),
                            goals_diff=st.get('goalsDiff'),
                            bh1=st.get('bh1'),
                            bh2=st.get('bh2'),
                            sb=st.get('sb'),
                            lives=st.get('lives'),
                            result=st.get('result')
                        )
                        db.session.merge(standing)
                    
                    # MATCHES
                    matches = g.get('matches', [])
                    for m in matches:
                        if not m.get('id'):
                            continue
                        
                        # Extrahiere Team-Daten (kann nested arrays sein für MonsterDYP)
                        entries_data = m.get('entries', [])
                        team1_name = 'TBD'
                        team2_name = 'TBD'
                        team1_entry_id = None
                        team2_entry_id = None
                        
                        if len(entries_data) >= 1 and entries_data[0]:
                            if isinstance(entries_data[0], list):
                                # MonsterDYP: [[{player1}, {player2}], [{player3}, {player4}]]
                                team1_name = ' / '.join([p.get('name', 'TBD') for p in entries_data[0] if p])
                            elif isinstance(entries_data[0], dict):
                                # Normal: [{id, name}, {id, name}]
                                team1_name = entries_data[0].get('name', 'TBD')
                                team1_entry_id = entries_data[0].get('id')
                        
                        if len(entries_data) >= 2 and entries_data[1]:
                            if isinstance(entries_data[1], list):
                                team2_name = ' / '.join([p.get('name', 'TBD') for p in entries_data[1] if p])
                            elif isinstance(entries_data[1], dict):
                                team2_name = entries_data[1].get('name', 'TBD')
                                team2_entry_id = entries_data[1].get('id')
                        
                        # Scores
                        display_score = m.get('displayScore', [])
                        score1 = display_score[0] if len(display_score) >= 1 else None
                        score2 = display_score[1] if len(display_score) >= 2 else None
                        
                        match = Match(
                            id=m['id'],
                            group_id=g['id'],
                            team1_name=team1_name,
                            team2_name=team2_name,
                            team1_entry_id=team1_entry_id,
                            team2_entry_id=team2_entry_id,
                            state=m.get('state', 'unknown'),
                            score1=score1,
                            score2=score2,
                            encounters=m.get('encounters'),
                            display_score=display_score,
                            discipline_id=m.get('disciplineId') or d['id'],
                            discipline_name=m.get('disciplineName') or d.get('name'),
                            round_id=m.get('roundId'),
                            round_name=m.get('roundName'),
                            group_name=m.get('groupName') or g.get('name'),
                            start_time=parse_datetime(m.get('startTime')),
                            end_time=parse_datetime(m.get('endTime')),
                            court_id=None,  # Wird später über Courts aktualisiert
                            is_live_result=m.get('isLiveResult', False)
                        )
                        db.session.merge(match)
        
        sync_logger.info(f"Synced {len(disciplines)} Disciplines with all nested data")
        
        # Commit alles in einer Transaktion
        db.session.commit()
        sync_logger.info(f"✓ Vollständiger Sync für Turnier {t_id} abgeschlossen")
        return True, "Sync erfolgreich"
        
    except IntegrityError as e:
        db.session.rollback()
        error_msg = f"DB Integrity Error: {str(e.orig)}"
        error_logger.error(f"Turnier {t_id}: {error_msg}")
        return False, error_msg
    except SQLAlchemyError as e:
        db.session.rollback()
        error_msg = f"DB Error: {str(e)}"
        error_logger.error(f"Turnier {t_id}: {error_msg}")
        return False, error_msg
    except Exception as e:
        db.session.rollback()
        error_msg = f"Unerwarteter Fehler: {str(e)}"
        error_logger.exception(f"Turnier {t_id}: {error_msg}")
        return False, error_msg


def log_webhook_event(webhook_id: Optional[int], tournament_id: str, event_types: list, success: bool, error_message: Optional[str] = None):
    try:
        if webhook_id is None:
            return
        log_entry = WebhookLog(
            webhook_id=webhook_id,
            tournament_id=tournament_id,
            event_types=event_types,
            success=success,
            error_message=error_message
        )
        db.session.merge(log_entry)
        db.session.commit()
    except Exception as e:
        error_logger.error(f"Fehler beim Webhook-Logging: {e}")
        db.session.rollback()


@api.route('/health', methods=['GET'])
def health_check():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503


@api.route('/webhook/kickertool', methods=['POST'])
def prod_webhook():
    try:
        data = request.get_json(force=True)
    except Exception:
        webhook_logger.error("Ungültiges JSON im Webhook-Request")
        return jsonify({"error": "Invalid JSON"}), 400
    
    is_valid, tournament_id, webhook_id = validate_webhook_payload(data)
    if not is_valid:
        return jsonify({"error": "Invalid webhook payload"}), 400
    
    webhook_logger.info(f"Webhook empfangen: ID={webhook_id}, Tournament={tournament_id}")
    
    if check_webhook_already_processed(webhook_id):
        webhook_logger.info(f"Webhook {webhook_id} bereits verarbeitet (Skip)")
        return jsonify({"status": "skipped", "message": "Webhook bereits verarbeitet"}), 200
    
    payload = data.get('body', data)
    event_types = [e.get('type') for e in payload.get('events', [])]
    
    success, api_data, error_msg = fetch_tournament_data(tournament_id)
    if not success:
        log_webhook_event(webhook_id, tournament_id, event_types, False, error_msg)
        return jsonify({"status": "error", "message": error_msg}), 200
    
    sync_success, sync_msg = sync_tournament_data(tournament_id, api_data)
    log_webhook_event(webhook_id, tournament_id, event_types, sync_success, sync_msg if not sync_success else None)
    
    return jsonify({
        "status": "ok" if sync_success else "error",
        "message": sync_msg,
        "tournament_id": tournament_id,
        "events_processed": len(event_types)
    }), 200


@api.route('/webhook/test', methods=['POST'])
def test_webhook():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400
    
    is_valid, tournament_id, webhook_id = validate_webhook_payload(data)
    if not is_valid:
        return jsonify({"error": "Invalid webhook payload"}), 400
    
    success, api_data, error_msg = fetch_tournament_data(tournament_id)
    if not success:
        webhook_logger.error(f"Test-Webhook Fehler: {error_msg}")
        return jsonify({"error": error_msg}), 200
    
    webhook_logger.info(
        f"=== TEST SNAPSHOT: Tournament {tournament_id} ===\n"
        f"{json.dumps(api_data, indent=2, ensure_ascii=False)}\n"
        f"{'='*60}"
    )
    
    return jsonify({
        "status": "logged",
        "message": "Daten erfolgreich geloggt",
        "tournament_id": tournament_id,
        "log_file": "logs/webhooks.log"
    }), 200


@api.route('/tournaments/<tournament_id>/stats', methods=['GET'])
def get_tournament_stats(tournament_id: str):
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
            "total_matches": db.session.query(Match).join(Group).join(Stage).join(Discipline).filter(
                Discipline.tournament_id == tournament_id
            ).count(),
            "finished_matches": db.session.query(Match).join(Group).join(Stage).join(Discipline).filter(
                Discipline.tournament_id == tournament_id,
                Match.state == 'played'
            ).count()
        }
    }
    
    return jsonify(stats), 200

# Füge diese Endpoints zu routes.py hinzu (am Ende vor dem letzten Return)

@api.route('/tournaments/<tournament_id>', methods=['GET'])
def get_tournament(tournament_id: str):
    """Gibt vollständige Turnierdaten zurück"""
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        return jsonify({"error": "Turnier nicht gefunden"}), 404
    
    return jsonify({
        "id": tournament.id,
        "name": tournament.name,
        "description": tournament.description,
        "state": tournament.state,
        "start_time": tournament.start_time.isoformat() if tournament.start_time else None,
        "end_time": tournament.end_time.isoformat() if tournament.end_time else None,
        "courts_count": tournament.courts_count,
        "last_synced": tournament.last_synced_at.isoformat() if tournament.last_synced_at else None
    }), 200


@api.route('/tournaments/<tournament_id>/courts', methods=['GET'])
def get_courts(tournament_id: str):
    """Gibt alle Tische/Courts zurück"""
    courts = Court.query.filter_by(tournament_id=tournament_id).order_by(Court.number).all()
    
    return jsonify([{
        "id": c.id,
        "number": c.number,
        "name": c.name,
        "current_match_id": c.current_match_id,
        "current_match": {
            "id": m.id,
            "team1_name": m.team1_name,
            "team2_name": m.team2_name,
            "score1": m.score1,
            "score2": m.score2,
            "state": m.state
        } if (m := Match.query.get(c.current_match_id)) else None
    } for c in courts]), 200


@api.route('/tournaments/<tournament_id>/disciplines', methods=['GET'])
def get_disciplines(tournament_id: str):
    """Gibt alle Disziplinen zurück"""
    disciplines = Discipline.query.filter_by(tournament_id=tournament_id).all()
    
    return jsonify([{
        "id": d.id,
        "name": d.name,
        "short_name": d.short_name,
        "entry_type": d.entry_type,
        "stages_count": Stage.query.filter_by(discipline_id=d.id).count()
    } for d in disciplines]), 200


@api.route('/tournaments/<tournament_id>/disciplines/<discipline_id>/groups', methods=['GET'])
def get_discipline_groups(tournament_id: str, discipline_id: str):
    """Gibt alle Gruppen einer Disziplin zurück"""
    groups = db.session.query(Group).join(Stage).filter(
        Stage.discipline_id == discipline_id
    ).all()
    
    return jsonify([{
        "id": g.id,
        "name": g.name,
        "tournament_mode": g.tournament_mode,
        "state": g.state,
        "options": g.options,
        "standings_count": Standing.query.filter_by(group_id=g.id).count(),
        "matches_count": Match.query.filter_by(group_id=g.id).count()
    } for g in groups]), 200


@api.route('/tournaments/<tournament_id>/groups/<group_id>/standings', methods=['GET'])
def get_group_standings(tournament_id: str, group_id: str):
    """Gibt Rangliste einer Gruppe zurück"""
    standings = Standing.query.filter_by(group_id=group_id).order_by(Standing.rank).all()
    
    return jsonify([{
        "rank": s.rank,
        "team_name": s.team_name,
        "entry_id": s.entry_id,
        "points": s.points,
        "matches": s.matches,
        "points_per_match": s.points_per_match,
        "matches_won": s.matches_won,
        "matches_lost": s.matches_lost,
        "matches_draw": s.matches_draw,
        "sets_won": s.sets_won,
        "sets_lost": s.sets_lost,
        "goals": s.goals,
        "goals_in": s.goals_in,
        "goals_diff": s.goals_diff,
        "bh1": s.bh1,
        "sb": s.sb,
        "lives": s.lives
    } for s in standings]), 200


@api.route('/tournaments/<tournament_id>/groups/<group_id>/matches', methods=['GET'])
def get_group_matches(tournament_id: str, group_id: str):
    """Gibt alle Spiele einer Gruppe zurück"""
    state_filter = request.args.get('state')  # Optional: ?state=running
    
    query = Match.query.filter_by(group_id=group_id)
    if state_filter:
        query = query.filter_by(state=state_filter)
    
    matches = query.order_by(Match.start_time.desc()).all()
    
    return jsonify([{
        "id": m.id,
        "team1_name": m.team1_name,
        "team2_name": m.team2_name,
        "score1": m.score1,
        "score2": m.score2,
        "display_score": m.display_score,
        "state": m.state,
        "round_name": m.round_name,
        "start_time": m.start_time.isoformat() if m.start_time else None,
        "end_time": m.end_time.isoformat() if m.end_time else None,
        "court_id": m.court_id,
        "is_live_result": m.is_live_result
    } for m in matches]), 200


@api.route('/tournaments/<tournament_id>/matches/running', methods=['GET'])
def get_running_matches(tournament_id: str):
    """Gibt alle laufenden Spiele zurück"""
    matches = db.session.query(Match).join(Group).join(Stage).join(Discipline).filter(
        Discipline.tournament_id == tournament_id,
        Match.state == 'running'
    ).all()
    
    return jsonify([{
        "id": m.id,
        "team1_name": m.team1_name,
        "team2_name": m.team2_name,
        "score1": m.score1,
        "score2": m.score2,
        "discipline_name": m.discipline_name,
        "round_name": m.round_name,
        "group_name": m.group_name,
        "court_id": m.court_id,
        "start_time": m.start_time.isoformat() if m.start_time else None
    } for m in matches]), 200


@api.route('/tournaments/<tournament_id>/entries', methods=['GET'])
def get_entries(tournament_id: str):
    """Gibt alle Teilnehmer zurück"""
    entries = Entry.query.filter_by(tournament_id=tournament_id).order_by(Entry.name).all()
    
    return jsonify([{
        "id": e.id,
        "name": e.name,
        "entry_type": e.entry_type
    } for e in entries]), 200


@api.route('/tournaments/<tournament_id>/search', methods=['GET'])
def search_tournament(tournament_id: str):
    """Suche nach Teams/Spielern"""
    query = request.args.get('q', '').lower()
    if not query or len(query) < 2:
        return jsonify({"error": "Query muss mindestens 2 Zeichen haben"}), 400
    
    # Suche in Entries
    entries = Entry.query.filter(
        Entry.tournament_id == tournament_id,
        Entry.name.ilike(f'%{query}%')
    ).limit(20).all()
    
    # Suche in Standings
    standings = db.session.query(Standing).join(Group).join(Stage).join(Discipline).filter(
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