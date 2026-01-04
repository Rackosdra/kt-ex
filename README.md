# Kickertool API v2.0 - Production Ready

Flask-basierte Webhook-API für Tournament.app (Kickertool V3) mit PostgreSQL und Cloudflare Tunnel.

## 🎯 Key Features

- ✅ **Idempotente Webhooks** - Verhindert doppelte Verarbeitung
- ✅ **Robuste Fehlerbehandlung** - Structured Logging & Rollbacks
- ✅ **Optimierte DB-Performance** - Batch-Upserts & Indizes
- ✅ **Sicherheit** - Environment Variables, Non-Root Container
- ✅ **Monitoring** - Health-Checks für alle Services
- ✅ **Production-Ready** - Multi-Stage Docker Build

---

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Kopiere Template und fülle Secrets aus
cp .env.example .env
nano .env
```

**Wichtig:** Ändere `POSTGRES_PASSWORD` und `KICKERTOOL_API_KEY`!

### 2. Development Mode (Hot-Reload aktiviert)

```bash
# Option A: Mit Makefile (empfohlen)
make dev

# Option B: Manuell
# Setze in .env: FLASK_DEBUG=1
docker-compose up --build -d
docker-compose logs -f api
```

**Änderungen in `app/*.py` werden automatisch erkannt!** 🔥

### 3. Production Mode

```bash
# Option A: Mit Makefile
make prod

# Option B: Manuell
# Setze in .env: FLASK_DEBUG=0
docker-compose up --build -d
```

### 4. Schnelle Befehle

```bash
make help       # Zeige alle verfügbaren Befehle
make restart    # API neu starten
make logs       # Live-Logs anzeigen
make shell      # Shell im Container
make test       # Webhook testen
```

### 3. Webhook-Konfiguration in Tournament.app

1. Login auf [Tournament.app](https://alpha.kickertool.de)
2. Profil → Settings → API → Create Webhook
3. Webhook-URL von Cloudflare Tunnel kopieren (siehe Logs: `docker-compose logs tunnel`)
4. Webhook-URL eintragen: `https://<tunnel-url>/webhook/kickertool`

---

## 🔥 Development Workflow

### Live-Coding mit Hot-Reload

```bash
# 1. Starte im Dev-Mode
make dev

# 2. Ändere Code in app/routes.py, app/models.py etc.
# 3. Flask erkennt Änderungen automatisch und lädt neu!

# Logs live verfolgen
make logs
```

**Was wird gemountet:**
- `./app/` → `/app/app/` (alle Python-Module)
- `./run.py` → `/app/run.py`
- `./logs/` → `/app/logs/` (Logs bleiben auf Host)

### Code-Änderung testen

```bash
# 1. Ändere z.B. app/routes.py
echo "# Test-Comment" >> app/routes.py

# 2. Container erkennt Änderung automatisch
# Logs zeigen: "Detected change in '/app/app/routes.py', reloading"

# 3. Teste sofort
curl http://localhost:5000/health
```

### Wechsel zwischen Dev/Prod

```bash
# Development (Hot-Reload AN)
make dev

# Production (Hot-Reload AUS, bessere Performance)
make prod
```

---

## 📡 API Endpoints

### System

**Health Check**
```bash
GET /health
```

**Root Info**
```bash
GET /
```

### Webhooks (von Tournament.app)

**Production Webhook**
```bash
POST /webhook/kickertool
```

**Test Webhook (Logging)**
```bash
POST /webhook/test
Content-Type: application/json
{"tournamentId": "tio:abc123"}
```

### Tournament Daten

**Tournament Info**
```bash
GET /tournaments/{tournament_id}
GET /tournaments/{tournament_id}/stats
```

**Teilnehmer**
```bash
GET /tournaments/{tournament_id}/entries
```

**Tische/Courts**
```bash
GET /tournaments/{tournament_id}/courts
```

**Disziplinen**
```bash
GET /tournaments/{tournament_id}/disciplines
GET /tournaments/{tournament_id}/disciplines/{discipline_id}/groups
```

**Ranglisten**
```bash
GET /tournaments/{tournament_id}/groups/{group_id}/standings
```

**Spiele**
```bash
GET /tournaments/{tournament_id}/groups/{group_id}/matches
GET /tournaments/{tournament_id}/groups/{group_id}/matches?state=running
GET /tournaments/{tournament_id}/matches/running
```

**Suche**
```bash
GET /tournaments/{tournament_id}/search?q=spielername
```

### Beispiele

```bash
# Alle laufenden Spiele
curl http://localhost:5000/tournaments/tio:E0y4V65tbEATG/matches/running

# Rangliste einer Gruppe
curl http://localhost:5000/tournaments/tio:E0y4V65tbEATG/groups/tio:UcYgOIZqIvB7t/standings

# Suche nach Spieler
curl "http://localhost:5000/tournaments/tio:E0y4V65tbEATG/search?q=mueller"
```

---

## 📊 Datenmodell (Vollständig)

```
Tournament (Turnier)
├── id, name, description, state
├── start_time, end_time
├── courts_count, raw_snapshot
└── Relationships:
    ├── Courts (Tische)
    │   ├── id, number, name
    │   └── current_match_id
    ├── Entries (Teams/Spieler)
    │   ├── id, name, entry_type
    │   └── ...
    └── Disciplines (Disziplinen)
        ├── id, name, short_name, entry_type
        └── Stages (Turnierphasen)
            ├── id, state
            └── Groups (Gruppen)
                ├── id, name, tournament_mode, state, options
                ├── Standings (Ranglisten)
                │   ├── rank, team_name, entry_id
                │   ├── points, matches, points_per_match
                │   ├── matches_won/lost/draw, sets_won/lost
                │   ├── goals, goals_in, goals_diff
                │   ├── bh1, bh2, sb (Buchholz, Sonneborn-Berger)
                │   └── lives, result (MonsterDYP)
                └── Matches (Spiele)
                    ├── id, state, team1/2_name, team1/2_entry_id
                    ├── score1/2, display_score, encounters (JSONB)
                    ├── discipline_id/name, round_id/name, group_name
                    ├── start_time, end_time
                    ├── court_id, is_live_result
                    └── ...
```

**Komplett gespeichert:**
- ✅ Turniere mit allen Metadaten
- ✅ Courts mit aktuellen Matches
- ✅ Alle Teilnehmer (Entries)
- ✅ Hierarchie: Disciplines → Stages → Groups
- ✅ Vollständige Standings mit allen Stats
- ✅ Matches mit Encounters, Scores, Zeiten
- ✅ Webhook-Log für Idempotenz
- ✅ raw_snapshot (komplettes JSON als Backup)

---

## 🔍 Logging & Debugging

### Log-Dateien

| Datei | Inhalt |
|-------|--------|
| `logs/sync.log` | Sync-Operationen mit Tournament.io API |
| `logs/webhooks.log` | Alle Webhook-Events (inkl. Test-Snapshots) |
| `logs/errors.log` | Kritische Fehler |

### Logs in Echtzeit

```bash
# Alle API-Logs
docker-compose logs -f api

# Nur Fehler
docker-compose logs -f api | grep ERROR

# Webhook-Events
docker exec kickertool_project-api-1 tail -f /app/logs/webhooks.log
```

### Debugging-Workflow

1. **Test-Webhook auslösen** in Tournament.app
2. **Logs prüfen:**
   ```bash
   cat logs/webhooks.log | grep "TEST SNAPSHOT"
   ```
3. **Bei Fehlern:**
   ```bash
   cat logs/errors.log
   ```

---

## 🛡️ Sicherheit

### Secrets Management
- ✅ API-Token in `.env` (nie im Code!)
- ✅ `.env` in `.gitignore`
- ✅ Non-root User im Container
- ✅ Cloudflare Tunnel statt Port-Forwarding

### Input Validation
- ✅ JSON-Schema-Validierung
- ✅ SQL-Injection-Schutz (SQLAlchemy ORM)
- ✅ Request-Timeouts

---

## ⚙️ Performance-Optimierungen

### Implementiert

1. **Batch-Upserts** - Alle Entities in einer Transaktion
2. **Connection Pooling** - 10 Connections, Auto-Reconnect
3. **DB-Indizes** - Optimiert für häufige Queries
4. **Lazy Loading** - Relationships nur bei Bedarf

### Monitoring

```bash
# Container-Stats
docker stats kickertool_project-api-1

# DB-Performance
docker exec kickertool_project-db-1 psql -U user -d kickertool_db -c "
  SELECT schemaname, tablename, 
         pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
  FROM pg_tables WHERE schemaname = 'public';
"
```

---

## 🧪 Testing

### Manueller Test-Workflow

1. **Health-Check:**
   ```bash
   curl http://localhost:5000/health
   ```

2. **Simuliere Webhook:**
   ```bash
   curl -X POST http://localhost:5000/webhook/test \
     -H "Content-Type: application/json" \
     -d '{
       "id": 999,
       "tournamentId": "tio:DEINE_TURNIER_ID"
     }'
   ```

3. **Prüfe Logs:**
   ```bash
   tail -n 50 logs/webhooks.log
   ```

4. **Prüfe DB:**
   ```bash
   docker exec -it kickertool_project-db-1 psql -U user -d kickertool_db
   
   # In psql:
   SELECT * FROM tournaments;
   SELECT COUNT(*) FROM matches WHERE state = 'running';
   ```

---

## 🔧 Troubleshooting

### Problem: "Database connection failed"

```bash
# Prüfe DB-Container
docker-compose ps db

# Prüfe DB-Logs
docker-compose logs db

# Teste Connection manuell
docker exec kickertool_project-db-1 pg_isready -U user
```

### Problem: "API Authentication failed"

```bash
# Prüfe API-Key in .env
cat .env | grep KICKERTOOL_API_KEY

# Teste API-Key
curl -H "Authorization: Bearer $(grep KICKERTOOL_API_KEY .env | cut -d= -f2)" \
  https://api.tournament.io/v1/public/hello
```

### Problem: Webhooks kommen nicht an

1. Prüfe Cloudflare Tunnel URL:
   ```bash
   docker-compose logs tunnel | grep "https://"
   ```

2. Teste Erreichbarkeit:
   ```bash
   curl https://<tunnel-url>/health
   ```

3. Prüfe Webhook-Config in Tournament.app Settings

---

## 📈 Produktions-Checkliste

- [ ] `.env` mit sicheren Passwörtern
- [ ] `FLASK_ENV=production` in `.env`
- [ ] Backup-Strategie für PostgreSQL
- [ ] Log-Rotation konfiguriert (bereits aktiv: 5MB × 5 Files)
- [ ] Monitoring-Alerts (z.B. Uptime-Kuma)
- [ ] Cloudflare Tunnel permanent (ggf. zu Named Tunnel migrieren)

---

## 🔄 Updates & Wartung

### Code-Update

```bash
git pull
docker-compose down
docker-compose up --build -d
```

### Datenbank-Backup

```bash
# Backup erstellen
docker exec kickertool_project-db-1 pg_dump -U user kickertool_db > backup_$(date +%F).sql

# Restore
docker exec -i kickertool_project-db-1 psql -U user kickertool_db < backup.sql
```

### Logs rotieren (manuell)

```bash
rm logs/*.log.{4,5}
```

---

## 📝 Changelog v2.0

### Neu
- ✅ Idempotente Webhook-Verarbeitung
- ✅ Strukturiertes 3-Level-Logging (sync, webhooks, errors)
- ✅ Input-Validierung für alle Endpoints
- ✅ Health-Checks für Container & DB
- ✅ Sicheres Environment-Management
- ✅ Tournament Stats Endpoint

### Optimiert
- 🚀 Batch-Upserts statt einzelner Merges
- 🚀 DB-Indizes für häufige Queries
- 🚀 Connection Pooling mit Auto-Reconnect
- 🚀 Multi-Stage Docker Build

### Behoben
- 🐛 Race-Conditions bei gleichzeitigen Webhooks
- 🐛 Fehlende Rollbacks bei Exceptions
- 🐛 Unbehandelte API-Timeouts
- 🐛 Missing Team-Names bei MonsterDYP

---

## 🤝 Support

- **Dokumentation:** [Tournament.app API Docs](https://alpha.kickertool.de/api-docs)
- **Issues:** GitHub Issues (wenn öffentlich)
- **Logs:** Immer `logs/errors.log` checken!

---

**Built with ❤️ for the Foosball Community**