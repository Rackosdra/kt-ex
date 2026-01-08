"""
🔍 DEBUG SCRIPT - Analysiert warum Courts nicht gespeichert werden
"""
import os
import sys
import requests
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, Tournament, Court


def test_api_courts(tournament_id: str):
    """Testet ob API Courts liefert"""
    print("\n" + "="*80)
    print("🔍 TEST 1: API Courts Response")
    print("="*80)
    
    api_key = os.getenv('KICKERTOOL_API_KEY')
    if not api_key:
        print("❌ KICKERTOOL_API_KEY nicht gesetzt!")
        return False
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    # Test 1: Tournament-Endpoint mit includeCourts
    print("\n📞 GET /tournaments/{id}?includeCourts=true")
    try:
        response = requests.get(
            f"https://api.tournament.io/v1/public/tournaments/{tournament_id}",
            headers=headers,
            params={"includeCourts": "true"},
            timeout=10
        )
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            courts_in_response = data.get('courts', [])
            print(f"✅ Response erhalten")
            print(f"   → courts array: {'VORHANDEN' if 'courts' in data else 'FEHLT'}")
            print(f"   → Anzahl Courts: {len(courts_in_response)}")
            
            if courts_in_response:
                print(f"\n📋 Beispiel Court:")
                print(json.dumps(courts_in_response[0], indent=2))
            else:
                print("⚠️ Keine Courts im Tournament-Response!")
        else:
            print(f"❌ Fehler: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False
    
    # Test 2: Courts-Endpoint (separat)
    print("\n📞 GET /tournaments/{id}/courts")
    try:
        response = requests.get(
            f"https://api.tournament.io/v1/public/tournaments/{tournament_id}/courts",
            headers=headers,
            timeout=10
        )
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            courts_data = response.json()
            print(f"✅ Response erhalten")
            print(f"   → Anzahl Courts: {len(courts_data)}")
            
            if courts_data:
                print(f"\n📋 Alle Courts:")
                for c in courts_data:
                    print(f"   - Court {c.get('number')}: {c.get('name')} (ID: {c.get('id')})")
                    if c.get('currentMatchId'):
                        print(f"     → Match: {c.get('currentMatchId')}")
                
                print(f"\n📋 Erster Court (vollständig):")
                print(json.dumps(courts_data[0], indent=2))
                return True
            else:
                print("⚠️ API liefert leeres Array!")
                print("   → Mögliche Ursachen:")
                print("      1. Tournament hat keine Courts konfiguriert")
                print("      2. Tournament ist noch nicht gestartet")
                return False
        else:
            print(f"❌ Fehler: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False


def test_db_courts(tournament_id: str):
    """Testet DB-Courts"""
    print("\n" + "="*80)
    print("🔍 TEST 2: Datenbank Courts")
    print("="*80)
    
    app = create_app()
    
    with app.app_context():
        # Prüfe Tournament
        tournament = Tournament.query.get(tournament_id)
        if not tournament:
            print(f"❌ Tournament {tournament_id} nicht in DB!")
            return False
        
        print(f"\n📊 Tournament: {tournament.name}")
        print(f"   → State: {tournament.state}")
        print(f"   → courts_count: {tournament.courts_count}")
        
        # Prüfe Courts
        courts = Court.query.filter_by(tournament_id=tournament_id).all()
        print(f"\n📊 Courts in DB: {len(courts)}")
        
        if courts:
            print("\n✅ Courts gefunden:")
            for c in courts:
                print(f"   - Court {c.number}: {c.name}")
                print(f"     → ID: {c.id}")
                print(f"     → Match: {c.current_match_id or 'Kein'}")
            return True
        else:
            print("❌ KEINE Courts in DB!")
            return False


def test_court_constraints():
    """Testet DB-Constraints"""
    print("\n" + "="*80)
    print("🔍 TEST 3: DB Constraints")
    print("="*80)
    
    app = create_app()
    
    with app.app_context():
        try:
            # Prüfe Courts-Tabelle
            result = db.session.execute(db.text("""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = 'courts'
                ORDER BY ordinal_position
            """))
            
            print("\n📋 Courts-Tabellen-Struktur:")
            for row in result:
                nullable = "NULL" if row[2] == 'YES' else "NOT NULL"
                default = f"DEFAULT {row[3]}" if row[3] else ""
                print(f"   - {row[0]}: {row[1]} {nullable} {default}")
            
            # Prüfe Constraints
            result = db.session.execute(db.text("""
                SELECT
                    conname as constraint_name,
                    contype as constraint_type
                FROM pg_constraint
                WHERE conrelid = 'courts'::regclass
            """))
            
            print("\n📋 Constraints:")
            constraints = list(result)
            if constraints:
                for row in constraints:
                    ctype = {
                        'p': 'PRIMARY KEY',
                        'f': 'FOREIGN KEY',
                        'u': 'UNIQUE',
                        'c': 'CHECK'
                    }.get(row[1], row[1])
                    print(f"   - {row[0]}: {ctype}")
            else:
                print("   → Keine Constraints gefunden")
            
            # Prüfe Indexes
            result = db.session.execute(db.text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'courts'
            """))
            
            print("\n📋 Indexes:")
            for row in result:
                print(f"   - {row[0]}")
            
            return True
            
        except Exception as e:
            print(f"❌ Fehler: {e}")
            import traceback
            traceback.print_exc()
            return False


def simulate_court_save(tournament_id: str):
    """Simuliert Court-Speicherung"""
    print("\n" + "="*80)
    print("🔍 TEST 4: Simuliere Court-Speicherung")
    print("="*80)
    
    app = create_app()
    
    with app.app_context():
        try:
            # Lösche alte Test-Courts
            print("\n🧹 Lösche alte Test-Courts...")
            Court.query.filter(Court.id.like('test_%')).delete()
            db.session.commit()
            
            # Erstelle Test-Court
            print("\n📝 Erstelle Test-Court...")
            test_court = Court(
                id='test_court_123',
                tournament_id=tournament_id,
                number=999,
                name='Test Court',
                current_match_id=None
            )
            db.session.add(test_court)
            db.session.commit()
            print("✅ Test-Court erstellt")
            
            # Verifiziere
            print("\n🔍 Verifiziere...")
            saved_court = Court.query.get('test_court_123')
            if saved_court:
                print("✅ Test-Court erfolgreich gespeichert und geladen!")
                print(f"   → ID: {saved_court.id}")
                print(f"   → Number: {saved_court.number}")
                print(f"   → Name: {saved_court.name}")
                
                # Cleanup
                db.session.delete(saved_court)
                db.session.commit()
                print("\n🧹 Test-Court gelöscht")
                
                return True
            else:
                print("❌ Test-Court nicht gefunden nach Speicherung!")
                return False
                
        except Exception as e:
            db.session.rollback()
            print(f"❌ Fehler beim Speichern: {e}")
            import traceback
            traceback.print_exc()
            return False


def analyze_sync_logs():
    """Analysiert Sync-Logs"""
    print("\n" + "="*80)
    print("🔍 TEST 5: Analysiere Sync-Logs")
    print("="*80)
    
    log_file = 'logs/sync.log'
    
    if not os.path.exists(log_file):
        print(f"⚠️ Log-Datei nicht gefunden: {log_file}")
        return False
    
    print(f"\n📄 Analysiere: {log_file}")
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Suche nach Court-relevanten Zeilen
    court_lines = [l for l in lines if 'court' in l.lower()]
    
    if court_lines:
        print(f"\n✅ {len(court_lines)} Court-relevante Log-Zeilen gefunden:")
        print("\n📋 Letzte 10 Zeilen:")
        for line in court_lines[-10:]:
            print(f"   {line.strip()}")
    else:
        print("⚠️ Keine Court-relevanten Log-Zeilen gefunden")
    
    # Suche nach Fehlern
    error_lines = [l for l in lines if 'error' in l.lower() or 'fehler' in l.lower()]
    
    if error_lines:
        print(f"\n⚠️ {len(error_lines)} Fehler-Zeilen gefunden:")
        print("\n📋 Letzte 5 Fehler:")
        for line in error_lines[-5:]:
            print(f"   {line.strip()}")
    
    return True


def main():
    """Hauptfunktion"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Debug Courts Problem')
    parser.add_argument(
        'tournament_id',
        help='Tournament ID zum Testen'
    )
    
    args = parser.parse_args()
    tournament_id = args.tournament_id
    
    print("\n" + "="*80)
    print("🔧 COURTS DEBUG ANALYSIS")
    print("="*80)
    print(f"Tournament ID: {tournament_id}")
    
    results = {
        "api_test": test_api_courts(tournament_id),
        "db_test": test_db_courts(tournament_id),
        "constraints_test": test_court_constraints(),
        "save_simulation": simulate_court_save(tournament_id),
        "log_analysis": analyze_sync_logs()
    }
    
    # Zusammenfassung
    print("\n" + "="*80)
    print("📊 ZUSAMMENFASSUNG")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ ALLE TESTS BESTANDEN")
        print("   → Courts können grundsätzlich gespeichert werden")
        print("   → Problem liegt wahrscheinlich im Sync-Code")
    else:
        print("❌ EINIGE TESTS FEHLGESCHLAGEN")
        
        if not results['api_test']:
            print("\n⚠️ API liefert keine Courts!")
            print("   → Prüfe ob Tournament Courts hat")
            print("   → Teste mit anderem Tournament")
        
        if not results['db_test']:
            print("\n⚠️ Keine Courts in DB!")
            print("   → Sync funktioniert nicht korrekt")
            print("   → Prüfe Sync-Logs")
        
        if not results['save_simulation']:
            print("\n⚠️ Court-Speicherung schlägt fehl!")
            print("   → DB-Problem oder Constraint-Violation")
            print("   → Prüfe Constraints und Foreign Keys")
    
    print("="*80 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())