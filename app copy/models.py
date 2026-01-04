from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

db = SQLAlchemy()


class Tournament(db.Model):
    __tablename__ = 'tournaments'
    
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    state = db.Column(db.String(50), index=True)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    courts_count = db.Column(db.Integer, default=0)
    raw_snapshot = db.Column(JSONB)
    last_synced_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    entries = db.relationship('Entry', backref='tournament', lazy='dynamic', cascade='all, delete-orphan')
    disciplines = db.relationship('Discipline', backref='tournament', lazy='dynamic', cascade='all, delete-orphan')
    courts = db.relationship('Court', backref='tournament', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Tournament {self.id}: {self.name}>'


class Entry(db.Model):
    __tablename__ = 'entries'
    
    id = db.Column(db.String(100), primary_key=True)
    tournament_id = db.Column(db.String(100), db.ForeignKey('tournaments.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    entry_type = db.Column(db.String(50))  # single, team_name, dyp, byp, monster_dyp
    
    def __repr__(self):
        return f'<Entry {self.id}: {self.name}>'


class Discipline(db.Model):
    __tablename__ = 'disciplines'
    
    id = db.Column(db.String(100), primary_key=True)
    tournament_id = db.Column(db.String(100), db.ForeignKey('tournaments.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    short_name = db.Column(db.String(50))
    entry_type = db.Column(db.String(50))  # single, team_name, dyp, byp, monster_dyp
    
    # Relationships
    stages = db.relationship('Stage', backref='discipline', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Discipline {self.id}: {self.name}>'


class Stage(db.Model):
    __tablename__ = 'stages'
    
    id = db.Column(db.String(100), primary_key=True)
    discipline_id = db.Column(db.String(100), db.ForeignKey('disciplines.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(255))
    state = db.Column(db.String(50))  # planned, ready, running, finished
    
    # Relationships
    groups = db.relationship('Group', backref='stage', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Stage {self.id}: {self.state}>'


class Group(db.Model):
    __tablename__ = 'groups'
    
    id = db.Column(db.String(100), primary_key=True)
    stage_id = db.Column(db.String(100), db.ForeignKey('stages.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100))
    tournament_mode = db.Column(db.String(50))  # swiss, elimination, round_robin, monster_dyp, etc.
    state = db.Column(db.String(50))  # planned, ready, running, finished
    
    # Group Options (gespeichert als JSONB für Flexibilität)
    options = db.Column(JSONB)
    
    # Relationships
    standings = db.relationship('Standing', backref='group', lazy='dynamic', cascade='all, delete-orphan')
    matches = db.relationship('Match', backref='group', lazy='dynamic', cascade='all, delete-orphan')
    
    __table_args__ = (
        db.Index('ix_groups_stage_state', 'stage_id', 'state'),
    )
    
    def __repr__(self):
        return f'<Group {self.id}: {self.name}>'


class Standing(db.Model):
    __tablename__ = 'standings'
    
    id = db.Column(db.String(200), primary_key=True)
    group_id = db.Column(db.String(100), db.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False, index=True)
    entry_id = db.Column(db.String(100))  # Reference zu Entry
    rank = db.Column(db.Integer)
    team_name = db.Column(db.String(255), nullable=False)
    
    # Statistiken (können NULL sein wenn nicht verfügbar)
    points = db.Column(db.Integer)
    matches = db.Column(db.Integer)
    points_per_match = db.Column(db.Float)
    corrected_points_per_match = db.Column(db.Float)
    matches_won = db.Column(db.Integer)
    matches_lost = db.Column(db.Integer)
    matches_draw = db.Column(db.Integer)
    matches_diff = db.Column(db.Integer)
    sets_won = db.Column(db.Integer)
    sets_lost = db.Column(db.Integer)
    sets_diff = db.Column(db.Integer)
    goals = db.Column(db.Integer)
    goals_in = db.Column(db.Integer)
    goals_diff = db.Column(db.Integer)
    
    # Tiebreaker (Buchholz, Sonneborn-Berger)
    bh1 = db.Column(db.Float)
    bh2 = db.Column(db.Float)
    sb = db.Column(db.Float)
    
    # MonsterDYP / Last One Standing spezifisch
    lives = db.Column(db.Integer)
    result = db.Column(db.Integer)
    
    __table_args__ = (
        db.Index('ix_standings_group_rank', 'group_id', 'rank'),
    )
    
    def __repr__(self):
        return f'<Standing {self.team_name}: Rank {self.rank}>'


class Match(db.Model):
    __tablename__ = 'matches'
    
    id = db.Column(db.String(100), primary_key=True)
    group_id = db.Column(db.String(100), db.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Teams/Spieler
    team1_name = db.Column(db.String(255))
    team2_name = db.Column(db.String(255))
    team1_entry_id = db.Column(db.String(100))  # Reference zu Entry
    team2_entry_id = db.Column(db.String(100))
    
    # Match-Status
    state = db.Column(db.String(50), index=True)  # open, running, played, skipped, paused, bye
    
    # Scores
    score1 = db.Column(db.Integer)
    score2 = db.Column(db.Integer)
    encounters = db.Column(JSONB)  # Vollständige Encounter-Daten
    display_score = db.Column(JSONB)  # [score1, score2]
    
    # Metadaten
    discipline_id = db.Column(db.String(100))
    discipline_name = db.Column(db.String(255))
    round_id = db.Column(db.String(100))
    round_name = db.Column(db.String(100))
    group_name = db.Column(db.String(100))
    
    # Zeiten
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    
    # Court Assignment
    court_id = db.Column(db.String(100), db.ForeignKey('courts.id', ondelete='SET NULL'), nullable=True)
    is_live_result = db.Column(db.Boolean, default=False)
    
    __table_args__ = (
        db.Index('ix_matches_group_state', 'group_id', 'state'),
        db.Index('ix_matches_court', 'court_id'),
    )
    
    def __repr__(self):
        return f'<Match {self.id}: {self.team1_name} vs {self.team2_name}>'


class Court(db.Model):
    __tablename__ = 'courts'
    
    id = db.Column(db.String(100), primary_key=True)
    tournament_id = db.Column(db.String(100), db.ForeignKey('tournaments.id', ondelete='CASCADE'), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    current_match_id = db.Column(db.String(100), nullable=True)
    
    # Relationships
    matches = db.relationship('Match', backref='court', lazy='dynamic')
    
    __table_args__ = (
        db.Index('ix_courts_tournament', 'tournament_id', 'number'),
    )
    
    def __repr__(self):
        return f'<Court {self.number}: {self.name}>'


class WebhookLog(db.Model):
    """Verhindert doppelte Webhook-Verarbeitung (Idempotenz)"""
    __tablename__ = 'webhook_logs'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    webhook_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    tournament_id = db.Column(db.String(100), nullable=False, index=True)
    event_types = db.Column(JSONB)
    processed_at = db.Column(db.DateTime, default=datetime.utcnow)
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text)
    
    def __repr__(self):
        return f'<WebhookLog {self.webhook_id}: {self.tournament_id}>'