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