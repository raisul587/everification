from datetime import datetime, timedelta
import secrets
import json
from database import (get_db, get_user, get_user_by_id, get_api_key, update_api_key_hits,
                     get_all_api_keys, get_stats, update_stats, log_activity,
                     get_user_activities)

class APIKey:
    """Model for API key management"""
    def __init__(self, owner_name, expiry_date, hit_limit, allowed_origins=None, key=None, active=True):
        self.id = secrets.token_hex(4)
        self.key = key or secrets.token_hex(16)
        self.owner_name = owner_name
        self.expiry_date = expiry_date
        self.hit_limit = hit_limit
        self.hits_used = 0
        self.allowed_origins = allowed_origins or []
        self.created_at = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        self.active = active

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "owner_name": self.owner_name,
            "expiry_date": self.expiry_date,
            "hit_limit": self.hit_limit,
            "hits_used": self.hits_used,
            "allowed_origins": self.allowed_origins,
            "created_at": self.created_at,
            "active": self.active
        }

    def is_valid(self):
        """Check if the API key is valid based on expiry date and usage"""
        if not self.active:
            return False

        # Check expiry
        try:
            expiry = datetime.strptime(self.expiry_date, "%Y-%m-%d %I:%M:%S %p")
            if expiry < datetime.now():
                return False
        except:
            # If expiry date is just a date without time
            try:
                expiry = datetime.strptime(self.expiry_date, "%Y-%m-%d")
                if expiry < datetime.now():
                    return False
            except:
                return False
        
        # Check hit limit
        if self.hit_limit > 0 and self.hits_used >= self.hit_limit:
            return False
        
        return True

    def increment_usage(self):
        """Increment the usage counter for this key"""
        self.hits_used += 1
        update_api_key_hits(self.id, self.hits_used)
        return self.hits_used

    def can_access_from_origin(self, origin):
        """Check if the key can be used from the given origin"""
        if not self.allowed_origins:
            return True
        return origin in self.allowed_origins


class KeyStore:
    """Storage for API keys"""
    def __init__(self):
        self.keys = {}
        self.load_keys()

    def load_keys(self):
        """Load keys from the database"""
        keys_data = get_all_api_keys()
        self.keys = {}
        for key_id, key_data in keys_data.items():
            api_key = APIKey(
                owner_name=key_data.get('owner_name', ''),
                expiry_date=key_data.get('expiry_date', ''),
                hit_limit=key_data.get('hit_limit', 0),
                allowed_origins=key_data.get('allowed_origins', []),  # Already deserialized in database.py
                key=key_data.get('key', ''),
                active=key_data.get('active', True)
            )
            api_key.id = key_id
            api_key.hits_used = key_data.get('hits_used', 0)
            api_key.created_at = key_data.get('created_at', api_key.created_at)
            self.keys[key_id] = api_key

    def save_keys(self):
        """No need to save keys as they are managed in the database"""
        pass

    def get_key(self, api_key):
        """Get a key by its value"""
        key_data = get_api_key(api_key)
        if not key_data:
            return None
        
        api_key = APIKey(
            owner_name=key_data['owner_name'],
            expiry_date=key_data['expiry_date'],
            hit_limit=key_data['hit_limit'],
            allowed_origins=key_data['allowed_origins'],
            key=key_data['key'],
            active=key_data['active']
        )
        api_key.id = key_data['id']
        api_key.hits_used = key_data['hits_used']
        api_key.created_at = key_data['created_at']
        return api_key

    def get_keys(self):
        """Get all keys"""
        self.load_keys()  # Refresh from database
        return self.keys

    def add_key(self, key):
        """Add a new key"""
        try:
            conn = get_db()
            # Check if key exists
            cursor = conn.execute('SELECT id FROM api_keys WHERE id = ? OR key = ?', (key.id, key.key))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing key
                conn.execute('''UPDATE api_keys SET 
                    key = ?, owner_name = ?, expiry_date = ?, hit_limit = ?, 
                    hits_used = ?, allowed_origins = ?, active = ?
                    WHERE id = ?''',
                    (key.key, key.owner_name, key.expiry_date, key.hit_limit,
                     key.hits_used, json.dumps(key.allowed_origins), key.active, key.id))
            else:
                # Insert new key
                conn.execute('''INSERT INTO api_keys 
                    (id, key, owner_name, expiry_date, hit_limit, hits_used, allowed_origins, created_at, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (key.id, key.key, key.owner_name, key.expiry_date,
                     key.hit_limit, key.hits_used, json.dumps(key.allowed_origins),
                     key.created_at, key.active))
            
            conn.commit()
            self.keys[key.id] = key
            return key
        except Exception as e:
            print(f"Error in add_key: {e}")
            raise
        finally:
            if 'conn' in locals():
                conn.close()

    def delete_key(self, key_id):
        """Delete a key"""
        if key_id in self.keys:
            conn = get_db()
            conn.execute('DELETE FROM api_keys WHERE id = ?', (key_id,))
            conn.commit()
            conn.close()
            del self.keys[key_id]
            return True
        return False


class User:
    """Simple user model for admin authentication"""
    def __init__(self, username, password_hash, is_admin=False):
        self.id = secrets.token_hex(4)
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin
        self.created_at = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "password_hash": self.password_hash,
            "is_admin": self.is_admin,
            "created_at": self.created_at
        }


class UserStore:
    """Storage for users"""
    def __init__(self):
        pass

    def get_user_by_username(self, username):
        """Get a user by username"""
        user_data = get_user(username)
        if user_data:
            user = User(user_data['username'], user_data['password_hash'], user_data['is_admin'])
            user.id = user_data['id']
            user.created_at = user_data['created_at']
            return user
        return None

    def add_user(self, user):
        """Add a new user"""
        conn = get_db()
        conn.execute('''INSERT INTO users 
            (id, username, password_hash, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?)''',
            (user.id, user.username, user.password_hash,
             user.is_admin, user.created_at))
        conn.commit()
        conn.close()
        return user


class Stats:
    """Statistics storage for the dashboard"""
    def __init__(self):
        pass

    def register_request(self, success=True, endpoint=None):
        """Register a new API request
        
        Args:
            success: Whether the request was successful
            endpoint: The endpoint that was requested (used to filter captcha requests)
        """
        # Skip counting captcha requests
        if endpoint == 'api_get_captcha':
            return
            
        update_stats(success)

    def get_stats(self):
        """Get all statistics"""
        return get_stats()


class UserActivity:
    """User activity tracking for the dashboard"""
    def __init__(self):
        pass

    def add_activity(self, api_key, event_type, details=None, success=True, ip_address="N/A"):
        """Add a new user activity"""
        # Skip logging captcha requests (they don't have a Name field)
        if event_type == "api_get_captcha" or (details and details.get('endpoint') == 'api_get_captcha'):
            return None
            
        return log_activity(api_key, event_type, details or {}, success, ip_address)

    def get_activities(self, page=1, per_page=10):
        """Get paginated activities"""
        activities = get_user_activities()
        start = (page - 1) * per_page
        end = start + per_page
        return activities[start:end], len(activities)

    def get_recent_activities(self, limit=5):
        """Get the most recent activities"""
        return get_user_activities(limit)


# Create global instances for use across the application
key_store = KeyStore()
user_store = UserStore()
stats = Stats()
user_activity = UserActivity()
