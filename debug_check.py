"""
Debug-Script zum Überprüfen der Datenbank
Führe aus: python debug_check.py
"""
import sys
import os

# Füge Parent-Directory zum Path hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, Tournament, Entry, Discipline, Stage, Group, Standing, Match, Court

def check_database():
    """Überprüft alle Tabellen in der Datenbank"""
    
    app = create_app()
    
    with app.app_context():
        print("\n" + "="*80)
        print("🔍 DATABASE VERIFICATION REPORT")
        print("="*80 + "\n")
        
        # 1. TOURNAMENTS
        tournaments = Tournament.query.all()
        print(f"📊 TOURNAMENTS: {len(tournaments)}")
        for t in tournaments:
            print(f"  - {t.id}: {t.name} ({t.state})")
        print()
        
        # 2. ENTRIES
        entries = Entry.query.all()
        print(f"👥 ENTRIES: {len(entries)}")
        if entries:
            print(f"  Beispiel: {entries[0].id} - {entries[0].name}")
        else:
            print("  ❌ LEER!")
        print()
        
        # 3. DISCIPLINES
        disciplines = Discipline.query.all()
        print(f"🏆 DISCIPLINES: {len(disciplines)}")
        for d in disciplines:
            print(f"  - {d.id}: {d.name} (Tournament: {d.tournament_id})")
        print()
        
        # 4. STAGES
        stages = Stage.query.all()
        print(f"📍 STAGES: {len(stages)}")
        print()
        
        # 5. GROUPS
        groups = Group.query.all()
        print(f"🎯 GROUPS: {len(groups)}")
        for g in groups:
            print(f"  - {g.id}: {g.name} ({g.tournament_mode})")
        print()
        
        # 6. STANDINGS
        standings = Standing.query.all()
        print(f"📈 STANDINGS: {len(standings)}")
        if standings:
            print(f"  Beispiel: {standings[0].team_name} - Rank {standings[0].rank}")
        else:
            print("  ❌ LEER!")
        print()
        
        # 7. MATCHES
        matches = Match.query.all()
        print(f"🎮 MATCHES: {len(matches)}")
        if matches:
            m = matches[0]
            print(f"  Beispiel: {m.team1_name} vs {m.team2_name} ({m.state})")
        else:
            print("  ❌ LEER!")
        print()
        
        # 8. COURTS
        courts = Court.query.all()
        print(f"🏓 COURTS: {len(courts)}")
        if courts:
            print(f"  Beispiel: Court {courts[0].number} - {courts[0].name}")
        else:
            print("  ❌ LEER!")
        print()
        
        # DETAILED CHECK für ein Tournament
        if tournaments:
            t_id = tournaments[0].id
            print("="*80)
            print(f"📋 DETAILED CHECK für Tournament: {t_id}")
            print("="*80 + "\n")
            
            t_entries = Entry.query.filter_by(tournament_id=t_id).count()
            t_courts = Court.query.filter_by(tournament_id=t_id).count()
            
            t_standings = Standing.query.join(Group).join(Stage).join(Discipline).filter(
                Discipline.tournament_id == t_id
            ).count()
            
            t_matches = Match.query.join(Group).join(Stage).join(Discipline).filter(
                Discipline.tournament_id == t_id
            ).count()
            
            print(f"  Entries: {t_entries}")
            print(f"  Courts: {t_courts}")
            print(f"  Standings: {t_standings}")
            print(f"  Matches: {t_matches}")
            print()
            
            # Check für Foreign Key Integrität
            print("🔗 FOREIGN KEY INTEGRITY CHECK:")
            
            # Matches ohne Group
            orphan_matches = Match.query.filter(
                ~Match.group_id.in_(db.session.query(Group.id))
            ).count()
            print(f"  Matches ohne Group: {orphan_matches}")
            
            # Standings ohne Group
            orphan_standings = Standing.query.filter(
                ~Standing.group_id.in_(db.session.query(Group.id))
            ).count()
            print(f"  Standings ohne Group: {orphan_standings}")
            
            # Matches mit Entry-IDs
            matches_with_entries = Match.query.filter(
                Match.team1_entry_id.isnot(None)
            ).count()
            print(f"  Matches mit Entry-ID: {matches_with_entries} / {t_matches}")
            
        print("\n" + "="*80)
        print("✅ VERIFICATION COMPLETE")
        print("="*80 + "\n")


if __name__ == "__main__":
    check_database()