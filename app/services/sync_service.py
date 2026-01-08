"""
🔧 COURTS DEBUG FIX - Komplette Analyse und Fix des Court-Problems

Problem identifiziert:
- API liefert keine Courts im Tournament-Response
- Courts müssen separat über /courts endpoint geladen werden
"""
import os
import requests
import json
import logging
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.models import (
    db, Tournament, Entry, Discipline, Stage, Group, 
    Standing, Match, Court
)

sync_logger = logging.getLogger('sync')
error_logger = logging.getLogger('errors')

API_BASE = "https://api.tournament.io/v1/public/tournaments"


def fetch_tournament_data(
    t_id: str,
    include_matches: bool = True,
    include_standings: bool = True,
    include_courts: bool = True
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """Holt Turnierdaten von der Kickertool API"""
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        return False, None, "KICKERTOOL_API_KEY nicht konfiguriert"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    params = {
        "includeMatches": "true" if include_matches else "false",
        "includeStandings": "true" if include_standings else "false",
        "includeCourts": "true" if include_courts else "false"
    }
    
    try:
        sync_logger.info(f"🌐 API-Call: GET {API_BASE}/{t_id} mit params: {params}")
        response = requests.get(
            f"{API_BASE}/{t_id}", 
            headers=headers, 
            params=params,
            timeout=10
        )
        
        sync_logger.info(f"📡 API Response Status: {response.status_code}")
        
        if response.status_code == 404:
            return False, None, f"Turnier {t_id} nicht gefunden"
        if response.status_code == 403:
            return False, None, "API-Authentifizierung fehlgeschlagen"
        if response.status_code != 200:
            return False, None, f"API-Fehler: HTTP {response.status_code}"
        
        data = response.json()
        
        # 🔍 DEBUG: Speichere und analysiere Response
        try:
            os.makedirs('logs/api_responses', exist_ok=True)
            filename = f'logs/api_responses/tournament_{t_id}.json'
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            sync_logger.info(f"📄 API response saved to {filename}")
            
            # ✅ DEBUG: Prüfe ob Courts im Response sind
            courts_in_response = data.get('courts', [])
            sync_logger.info(f"🔍 DEBUG: Courts in Tournament-Response: {len(courts_in_response)}")
            
            if not courts_in_response:
                sync_logger.warning("⚠️ KEIN 'courts' Array in Tournament-Response!")
                sync_logger.warning("   → Courts müssen separat über /courts endpoint geladen werden")
            else:
                sync_logger.info(f"✅ {len(courts_in_response)} Courts in Response gefunden")
                
        except Exception as e:
            sync_logger.warning(f"Could not save/analyze API response: {e}")
        
        return True, data, None
        
    except requests.Timeout:
        return False, None, "API-Timeout nach 10s"
    except requests.RequestException as e:
        return False, None, f"Request-Fehler: {str(e)}"
    except json.JSONDecodeError:
        return False, None, "Ungültige JSON-Antwort von API"


def fetch_courts(t_id: str, include_match_details: bool = False) -> Tuple[bool, Optional[List], Optional[str]]:
    """
    ✅ FIX: Holt Courts über separaten Endpoint
    WICHTIG: Dies ist der einzige Weg Courts zu laden!
    """
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        return False, None, "KICKERTOOL_API_KEY nicht konfiguriert"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"includeMatchDetails": "true"} if include_match_details else {}
    
    try:
        url = f"{API_BASE}/{t_id}/courts"
        sync_logger.info(f"🌐 API-Call: GET {url}")
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        sync_logger.info(f"📡 Courts Response Status: {response.status_code}")
        
        if response.status_code != 200:
            return False, None, f"API-Fehler: HTTP {response.status_code}"
        
        courts_data = response.json()
        sync_logger.info(f"✅ Courts API returned: {len(courts_data)} courts")
        
        # 🔍 DEBUG: Zeige Court-Details
        if courts_data:
            for c in courts_data[:3]:  # Zeige erste 3
                sync_logger.debug(f"  📌 Court: {c}")
        
        return True, courts_data, None
        
    except Exception as e:
        error_logger.exception(f"Fehler beim Courts-Abruf: {e}")
        return False, None, f"Fehler: {str(e)}"


def sync_tournament_data(t_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    ✅ FIXED: Synchronisiert ALLE Turnierdaten
    Courts werden jetzt über separaten API-Call geladen!
    """
    
    sync_logger.info(f"\n{'='*80}")
    sync_logger.info(f"🔄 STARTE SYNC FÜR TOURNAMENT: {t_id}")
    sync_logger.info(f"{'='*80}")
    
    try:
        # STEP 1: TOURNAMENT
        sync_logger.info("\n🔹 STEP 1: Tournament-Daten")
        
        # ✅ FIX: Lade Courts SEPARAT
        sync_logger.info("  📞 Lade Courts über separaten API-Call...")
        courts_success, courts_api_data, courts_error = fetch_courts(t_id, include_match_details=False)
        
        actual_courts_count = 0
        if courts_success and courts_api_data:
            actual_courts_count = len(courts_api_data)
            sync_logger.info(f"  ✅ {actual_courts_count} Courts von API erhalten")
        else:
            sync_logger.warning(f"  ⚠️ Konnte Courts nicht laden: {courts_error}")
            courts_api_data = []
        
        tournament = Tournament(
            id=t_id,
            name=data.get('name', 'Unbekannt'),
            description=data.get('description', ''),
            state=data.get('state', 'unknown'),
            start_time=parse_datetime(data.get('startTime')),
            end_time=parse_datetime(data.get('endTime')),
            courts_count=actual_courts_count,  # ✅ Korrekte Anzahl
            raw_snapshot=data,
            last_synced_at=datetime.utcnow()
        )
        db.session.merge(tournament)
        db.session.flush()
        
        sync_logger.info(f"✅ Tournament: {tournament.name} ({tournament.state})")
        sync_logger.info(f"   → Courts Count: {actual_courts_count}")
        
        # ✅ STEP 2: COURTS - Mit API-Daten vom separaten Endpoint
        sync_logger.info("\n🔹 STEP 2: Courts")
        
        court_match_mapping = {}
        courts_saved = 0
        
        if courts_api_data:
            sync_logger.info(f"💾 Speichere {len(courts_api_data)} Courts in DB...")
            
            for c in courts_api_data:
                if not c.get('id'):
                    sync_logger.warning(f"⚠️ Court ohne ID übersprungen: {c}")
                    continue
                
                sync_logger.debug(f"  📌 Court {c.get('number')}: ID={c.get('id')}, Name={c.get('name')}")
                
                court = Court(
                    id=c['id'],
                    tournament_id=t_id,
                    number=c.get('number', 0),
                    name=c.get('name', str(c.get('number', ''))),
                    current_match_id=c.get('currentMatchId')
                )
                db.session.merge(court)
                courts_saved += 1
                
                # Match-Court-Mapping
                if c.get('currentMatchId'):
                    court_match_mapping[c['currentMatchId']] = c['id']
                    sync_logger.debug(f"    → Match: {c['currentMatchId']}")
            
            db.session.flush()
            sync_logger.info(f"✅ Courts: {courts_saved} gespeichert")
            
            if court_match_mapping:
                sync_logger.info(f"📌 Court-Match-Mappings: {len(court_match_mapping)}")
        else:
            sync_logger.warning("⚠️ Keine Courts zum Speichern")
            sync_logger.info("   → Mögliche Ursachen:")
            sync_logger.info("      1. Tournament hat keine Courts konfiguriert")
            sync_logger.info("      2. API-Endpoint liefert keine Daten")
            sync_logger.info("      3. Tournament ist noch nicht gestartet")
        
        # STEP 3: DISCIPLINES → STAGES → GROUPS
        sync_logger.info("\n🔹 STEP 3: Disciplines, Stages, Groups")
        
        disciplines = data.get('disciplines', [])
        sync_logger.info(f"📥 {len(disciplines)} Disciplines in API-Response")
        
        disciplines_saved = 0
        stages_saved = 0
        groups_saved = 0
        
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
            disciplines_saved += 1
            
            stages = d.get('stages', [])
            for s in stages:
                if not s.get('id'):
                    continue
                
                stage = Stage(
                    id=s['id'],
                    discipline_id=d['id'],
                    name=s.get('name'),
                    state=s.get('state', 'planned')
                )
                db.session.merge(stage)
                stages_saved += 1
                
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
                    groups_saved += 1
        
        db.session.flush()
        
        sync_logger.info(f"✅ Disciplines: {disciplines_saved}")
        sync_logger.info(f"✅ Stages: {stages_saved}")
        sync_logger.info(f"✅ Groups: {groups_saved}")
        
        # STEP 4: ENTRIES (Tournament + Discipline-spezifisch)
        sync_logger.info("\n🔹 STEP 4: Entries")
        
        # Tournament-Entries
        entries_success, entries_data, entries_error = fetch_tournament_entries(t_id)
        entries_saved = 0
        
        if entries_success and entries_data:
            sync_logger.info(f"📥 {len(entries_data)} Tournament-Entries geladen")
            
            for e in entries_data:
                if not e.get('id'):
                    continue
                
                entry = Entry(
                    id=e['id'],
                    tournament_id=t_id,
                    name=e.get('name', 'N/A'),
                    entry_type=e.get('type')
                )
                db.session.merge(entry)
                entries_saved += 1
            
            db.session.flush()
            sync_logger.info(f"✅ Entries: {entries_saved} gespeichert")
        else:
            sync_logger.error(f"❌ Entries-Abruf fehlgeschlagen: {entries_error}")
        
        # STEP 5: STANDINGS
        sync_logger.info("\n🔹 STEP 5: Standings")
        
        total_standings = 0
        
        for d in disciplines:
            stages = d.get('stages', [])
            for s in stages:
                groups = s.get('groups', [])
                for g in groups:
                    group_id = g['id']
                    
                    standings_success, standings_data, standings_error = fetch_group_standings(t_id, group_id)
                    
                    if standings_success and standings_data:
                        for st in standings_data:
                            entry_obj = st.get('entry', {})
                            entry_id = entry_obj.get('id') if entry_obj else None
                            team_name = entry_obj.get('name', 'TBD') if entry_obj else 'TBD'
                            
                            standing_id = f"{group_id}_{entry_id if entry_id else team_name.replace(' ', '_')}"
                            
                            standing = Standing(
                                id=standing_id,
                                group_id=group_id,
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
                            total_standings += 1
        
        db.session.flush()
        sync_logger.info(f"✅ Standings: {total_standings}")
        
        # FINAL COMMIT
        sync_logger.info("\n🔹 FINAL: Commit to Database")
        db.session.commit()
        sync_logger.info("✅ Transaction committed")
        
        # VERIFICATION
        sync_logger.info("\n🔹 VERIFICATION: Prüfe gespeicherte Daten")
        
        verify_results = {
            "entries": Entry.query.filter_by(tournament_id=t_id).count(),
            "courts": Court.query.filter_by(tournament_id=t_id).count(),
            "standings": Standing.query.join(Group).join(Stage).join(Discipline).filter(
                Discipline.tournament_id == t_id
            ).count()
        }
        
        sync_logger.info(f"📊 In DB gespeichert:")
        sync_logger.info(f"  - Entries: {verify_results['entries']}")
        sync_logger.info(f"  - Courts: {verify_results['courts']}")
        sync_logger.info(f"  - Standings: {verify_results['standings']}")
        
        # Validierung
        if verify_results['courts'] != courts_saved:
            sync_logger.error(f"❌ COURTS MISMATCH: Erwartet {courts_saved}, gefunden {verify_results['courts']}")
        
        if verify_results['courts'] == 0 and actual_courts_count > 0:
            sync_logger.error("❌ KRITISCHER FEHLER: Courts wurden nicht gespeichert!")
            sync_logger.error("   → API lieferte Courts, aber DB ist leer")
            sync_logger.error("   → Mögliche Ursache: DB-Constraint-Fehler")
        
        sync_logger.info(f"\n{'='*80}")
        sync_logger.info(f"✅ SYNC ERFOLGREICH ABGESCHLOSSEN FÜR {t_id}")
        sync_logger.info(f"{'='*80}\n")
        
        return True, "Sync erfolgreich"
        
    except IntegrityError as e:
        db.session.rollback()
        error_msg = f"DB Integrity Error: {str(e.orig)}"
        error_logger.exception(f"Turnier {t_id}: {error_msg}")
        sync_logger.error(f"❌ ROLLBACK: {error_msg}")
        return False, error_msg
    
    except SQLAlchemyError as e:
        db.session.rollback()
        error_msg = f"DB Error: {str(e)}"
        error_logger.exception(f"Turnier {t_id}: {error_msg}")
        sync_logger.error(f"❌ ROLLBACK: {error_msg}")
        return False, error_msg
    
    except Exception as e:
        db.session.rollback()
        error_msg = f"Unerwarteter Fehler: {str(e)}"
        error_logger.exception(f"Turnier {t_id}: {error_msg}")
        sync_logger.error(f"❌ ROLLBACK: {error_msg}")
        return False, error_msg


# Hilfsfunktionen (bleiben unverändert)
def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parst ISO-DateTime String zu Python datetime"""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except:
        return None


def fetch_tournament_entries(t_id: str, discipline_id: Optional[str] = None) -> Tuple[bool, Optional[List], Optional[str]]:
    """Holt Entries für Tournament oder Discipline"""
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        return False, None, "KICKERTOOL_API_KEY nicht konfiguriert"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    if discipline_id:
        url = f"{API_BASE}/{t_id}/discipline/{discipline_id}/entries"
    else:
        url = f"{API_BASE}/{t_id}/entries"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return False, None, f"API-Fehler: HTTP {response.status_code}"
        
        entries = response.json()
        return True, entries, None
    except Exception as e:
        return False, None, f"Fehler: {str(e)}"


def fetch_group_standings(t_id: str, group_id: str) -> Tuple[bool, Optional[List], Optional[str]]:
    """Holt Standings für eine Gruppe"""
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        return False, None, "KICKERTOOL_API_KEY nicht konfiguriert"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        response = requests.get(f"{API_BASE}/{t_id}/groups/{group_id}/standings", headers=headers, timeout=10)
        if response.status_code != 200:
            return False, None, f"API-Fehler: HTTP {response.status_code}"
        return True, response.json(), None
    except Exception as e:
        return False, None, f"Fehler: {str(e)}"


def sync_match_to_db(t_id: str, match_data: Dict[str, Any]):
    """Speichert Match mit Court-Zuordnung"""
    try:
        if not match_data.get('id'):
            return
        
        match_id = match_data['id']
        group_id = match_data.get('groupId')
        
        if group_id:
            from app.models import Group
            group_exists = Group.query.get(group_id)
            if not group_exists:
                sync_logger.warning(
                    f"⚠️ Match {match_id}: Group {group_id} existiert nicht in DB"
                )
                return
        
        # Team-Namen extrahieren
        entries_data = match_data.get('entries', [])
        team1_name = 'TBD'
        team2_name = 'TBD'
        team1_entry_id = None
        team2_entry_id = None
        
        if len(entries_data) >= 1 and entries_data[0]:
            if isinstance(entries_data[0], dict):
                team1_name = entries_data[0].get('name', 'TBD')
                team1_entry_id = entries_data[0].get('id')
            elif isinstance(entries_data[0], list):
                names = [p.get('name', 'TBD') for p in entries_data[0] if p]
                team1_name = ' / '.join(names)
        
        if len(entries_data) >= 2 and entries_data[1]:
            if isinstance(entries_data[1], dict):
                team2_name = entries_data[1].get('name', 'TBD')
                team2_entry_id = entries_data[1].get('id')
            elif isinstance(entries_data[1], list):
                names = [p.get('name', 'TBD') for p in entries_data[1] if p]
                team2_name = ' / '.join(names)
        
        display_score = match_data.get('displayScore', [])
        score1 = display_score[0] if len(display_score) >= 1 else None
        score2 = display_score[1] if len(display_score) >= 2 else None
        
        # Court-Zuordnung
        court_id = None
        if match_id:
            court = Court.query.filter_by(current_match_id=match_id).first()
            if court:
                court_id = court.id
        
        match = Match(
            id=match_id,
            group_id=group_id,
            team1_name=team1_name,
            team2_name=team2_name,
            team1_entry_id=team1_entry_id,
            team2_entry_id=team2_entry_id,
            state=match_data.get('state', 'unknown'),
            score1=score1,
            score2=score2,
            encounters=match_data.get('encounters'),
            display_score=display_score,
            discipline_id=match_data.get('disciplineId'),
            discipline_name=match_data.get('disciplineName'),
            round_id=match_data.get('roundId'),
            round_name=match_data.get('roundName'),
            group_name=match_data.get('groupName'),
            start_time=parse_datetime(match_data.get('startTime')),
            end_time=parse_datetime(match_data.get('endTime')),
            court_id=court_id,
            is_live_result=match_data.get('isLiveResult', False)
        )
        db.session.merge(match)
        db.session.commit()
        
        sync_logger.info(f"✅ Match {match_id} gespeichert")
        
    except Exception as e:
        db.session.rollback()
        error_logger.exception(f"Fehler beim Match-Sync: {e}")


def fetch_single_match(t_id: str, match_id: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """Holt einzelnes Match"""
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        return False, None, "KICKERTOOL_API_KEY nicht konfiguriert"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        response = requests.get(f"{API_BASE}/{t_id}/matches/{match_id}", headers=headers, timeout=10)
        if response.status_code != 200:
            return False, None, f"API-Fehler: HTTP {response.status_code}"
        
        match_data = response.json()
        sync_match_to_db(t_id, match_data)
        
        return True, match_data, None
    except Exception as e:
        return False, None, f"Fehler: {str(e)}"


def fetch_tournaments_list(limit: int = 25, offset: int = 0, state: Optional[str] = None) -> Tuple[bool, Optional[List[Dict]], Optional[str]]:
    """Holt Liste aller Turniere"""
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        return False, None, "KICKERTOOL_API_KEY nicht konfiguriert"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"limit": limit, "offset": offset}
    if state:
        params["state"] = state
    
    try:
        response = requests.get(API_BASE, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return False, None, f"API-Fehler: HTTP {response.status_code}"
        return True, response.json(), None
    except Exception as e:
        return False, None, f"Fehler: {str(e)}"


def update_match_result(t_id: str, match_id: str, result: List) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """Setzt Match-Ergebnis"""
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        return False, None, "KICKERTOOL_API_KEY nicht konfiguriert"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.put(
            f"{API_BASE}/{t_id}/matches/{match_id}/result",
            headers=headers,
            json={"result": result},
            timeout=10
        )
        
        if response.status_code == 412:
            return False, None, "Match ist nicht im Status 'running'"
        if response.status_code != 200:
            return False, None, f"API-Fehler: HTTP {response.status_code}"
        
        return True, response.json(), None
    except Exception as e:
        return False, None, f"Fehler: {str(e)}"


def update_match_live_result(t_id: str, match_id: str, result: List) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """Setzt Live-Score ohne Match zu beenden"""
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        return False, None, "KICKERTOOL_API_KEY nicht konfiguriert"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.put(
            f"{API_BASE}/{t_id}/matches/{match_id}/live-result",
            headers=headers,
            json={"result": result},
            timeout=10
        )
        
        if response.status_code == 412:
            return False, None, "Match ist nicht im Status 'running'"
        if response.status_code != 200:
            return False, None, f"API-Fehler: HTTP {response.status_code}"
        
        return True, response.json(), None
    except Exception as e:
        return False, None, f"Fehler: {str(e)}"