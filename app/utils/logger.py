"""
Logger-Konfiguration - ERWEITERT
✅ Fügt webhook_test Logger hinzu
"""
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    """
    Erstellt einen konfigurierten Logger mit Rotation
    
    Args:
        name: Logger-Name
        log_file: Dateiname (wird in logs/ gespeichert)
        level: Log-Level (default: INFO)
    
    Returns:
        Konfigurierter Logger
    """
    # Erstelle logs/ Verzeichnis falls nicht vorhanden
    os.makedirs('logs', exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Verhindere doppelte Handler
    if logger.handlers:
        return logger
    
    # File Handler mit Rotation (5MB, 5 Backups)
    handler = RotatingFileHandler(
        f'logs/{log_file}',
        maxBytes=5_000_000,
        backupCount=5,
        encoding='utf-8'
    )
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger


def setup_all_loggers():
    """
    Initialisiert alle Projekt-Logger
    
    ✅ NEU: Fügt webhook_test Logger hinzu
    """
    loggers = {
        'sync': 'sync.log',
        'webhooks': 'webhooks.log',
        'webhook_test': 'webhook_test.log',  # ✅ NEU
        'errors': 'errors.log'
    }
    
    for name, file in loggers.items():
        level = logging.ERROR if name == 'errors' else logging.INFO
        setup_logger(name, file, level)