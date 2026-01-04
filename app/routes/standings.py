"""
Standings-Endpoints
Implementiert Ranglisten gemäß API-Dokumentation mit allen Feldern
"""
from flask import Blueprint, jsonify
from app.models import Standing
from app.services.sync_service import fetch_group_standings

standings_bp = Blueprint('standings', __name__)


def format_standing_response(standing: Standing) -> dict:
    """
    Formatiert Standing-Objekt gemäß API-Spec
    
    Gemäß API-Doku: Jedes Standing enthält immer id und entry,
    alle anderen Felder nur wenn in der Standings-Tabelle konfiguriert.
    
    Mögliche Felder (aus API-Doku):
    - matches, points, pointsPerMatch, correctedPointsPerMatch
    - matchesWon, matchesLost, matchesDraw, matchesDiff
    - setsWon, setsLost, setsDiff
    - encounterWon, encounterLost, encounterDraw, encounterDiff
    - goals, goalsIn, goalsDiff
    - bh1, bh2, sb (Tiebreaker)
    - lives (Last One Standing)
    - rank, result, prelimResult, lastRound, firstRound, finalResult
    """
    response = {
        "id": standing.id,
        "entry": {
            "id": standing.entry_id,
            "name": standing.team_name
        }
    }
    
    # Nur Felder hinzufügen die nicht None sind
    # Dies entspricht dem Verhalten der API: Nur konfigurierte Felder werden gesendet
    
    if standing.rank is not None:
        response["rank"] = standing.rank
    
    if standing.matches is not None:
        response["matches"] = standing.matches
    
    if standing.points is not None:
        response["points"] = standing.points
    
    if standing.points_per_match is not None:
        response["points_per_match"] = standing.points_per_match
    
    if standing.corrected_points_per_match is not None:
        response["corrected_points_per_match"] = standing.corrected_points_per_match
        response["has_corrected_value"] = True
    
    # Matches-Statistiken
    if standing.matches_won is not None:
        response["matches_won"] = standing.matches_won
    
    if standing.matches_lost is not None:
        response["matches_lost"] = standing.matches_lost
    
    if standing.matches_draw is not None:
        response["matches_draw"] = standing.matches_draw
    
    if standing.matches_diff is not None:
        response["matches_diff"] = standing.matches_diff
    
    # Sets-Statistiken
    if standing.sets_won is not None:
        response["sets_won"] = standing.sets_won
    
    if standing.sets_lost is not None:
        response["sets_lost"] = standing.sets_lost
    
    if standing.sets_diff is not None:
        response["sets_diff"] = standing.sets_diff
    
    # Goals-Statistiken
    if standing.goals is not None:
        response["goals"] = standing.goals
    
    if standing.goals_in is not None:
        response["goals_in"] = standing.goals_in
    
    if standing.goals_diff is not None:
        response["goals_diff"] = standing.goals_diff
    
    # Tiebreaker (Buchholz, Sonneborn-Berger)
    if standing.bh1 is not None:
        response["bh1"] = standing.bh1
    
    if standing.bh2 is not None:
        response["bh2"] = standing.bh2
    
    if standing.sb is not None:
        response["sb"] = standing.sb
    
    # MonsterDYP / Last One Standing spezifisch
    if standing.lives is not None:
        response["lives"] = standing.lives
    
    if standing.result is not None:
        response["result"] = standing.result
    
    return response


@standings_bp.route('/tournaments/<tournament_id>/groups/<group_id>/standings', methods=['GET'])
def get_group_standings(tournament_id: str, group_id: str):
    """
    GET /tournaments/:id/groups/:groupId/standings
    
    Gibt Rangliste einer Gruppe zurück, sortiert nach Rank
    
    Response-Struktur gemäß API-Doku:
    [
        {
            "id": "...",
            "entry": {"id": "...", "name": "..."},
            "rank": 1,
            "points": 4,
            "matches": 2,
            "bh1": 0.75,
            ... (nur konfigurierte Felder)
        },
        ...
    ]
    
    Hinweis: Die Felder variieren je nach Tournament-Mode:
    - Swiss: bh1, bh2, sb
    - Round Robin: matches, points, goals
    - MonsterDYP: lives, correctedPointsPerMatch
    - Last One Standing: lives, result
    """
    standings = Standing.query.filter_by(
        group_id=group_id
    ).order_by(Standing.rank).all()
    
    if not standings:
        # Leere Liste wenn keine Standings vorhanden
        # (z.B. bei gerade gestarteten Turnieren)
        return jsonify([]), 200
    
    return jsonify([format_standing_response(s) for s in standings]), 200


@standings_bp.route('/tournaments/<tournament_id>/disciplines/<discipline_id>/standings', methods=['GET'])
def get_discipline_standings(tournament_id: str, discipline_id: str):
    """
    GET /tournaments/:id/disciplines/:disciplineId/standings
    
    Gibt aggregierte Standings für alle Gruppen einer Disziplin zurück
    (Custom Endpoint - nicht in offizieller API)
    """
    from app.models import Group, Stage
    
    # Hole alle Groups dieser Discipline
    groups = db.session.query(Group).join(Stage).filter(
        Stage.discipline_id == discipline_id
    ).all()
    
    group_ids = [g.id for g in groups]
    
    # Hole alle Standings dieser Groups
    standings = Standing.query.filter(
        Standing.group_id.in_(group_ids)
    ).order_by(Standing.rank).all()
    
    # Gruppiere nach Group
    result = {}
    for standing in standings:
        group_id = standing.group_id
        if group_id not in result:
            result[group_id] = {
                "group_id": group_id,
                "group_name": next((g.name for g in groups if g.id == group_id), None),
                "standings": []
            }
        result[group_id]["standings"].append(format_standing_response(standing))
    
    return jsonify(list(result.values())), 200