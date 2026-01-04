"""
Webhook-Endpoints - AUTO-SYNC VERSION
✅ Führt automatisch Full-Sync aus wenn Tournament-Daten fehlen
"""
import json
import logging
from flask import Blueprint, request, jsonify
from datetime import datetime

from app.services.webhook_service import (
    validate_webhook_payload,
    log_webhook_event,
    parse_webhook_events,
    should_trigger_full_sync,
    log_event_summary
)
from app.services.sync_service import (
    fetch_tournament_data,
    sync_tournament_data,
    fetch_single_match,
    fetch_courts,
    sync_match_to_db
)
from app.models import db, Court, Tournament

webhook_bp = Blueprint('webhooks', __name__, url_prefix='/webhook')
webhook_logger = logging.getLogger('webhooks')


def check_tournament_synced(tournament_id: str) -> bool:
    """Prüft ob Tournament bereits in DB existiert"""
    tournament = Tournament.query.get(tournament_id)
    return tournament is not None


@webhook_bp.route('/kickertool', methods=['POST'])
def prod_webhook():
    """
    Produktions-Webhook Endpoint
    ✅ Führt automatisch Full-Sync aus wenn Tournament nicht existiert
    """
    try:
        data = request.get_json(force=True)
    except Exception as e:
        webhook_logger.error(f"❌ Ungültiges JSON im Webhook-Request: {e}")
        return jsonify({"error": "Invalid JSON"}), 400
    
    # 1. VALIDIERUNG
    is_valid, tournament_id, webhook_id, payload = validate_webhook_payload(data)
    if not is_valid:
        return jsonify({"error": "Invalid webhook payload"}), 400
    
    # 2. EVENT-PARSING
    events = parse_webhook_events(payload)
    event_types = [e['type'] for e in events]
    
    log_event_summary(webhook_id, tournament_id, events)
    
    # 🔧 Versuche Webhook zu loggen (ignoriere Duplikat-Fehler)
    try:
        log_webhook_event(webhook_id, tournament_id, event_types, True, None)
    except Exception as log_error:
        webhook_logger.warning(f"⚠️ Webhook-Logging fehlgeschlagen (wird ignoriert): {log_error}")
    
    # ✅ WICHTIG: Prüfe ob Tournament existiert
    is_synced = check_tournament_synced(tournament_id)
    
    if not is_synced:
        webhook_logger.warning(
            f"⚠️  Tournament {tournament_id} nicht in DB gefunden. "
            f"Führe automatischen Initial-Sync aus..."
        )
        
        # Automatischer Initial-Sync
        success, api_data, error_msg = fetch_tournament_data(tournament_id)
        if success:
            sync_success, sync_msg = sync_tournament_data(tournament_id, api_data)
            if sync_success:
                webhook_logger.info(f"✅ Initial-Sync erfolgreich für {tournament_id}")
            else:
                webhook_logger.error(f"❌ Initial-Sync fehlgeschlagen: {sync_msg}")
        else:
            webhook_logger.error(f"❌ Konnte Tournament nicht laden: {error_msg}")
    
    # 3. SYNC-STRATEGIE BESTIMMEN
    needs_full_sync = should_trigger_full_sync(events)
    
    if needs_full_sync:
        webhook_logger.info(f"🔄 Full-Sync wird ausgeführt für {tournament_id}")
        
        success, api_data, error_msg = fetch_tournament_data(tournament_id)
        if not success:
            log_webhook_event(webhook_id, tournament_id, event_types, False, error_msg)
            return jsonify({
                "status": "error", 
                "message": error_msg
            }), 200
        
        sync_success, sync_msg = sync_tournament_data(tournament_id, api_data)
        log_webhook_event(
            webhook_id, 
            tournament_id, 
            event_types, 
            sync_success, 
            sync_msg if not sync_success else None
        )
        
        return jsonify({
            "status": "ok" if sync_success else "error",
            "message": sync_msg,
            "tournament_id": tournament_id,
            "events_processed": len(event_types),
            "sync_type": "full"
        }), 200
    
    else:
        # ✅ IMPROVED: Partial-Sync mit Match-Synchronisation
        webhook_logger.info(f"⚡ Partial-Sync für {tournament_id}")
        
        updated_resources = []
        
        # Verarbeite jedes Event einzeln
        for event in events:
            event_type = event.get('type')
            
            # 1. MATCH UPDATED - Synchronisiere Match
            if event_type == "MatchUpdated":
                match_id = event.get('match_id')
                if match_id:
                    webhook_logger.info(f"  🎯 Synchronisiere Match: {match_id}")
                    success, match_data, error_msg = fetch_single_match(tournament_id, match_id)
                    if success:
                        sync_match_to_db(tournament_id, match_data)  # ✅ Verwendet neue Fehlerbehandlung
                        updated_resources.append(f"match:{match_id}")
                        webhook_logger.info(f"  ✅ Match {match_id} synchronisiert")
                    else:
                        webhook_logger.error(f"  ❌ Match {match_id} Fehler: {error_msg}")
            
            # 2. COURT MATCH CHANGED - Aktualisiere Court
            elif event_type == "CourtMatchChanged":
                court_id = event.get('court_id')
                match_id = event.get('match_id')
                
                if court_id:
                    webhook_logger.info(f"  🏓 Aktualisiere Court: {court_id}")
                    
                    # Hole Court mit Match-Details
                    success, courts_data, error_msg = fetch_courts(tournament_id, include_match_details=True)
                    if success:
                        # Finde den betroffenen Court
                        court_data = next((c for c in courts_data if c.get('id') == court_id), None)
                        if court_data:
                            # Aktualisiere Court in DB
                            court = Court.query.get(court_id)
                            if court:
                                court.current_match_id = court_data.get('currentMatchId')
                                db.session.commit()
                                updated_resources.append(f"court:{court_id}")
                                webhook_logger.info(f"  ✅ Court {court_id} aktualisiert")
                            
                            # Wenn Match-Details vorhanden, speichere auch das Match
                            if court_data.get('currentMatch'):
                                match_data = court_data['currentMatch']
                                sync_match_to_db(tournament_id, match_data)
                                updated_resources.append(f"match:{match_data.get('id')}")
                    else:
                        webhook_logger.error(f"  ❌ Court {court_id} Fehler: {error_msg}")
        
        sync_success = True  # ✅ Erfolg auch wenn einzelne Matches fehlschlagen
        sync_msg = f"Partial-Sync: {len(updated_resources)} Ressourcen aktualisiert"
        
        log_webhook_event(webhook_id, tournament_id, event_types, sync_success, None)
        
        return jsonify({
            "status": "ok",
            "message": sync_msg,
            "tournament_id": tournament_id,
            "events_processed": len(event_types),
            "sync_type": "partial",
            "updated_resources": updated_resources
        }), 200


@webhook_bp.route('/test', methods=['POST'])
def test_webhook():
    """
    ✅ Test-Webhook mit detailliertem Logging
    """
    test_logger = logging.getLogger('webhook_test')
    
    try:
        data = request.get_json(force=True)
    except Exception as e:
        test_logger.error(f"❌ Invalid JSON: {e}")
        return jsonify({"error": "Invalid JSON"}), 400
    
    is_valid, tournament_id, webhook_id, payload = validate_webhook_payload(data)
    if not is_valid:
        test_logger.error(f"❌ Invalid payload: {data}")
        return jsonify({"error": "Invalid webhook payload"}), 400
    
    events = parse_webhook_events(payload)
    
    test_logger.info("\n" + "="*80)
    test_logger.info("🧪 TEST WEBHOOK - START")
    test_logger.info("="*80)
    test_logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    test_logger.info(f"Webhook-ID: {webhook_id}")
    test_logger.info(f"Tournament-ID: {tournament_id}")
    test_logger.info(f"Events: {len(events)}")
    test_logger.info("-"*80)
    
    test_logger.info("\n📦 ORIGINAL PAYLOAD:")
    test_logger.info(json.dumps(payload, indent=2, ensure_ascii=False))
    
    test_logger.info("\n📋 EVENTS BREAKDOWN:")
    for i, event in enumerate(events, 1):
        test_logger.info(f"\n  Event {i}/{len(events)}:")
        test_logger.info(f"    Type: {event.get('type')}")
        test_logger.info(f"    Created: {event.get('created_at')}")
        if event.get('match_id'):
            test_logger.info(f"    Match-ID: {event.get('match_id')}")
        if event.get('court_id'):
            test_logger.info(f"    Court-ID: {event.get('court_id')}")
    
    test_logger.info("\n" + "="*80)
    test_logger.info("✅ TEST WEBHOOK - COMPLETE")
    test_logger.info("="*80 + "\n")
    
    return jsonify({
        "status": "logged",
        "message": "Test-Webhook erfolgreich verarbeitet und geloggt",
        "webhook_id": webhook_id,
        "tournament_id": tournament_id,
        "events_count": len(events),
        "event_types": [e['type'] for e in events],
        "log_file": "logs/webhook_test.log"
    }), 200


@webhook_bp.route('/admin/reset-idempotency', methods=['POST'])
def reset_idempotency():
    """
    🔧 ADMIN: Löscht alle Webhook-Logs
    """
    try:
        from app.models import WebhookLog, db
        
        count = WebhookLog.query.count()
        WebhookLog.query.delete()
        db.session.commit()
        
        webhook_logger.info(f"🗑️ {count} Webhook-Logs gelöscht (Idempotenz-Reset)")
        
        return jsonify({
            "status": "ok",
            "message": f"{count} Webhook-Logs gelöscht",
            "deleted_count": count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        webhook_logger.error(f"❌ Fehler beim Löschen: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500