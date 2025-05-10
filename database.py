import sqlite3
import json
from datetime import datetime
import os

DB_PATH = 'app.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Create users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin BOOLEAN NOT NULL,
        created_at TEXT NOT NULL
    )''')

    # Create api_keys table
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        key TEXT UNIQUE NOT NULL,
        owner_name TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        hit_limit INTEGER NOT NULL,
        hits_used INTEGER NOT NULL DEFAULT 0,
        allowed_origins TEXT NOT NULL,
        created_at TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT true
    )''')

    # Create stats table
    c.execute('''CREATE TABLE IF NOT EXISTS stats (
        id INTEGER PRIMARY KEY,
        total_requests INTEGER NOT NULL DEFAULT 0,
        successful_requests INTEGER NOT NULL DEFAULT 0,
        failed_requests INTEGER NOT NULL DEFAULT 0
    )''')

    # Create daily_stats table
    c.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
        date TEXT PRIMARY KEY,
        total INTEGER NOT NULL DEFAULT 0,
        successful INTEGER NOT NULL DEFAULT 0,
        failed INTEGER NOT NULL DEFAULT 0
    )''')
    
    # Create hourly_stats table
    c.execute('''CREATE TABLE IF NOT EXISTS hourly_stats (
        hour TEXT PRIMARY KEY,
        total INTEGER NOT NULL DEFAULT 0,
        successful INTEGER NOT NULL DEFAULT 0,
        failed INTEGER NOT NULL DEFAULT 0
    )''')

    # Create user_activity table
    c.execute('''CREATE TABLE IF NOT EXISTS user_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        api_key TEXT NOT NULL,
        event_type TEXT NOT NULL,
        details TEXT NOT NULL,
        success BOOLEAN NOT NULL,
        ip_address TEXT
    )''')

    # Insert initial stats record if not exists
    c.execute('INSERT OR IGNORE INTO stats (id, total_requests, successful_requests, failed_requests) VALUES (1, 0, 0, 0)')
    
    conn.commit()
    conn.close()

def migrate_data():
    # Initialize database
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Migrate users
    if os.path.exists('users.json'):
        with open('users.json', 'r') as f:
            users = json.load(f)
            for user_id, user_data in users.items():
                c.execute('''INSERT OR REPLACE INTO users 
                    (id, username, password_hash, is_admin, created_at)
                    VALUES (?, ?, ?, ?, ?)''',
                    (user_id, user_data['username'], user_data['password_hash'],
                     user_data['is_admin'], user_data['created_at']))

    # Migrate API keys
    if os.path.exists('api_keys.json'):
        with open('api_keys.json', 'r') as f:
            api_keys = json.load(f)
            for key_id, key_data in api_keys.items():
                c.execute('''INSERT OR REPLACE INTO api_keys 
                    (id, key, owner_name, expiry_date, hit_limit, hits_used, allowed_origins, created_at, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (key_id, key_data['key'], key_data['owner_name'], key_data['expiry_date'],
                     key_data['hit_limit'], key_data['hits_used'], 
                     json.dumps(key_data['allowed_origins']), key_data['created_at'], key_data['active']))

    # Migrate stats
    if os.path.exists('stats.json'):
        with open('stats.json', 'r') as f:
            stats_data = json.load(f)
            c.execute('''UPDATE stats SET 
                total_requests = ?, successful_requests = ?, failed_requests = ?
                WHERE id = 1''',
                (stats_data['total_requests'], stats_data['successful_requests'],
                 stats_data['failed_requests']))
            
            # Migrate daily stats
            for date, daily_data in stats_data['daily_stats'].items():
                c.execute('''INSERT OR REPLACE INTO daily_stats 
                    (date, total, successful, failed)
                    VALUES (?, ?, ?, ?)''',
                    (date, daily_data['total'], daily_data['successful'],
                     daily_data['failed']))

    # Migrate user activity
    if os.path.exists('user_activity.json'):
        with open('user_activity.json', 'r') as f:
            activities = json.load(f)
            for activity in activities:
                c.execute('''INSERT OR REPLACE INTO user_activity 
                    (id, timestamp, api_key, event_type, details, success, ip_address)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (activity['id'], activity['timestamp'], activity['api_key'],
                     activity['event_type'], json.dumps(activity['details']),
                     activity['success'], activity['ip_address']))

    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# User functions
def get_user(username):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

# API key functions
def get_api_key(key):
    conn = get_db()
    api_key = conn.execute('SELECT * FROM api_keys WHERE key = ?', (key,)).fetchone()
    if api_key:
        result = dict(api_key)
        result['allowed_origins'] = json.loads(result['allowed_origins'])
        conn.close()
        return result
    conn.close()
    return None

def update_api_key_hits(key_id, hits):
    conn = get_db()
    conn.execute('UPDATE api_keys SET hits_used = ? WHERE id = ?', (hits, key_id))
    conn.commit()
    conn.close()

def get_all_api_keys():
    conn = get_db()
    api_keys = conn.execute('SELECT * FROM api_keys').fetchall()
    result = {}
    for key in api_keys:
        key_dict = dict(key)
        key_dict['allowed_origins'] = json.loads(key_dict['allowed_origins'])
        result[key_dict['id']] = key_dict
    conn.close()
    return result

# Stats functions
def get_stats():
    conn = get_db()
    stats = conn.execute('SELECT * FROM stats WHERE id = 1').fetchone()
    daily_stats = conn.execute('SELECT * FROM daily_stats').fetchall()
    hourly_stats = conn.execute('SELECT * FROM hourly_stats').fetchall()
    
    result = dict(stats)
    result['daily_stats'] = {row['date']: {
        'total': row['total'],
        'successful': row['successful'],
        'failed': row['failed']
    } for row in daily_stats}
    
    result['hourly_stats'] = {row['hour']: {
        'total': row['total'],
        'successful': row['successful'],
        'failed': row['failed']
    } for row in hourly_stats}
    
    conn.close()
    return result

def update_stats(success):
    conn = get_db()
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    current_hour = now.strftime('%Y-%m-%d %H')
    
    # Update overall stats
    conn.execute('''UPDATE stats SET 
        total_requests = total_requests + 1,
        successful_requests = successful_requests + ?,
        failed_requests = failed_requests + ?
        WHERE id = 1''', (1 if success else 0, 0 if success else 1))

    # Update or create daily stats
    conn.execute('''INSERT INTO daily_stats (date, total, successful, failed)
        VALUES (?, 1, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
        total = total + 1,
        successful = successful + ?,
        failed = failed + ?''',
        (today, 1 if success else 0, 0 if success else 1,
         1 if success else 0, 0 if success else 1))
    
    # Update or create hourly stats
    conn.execute('''INSERT INTO hourly_stats (hour, total, successful, failed)
        VALUES (?, 1, ?, ?)
        ON CONFLICT(hour) DO UPDATE SET
        total = total + 1,
        successful = successful + ?,
        failed = failed + ?''',
        (current_hour, 1 if success else 0, 0 if success else 1,
         1 if success else 0, 0 if success else 1))
    
    conn.commit()
    conn.close()

# User activity functions
def log_activity(api_key, event_type, details, success, ip_address="N/A"):
    # Skip logging if there's no name in the details
    if not details or not details.get('nameEn'):
        return None
    conn = get_db()
    timestamp = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
    
    c = conn.execute('''INSERT INTO user_activity 
        (timestamp, api_key, event_type, details, success, ip_address)
        VALUES (?, ?, ?, ?, ?, ?)''',
        (timestamp, api_key, event_type, json.dumps(details), success, ip_address))
    
    activity_id = c.lastrowid
    conn.commit()
    conn.close()
    return activity_id

def delete_user_activity(activity_id):
    """Delete a specific user activity by ID"""
    conn = get_db()
    try:
        conn.execute('DELETE FROM user_activity WHERE id = ?', (activity_id,))
        conn.commit()
        success = True
    except Exception as e:
        print(f"Error deleting activity {activity_id}: {e}")
        success = False
    finally:
        conn.close()
    return success

def delete_user_activities(activity_ids=None):
    """Delete multiple user activities by ID or all if None"""
    conn = get_db()
    try:
        if activity_ids:
            # Convert to tuple for SQL IN clause
            placeholders = ','.join('?' for _ in activity_ids)
            conn.execute(f'DELETE FROM user_activity WHERE id IN ({placeholders})', activity_ids)
        else:
            # Delete all activities
            conn.execute('DELETE FROM user_activity')
        conn.commit()
        success = True
    except Exception as e:
        print(f"Error deleting activities: {e}")
        success = False
    finally:
        conn.close()
    return success

def get_user_activities(limit=None):
    conn = get_db()
    query = 'SELECT * FROM user_activity ORDER BY id DESC'
    if limit:
        query += f' LIMIT {limit}'
    
    activities = conn.execute(query).fetchall()
    result = []
    for activity in activities:
        activity_dict = dict(activity)
        activity_dict['details'] = json.loads(activity_dict['details'])
        result.append(activity_dict)
    
    conn.close()
    return result
