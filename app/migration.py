"""
Database Migration Script - Version 2.2
Fügt discipline_ids zu Entry-Tabelle hinzu
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Füge app-Pfad hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import db
from app import create_app


def run_migration():
    """Führt Database Migration durch"""
    
    print("\n" + "="*80)
    print("🔧 DATABASE MIGRATION - Version 2.2")
    print("="*80)
    
    # Erstelle App-Context
    app = create_app()
    
    with app.app_context():
        try:
            # 1. Prüfe ob Spalte bereits existiert
            print("\n📊 Prüfe aktuelle Tabellen-Struktur...")
            
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'entries' 
                AND column_name = 'discipline_ids'
            """))
            
            exists = result.fetchone() is not None
            
            if exists:
                print("✅ Spalte 'discipline_ids' existiert bereits")
                print("⚠️ Migration wurde bereits durchgeführt")
                return True
            
            # 2. Füge neue Spalte hinzu
            print("\n🔹 Füge Spalte 'discipline_ids' zu 'entries' hinzu...")
            
            db.session.execute(text("""
                ALTER TABLE entries 
                ADD COLUMN discipline_ids JSONB
            """))
            
            db.session.commit()
            print("✅ Spalte erfolgreich hinzugefügt")
            
            # 3. Erstelle Index für bessere Performance
            print("\n🔹 Erstelle Index für 'discipline_ids'...")
            
            try:
                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_entries_discipline_ids 
                    ON entries USING GIN (discipline_ids)
                """))
                db.session.commit()
                print("✅ Index erfolgreich erstellt")
            except Exception as e:
                print(f"⚠️ Index-Erstellung fehlgeschlagen (kann ignoriert werden): {e}")
            
            # 4. Verifiziere Migration
            print("\n🔹 Verifiziere Migration...")
            
            result = db.session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'entries' 
                AND column_name = 'discipline_ids'
            """))
            
            column_info = result.fetchone()
            if column_info:
                print(f"✅ Verifizierung erfolgreich:")
                print(f"   - Spaltenname: {column_info[0]}")
                print(f"   - Datentyp: {column_info[1]}")
            else:
                print("❌ Verifizierung fehlgeschlagen!")
                return False
            
            # 5. Statistik
            print("\n📊 Statistik:")
            
            entry_count = db.session.execute(text("SELECT COUNT(*) FROM entries")).scalar()
            print(f"   - Anzahl Entries: {entry_count}")
            
            if entry_count > 0:
                null_count = db.session.execute(text("""
                    SELECT COUNT(*) FROM entries WHERE discipline_ids IS NULL
                """)).scalar()
                print(f"   - Entries ohne Discipline-Zuordnung: {null_count}")
            
            print("\n" + "="*80)
            print("✅ MIGRATION ERFOLGREICH ABGESCHLOSSEN")
            print("="*80)
            print("\n⚠️ WICHTIG: Server neustarten erforderlich!")
            print("   docker-compose restart\n")
            
            return True
            
        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"\n❌ FEHLER bei Migration: {e}")
            print("\n🔄 Rollback durchgeführt")
            return False
        
        except Exception as e:
            print(f"\n❌ UNERWARTETER FEHLER: {e}")
            return False


def rollback_migration():
    """Macht Migration rückgängig (nur für Testing!)"""
    
    print("\n" + "="*80)
    print("⚠️ ROLLBACK MIGRATION - Version 2.2")
    print("="*80)
    print("\n⚠️ WARNUNG: Dies löscht die 'discipline_ids' Spalte!")
    
    confirm = input("Wirklich fortfahren? (yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ Abgebrochen")
        return False
    
    app = create_app()
    
    with app.app_context():
        try:
            print("\n🔹 Entferne Index...")
            db.session.execute(text("""
                DROP INDEX IF EXISTS ix_entries_discipline_ids
            """))
            db.session.commit()
            print("✅ Index entfernt")
            
            print("\n🔹 Entferne Spalte 'discipline_ids'...")
            db.session.execute(text("""
                ALTER TABLE entries 
                DROP COLUMN IF EXISTS discipline_ids
            """))
            db.session.commit()
            print("✅ Spalte entfernt")
            
            print("\n✅ ROLLBACK ERFOLGREICH")
            return True
            
        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"\n❌ FEHLER bei Rollback: {e}")
            return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Database Migration v2.2')
    parser.add_argument(
        '--rollback', 
        action='store_true',
        help='Rollback migration (use with caution!)'
    )
    
    args = parser.parse_args()
    
    if args.rollback:
        success = rollback_migration()
    else:
        success = run_migration()
    
    sys.exit(0 if success else 1)