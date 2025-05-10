import os
from datetime import timedelta

# Application configuration
class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key-for-this-application'
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    
    # Admin config
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME') or 'admin'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'admin123'
    
    # File paths
    API_KEYS_FILE = os.path.join(os.path.dirname(__file__), 'api_keys.json')
    USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')
    STATS_FILE = os.path.join(os.path.dirname(__file__), 'stats.json')
    
    # Default API key settings
    DEFAULT_KEY_EXPIRY_DAYS = 30
    DEFAULT_HIT_LIMIT = 1000
