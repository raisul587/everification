from functools import wraps
from flask import request, jsonify, session, redirect, url_for
from models import key_store, stats, user_activity
from database import get_user_by_id, get_user
from urllib.parse import urlparse
def require_api_key(func):
    """Decorator to require an API key for access"""
    @wraps(func)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        # Get the current endpoint
        endpoint = request.endpoint.split('.')[-1] if '.' in request.endpoint else request.endpoint
        
        if not api_key:
            stats.register_request(success=False, endpoint=endpoint)
            log_api_failure(None, 'API key is required')
            return jsonify({
                'success': False,
                'error': 'API key is required'
            }), 401
        
        try:
            # Get the key from the store
            key_obj = key_store.get_key(api_key)
            
            if not key_obj:
                stats.register_request(success=False, endpoint=endpoint)
                log_api_failure(api_key, 'Invalid API key')
                return jsonify({
                    'success': False,
                    'error': 'Invalid API key'
                }), 401
            
            # Check if the key is valid (not expired and within limits)
            if not key_obj.is_valid():
                stats.register_request(success=False, endpoint=endpoint)
                error_message = 'API key has expired or exceeded usage limits'
                if key_obj.hits_used >= key_obj.hit_limit:
                    error_message = 'API key has exceeded usage limits'
                elif not key_obj.active:
                    error_message = 'API key has been deactivated'
                else:
                    error_message = 'API key has expired'
                    
                log_api_failure(api_key, error_message)
                return jsonify({
                    'success': False,
                    'error': error_message
                }), 403
            
            
            # Check if the origin is allowed
            origin_header = request.headers.get('Origin') or request.headers.get('Referer')
            origin_host = None

            if origin_header:
                try:
                    parsed_url = urlparse(origin_header if '://' in origin_header else f'http://{origin_header}')
                    origin_host = parsed_url.hostname
                except Exception as e:
                    origin_host = None

            if key_obj.allowed_origins:
                if origin_host:
                    if origin_host not in key_obj.allowed_origins:
                        stats.register_request(success=False, endpoint=endpoint)
                        error_message = f'Origin {origin_host} is not allowed for this API key'
                        log_api_failure(api_key, error_message)
                        return jsonify({'success': False, 'error': error_message}), 403
                else:
                    # fallback to IP check only if needed
                    client_ip = request.remote_addr
                    if client_ip not in key_obj.allowed_origins:
                        stats.register_request(success=False, endpoint=endpoint)
                        error_message = f'IP {client_ip} is not allowed for this API key'
                        log_api_failure(api_key, error_message)
                        return jsonify({'success': False, 'error': error_message}), 403

            
            # Register request and increment usage counter
            stats.register_request(success=True, endpoint=endpoint)
            key_obj.hits_used += 1
            key_store.add_key(key_obj)
            
            # Log successful request
            event_type = request.endpoint.split('.')[-1] if '.' in request.endpoint else request.endpoint
            details = {
                'endpoint': request.endpoint,
                'method': request.method,
                'path': request.path,
                'remote_addr': request.remote_addr,
                'origin': origin_header or request.remote_addr or 'unknown'
            }
            user_activity.add_activity(api_key, event_type, details, success=True)
            
            return func(*args, **kwargs)
            
        except Exception as e:
            print(f"Error in API key validation: {e}")
            stats.register_request(success=False)
            log_api_failure(api_key, f"Internal server error: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Internal server error'
            }), 500
    
    return decorated_function


def require_admin(func):
    """Decorator to require admin authentication for routes"""
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('admin.login'))
        
        # Check if the user is an admin
        user = get_user_by_id(session['user_id'])
        if not user or not user.get('is_admin'):
            session.pop('user_id', None)  # Clear invalid session
            return redirect(url_for('admin.login'))
        
        return func(*args, **kwargs)
    
    return decorated_function


def log_api_failure(api_key, error_message):
    """Log a failed API request"""
    # Don't log captcha or get_captcha failures
    if request.path not in ['/api/captcha', '/get_captcha']:
        event_type = request.endpoint.split('.')[-1] if '.' in request.endpoint else request.endpoint
        details = {
            'error': error_message,
            'endpoint': request.endpoint,
            'method': request.method,
            'path': request.path,
            'remote_addr': request.remote_addr,
            'origin': request.headers.get('Origin') or request.headers.get('Referer') or request.remote_addr or 'unknown'
        }
        user_activity.add_activity(api_key, event_type, details, success=False)


def init_middleware(app):
    """Initialize middleware for the Flask app"""
    app.before_request(lambda: None)  # Placeholder for future use
