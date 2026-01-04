"""
Webhook-Service für Event-Verarbeitung
⚠️ IDEMPOTENZ VORÜBERGEHEND DEAKTIVIERT
Verantwortlich für: Webhook-Validierung, Logging (ohne Duplicate-Check)
"""
import logging
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

from app.models import db, WebhookLog

webhook_logger = logging.getLogger('webhooks')
error_logger = logging.getLogger('errors')


class WebhookEventType(str, Enum):
    """Alle Event-Typen aus API-Dokumentation"""
    TOURNAMENT_ADDED = "TournamentAdded"
    TOURNAMENT_UPDATED = "TournamentUpdated"
    MATCH_UPDATED = "MatchUpdated"
    COURT_MATCH_CHANGED = "CourtMatchChanged"
    ENTRY_LIST_UPDATED = "EntryListUpdated"
    STANDINGS_UPDATED = "StandingsUpdated"


def validate_webhook_payload(data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[int], Optional[Dict]]:
    """
    Validiert eingehende Webhook-Payloads gemäß API-Spec
    
    Returns: (is_valid, tournament_id, webhook_id, payload)
    """
    if not isinstance(data, dict):
        error_logger.error(f"Webhook Payload ist kein Dict: {type(data)}")
        return False, None, None, None
    
    # Payload kann direkt oder unter 'body' sein
    payload = data.get('body', data)
    
    if not isinstance(payload, dict):
        error_logger.error(f"Webhook Body ist kein Dict: {type(payload)}")
        return False, None, None, None
    
    tournament_id = payload.get('tournamentId')
    webhook_id = payload.get('id')
    
    if not tournament_id:
        error_logger.error(f"Webhook ohne tournamentId: {data}")
        return False, None, None, None
    
    # Events validieren
    events = payload.get('events', [])
    if not isinstance(events, list):
        webhook_logger.warning(f"Events ist keine Liste: {type(events)}")
    
    return True, tournament_id, webhook_id, payload


def check_webhook_already_processed(webhook_id: Optional[int]) -> bool:
    """
    ⚠️ IDEMPOTENZ DEAKTIVIERT
    Diese Funktion gibt jetzt immer False zurück
    """
    webhook_logger.warning("⚠️ IDEMPOTENZ DEAKTIVIERT - Webhook wird NICHT auf Duplikate geprüft!")
    return False  # ✅ Webhooks werden IMMER verarbeitet


def log_webhook_event(
    webhook_id: Optional[int], 
    tournament_id: str, 
    event_types: List[str], 
    success: bool, 
    error_message: Optional[str] = None
):
    """
    Persistiert Webhook-Verarbeitung für Audit Trail
    ⚠️ KEINE DUPLICATE-PREVENTION mehr!
    """
    try:
        if webhook_id is None:
            webhook_logger.warning(f"Webhook ohne ID für Tournament {tournament_id} - kann nicht geloggt werden")
            return
        
        # ✅ Erstellt immer neuen Log-Eintrag (keine UNIQUE constraint mehr)
        log_entry = WebhookLog(
            webhook_id=webhook_id,
            tournament_id=tournament_id,
            event_types=event_types,
            success=success,
            error_message=error_message
        )
        db.session.add(log_entry)  # ✅ add() statt merge()
        db.session.commit()
        
        webhook_logger.info(f"📝 Webhook #{webhook_id} geloggt (Duplikate erlaubt)")
        
    except Exception as e:
        error_logger.error(f"Fehler beim Webhook-Logging: {e}")
        db.session.rollback()


def extract_event_types(payload: Dict[str, Any]) -> List[str]:
    """Extrahiert Event-Typen aus Webhook-Payload"""
    events = payload.get('events', [])
    return [e.get('type') for e in events if isinstance(e, dict) and e.get('type')]


def parse_webhook_events(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parst und validiert alle Events in der Payload
    
    Returns: Liste von Event-Dicts mit type, timestamp und optionalen IDs
    """
    events = payload.get('events', [])
    parsed_events = []
    
    for event in events:
        if not isinstance(event, dict):
            continue
        
        event_type = event.get('type')
        if not event_type:
            continue
        
        parsed_event = {
            'type': event_type,
            'created_at': event.get('createdAt')
        }
        
        # Füge typ-spezifische Felder hinzu
        if event_type == WebhookEventType.COURT_MATCH_CHANGED:
            parsed_event['court_id'] = event.get('courtId')
            parsed_event['match_id'] = event.get('matchId')
        
        elif event_type == WebhookEventType.MATCH_UPDATED:
            parsed_event['match_id'] = event.get('matchId')
        
        parsed_events.append(parsed_event)
    
    return parsed_events


def should_trigger_full_sync(events: List[Dict[str, Any]]) -> bool:
    """
    Entscheidet ob ein Full-Sync notwendig ist basierend auf Event-Typen
    
    Full-Sync bei:
    - TournamentAdded
    - TournamentUpdated
    - EntryListUpdated
    - StandingsUpdated
    
    Partial-Sync möglich bei:
    - MatchUpdated
    - CourtMatchChanged
    """
    full_sync_types = {
        WebhookEventType.TOURNAMENT_ADDED,
        WebhookEventType.TOURNAMENT_UPDATED,
        WebhookEventType.ENTRY_LIST_UPDATED,
        WebhookEventType.STANDINGS_UPDATED
    }
    
    for event in events:
        if event.get('type') in full_sync_types:
            return True
    
    return False


def get_affected_resource_ids(events: List[Dict[str, Any]]) -> Dict[str, set]:
    """
    Extrahiert betroffene Ressourcen-IDs aus Events
    
    Returns: {
        'matches': {'match_id1', 'match_id2', ...},
        'courts': {'court_id1', 'court_id2', ...}
    }
    """
    affected = {
        'matches': set(),
        'courts': set()
    }
    
    for event in events:
        event_type = event.get('type')
        
        if event_type == WebhookEventType.MATCH_UPDATED:
            match_id = event.get('match_id')
            if match_id:
                affected['matches'].add(match_id)
        
        elif event_type == WebhookEventType.COURT_MATCH_CHANGED:
            court_id = event.get('court_id')
            match_id = event.get('match_id')
            if court_id:
                affected['courts'].add(court_id)
            if match_id:
                affected['matches'].add(match_id)
    
    return affected


def log_event_summary(webhook_id: int, tournament_id: str, events: List[Dict[str, Any]]):
    """Loggt übersichtliche Zusammenfassung der empfangenen Events"""
    event_counts = {}
    for event in events:
        event_type = event.get('type', 'Unknown')
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
    
    summary_parts = [f"{count}x {etype}" for etype, count in event_counts.items()]
    summary = ", ".join(summary_parts)
    
    webhook_logger.info(
        f"📨 Webhook #{webhook_id} | Tournament: {tournament_id} | "
        f"Events: {len(events)} ({summary})"
    )