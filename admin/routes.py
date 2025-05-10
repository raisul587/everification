from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
import json

from admin.forms import LoginForm, APIKeyForm, ChangePasswordForm
from models import key_store, user_store, stats, APIKey, user_activity
from middleware import require_admin
from database import get_user, get_user_by_id

# Create Blueprint
admin = Blueprint('admin', __name__, url_prefix='/admin')

@admin.route('/')
@admin.route('/dashboard')
@require_admin
def dashboard():
    """Admin dashboard page"""
    # Build mapping from api_key to owner_name for fast lookup
    api_key_owner_map = {}
    api_keys = key_store.get_keys().values()
    for k in api_keys:
        key_val = k.key
        owner_val = k.owner_name
        api_key_owner_map[key_val] = owner_val

    stats_data = stats.get_stats()
    
    # Get page parameter for user activity pagination
    page = request.args.get('page', 1, type=int)
    
    # Get user activity data with pagination
    activities, total = user_activity.get_activities(page=page, per_page=10)
    activity_data = {
        'items': activities,
        'total': total,
        'page': page,
        'per_page': 10,
        'pages': (total + 10 - 1) // 10
    }
    
    # Calculate pagination range for template
    start_page = max(1, page - 2)
    end_page = min(activity_data['pages'], page + 2)
    page_range = list(range(start_page, end_page + 1))
    
    # Prepare data for request chart
    daily_labels = []
    daily_data = []
    
    daily_stats = stats_data.get('daily_stats', {})
    sorted_days = sorted(daily_stats.items())
    for day, day_stats in sorted_days[-7:]:  # Get last 7 days
        daily_labels.append(day)
        daily_data.append(day_stats['total'])
    
    # Prepare data for hourly distribution chart
    hours = [str(i).zfill(2) for i in range(24)]
    hourly_counts = [0] * 24
    
    # Count requests by hour
    for hour_str, hour_stats in stats_data.get('hourly_stats', {}).items():
        if ' ' in hour_str:
            try:
                hour = int(hour_str.split(' ')[1])
                if 0 <= hour < 24:
                    hourly_counts[hour] += hour_stats.get('total', 0)
            except (ValueError, IndexError):
                pass
    
    # Calculate active vs inactive keys
    active_keys = sum(1 for k in api_keys if k.active and k.is_valid())
    inactive_keys = len(list(api_keys)) - active_keys
    
    # Calculate usage statistics
    keys_near_limit = sum(1 for k in api_keys if k.hit_limit > 0 and k.hits_used >= 0.8 * k.hit_limit)
    keys_expiring_soon = sum(1 for k in api_keys if k.is_valid() and 
                            datetime.strptime(k.expiry_date.split()[0], "%Y-%m-%d") < 
                            datetime.now() + timedelta(days=7))
    
    return render_template('admin/dashboard.html', 
                           stats=stats_data,
                           api_keys=api_keys,
                           api_key_owner_map=api_key_owner_map,
                           active_keys=active_keys,
                           inactive_keys=inactive_keys,
                           keys_near_limit=keys_near_limit,
                           keys_expiring_soon=keys_expiring_soon,
                           daily_labels=json.dumps(daily_labels),
                           daily_data=json.dumps(daily_data),
                           hourly_labels=json.dumps(hours),
                           hourly_data=json.dumps(hourly_counts),
                           activity_data=activity_data,
                           page_range=page_range)

@admin.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
    if 'user_id' in session:
        user = get_user_by_id(session['user_id'])
        if user and user.get('is_admin'):
            return redirect(url_for('admin.dashboard'))
        session.pop('user_id', None)
    
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        user = get_user(username)
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session.permanent = True
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('admin/login.html', form=form)

@admin.route('/logout')
def logout():
    """Admin logout"""
    session.pop('user_id', None)
    return redirect(url_for('admin.login'))

@admin.route('/keys')
@require_admin
def keys():
    """API keys management page"""
    api_keys = key_store.get_keys().values()
    return render_template('admin/keys.html', api_keys=api_keys)

@admin.route('/keys/add', methods=['GET', 'POST'])
@require_admin
def add_key():
    """Add a new API key"""
    form = APIKeyForm()
    
    if form.validate_on_submit():
        # Create new API key with expiry at end of day
        expiry_datetime = datetime.combine(form.expiry_date.data, datetime.strptime("11:59:59 PM", "%I:%M:%S %p").time())
        expiry_str = expiry_datetime.strftime("%Y-%m-%d %I:%M:%S %p")
        
        # Create new API key
        api_key = APIKey(
            owner_name=form.owner_name.data,
            expiry_date=expiry_str,
            hit_limit=form.hit_limit.data,
            allowed_origins=form.allowed_origins.data.split(),
            active=True  # New keys are active by default
        )
        
        # Add to store
        key_store.add_key(api_key)
        
        flash('API key created successfully', 'success')
        return redirect(url_for('admin.keys'))
    
    return render_template('admin/key_form.html', form=form, title='Add New API Key')

@admin.route('/keys/<key_id>/edit', methods=['GET', 'POST'])
@require_admin
def edit_key(key_id):
    """Edit an existing API key"""
    api_key = key_store.get_keys().get(key_id)
    if not api_key:
        flash('API key not found', 'danger')
        return redirect(url_for('admin.keys'))
    
    form = APIKeyForm(obj=api_key)
    
    if form.validate_on_submit():
        # Update key
        api_key.owner_name = form.owner_name.data
        api_key.expiry_date = form.expiry_date.data.strftime("%Y-%m-%d %I:%M:%S %p")
        api_key.hit_limit = form.hit_limit.data
        api_key.allowed_origins = form.allowed_origins.data.split()
        
        # Save changes
        key_store.add_key(api_key)
        
        flash('API key updated successfully', 'success')
        return redirect(url_for('admin.keys'))
    
    # Pre-fill form fields
    if request.method == 'GET':
        # Convert expiry_date string to datetime for the form
        try:
            form.expiry_date.data = datetime.strptime(api_key.expiry_date, "%Y-%m-%d %I:%M:%S %p")
        except (ValueError, TypeError):
            # If date parsing fails, set to a month from now
            form.expiry_date.data = datetime.now() + timedelta(days=30)
        
        form.allowed_origins.data = ' '.join(api_key.allowed_origins)
    
    return render_template('admin/key_form.html', form=form, title='Edit API Key')

@admin.route('/keys/<key_id>/toggle', methods=['POST'])
@require_admin
def toggle_key(key_id):
    """Toggle an API key's active status"""
    api_key = key_store.get_keys().get(key_id)
    if not api_key:
        return jsonify({'success': False, 'error': 'API key not found'})
    
    api_key.active = not api_key.active
    key_store.add_key(api_key)
    
    return jsonify({
        'success': True,
        'active': api_key.active
    })

@admin.route('/keys/<key_id>/delete', methods=['POST'])
@require_admin
def delete_key(key_id):
    """Delete an API key"""
    if key_store.delete_key(key_id):
        flash('API key deleted successfully', 'success')
    else:
        flash('Error deleting API key', 'danger')
    
    return redirect(url_for('admin.keys'))

@admin.route('/profile', methods=['GET', 'POST'])
@require_admin
def profile():
    """Admin profile page with password change functionality"""
    from database import get_db  # Import get_db here to fix NameError
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        user = get_user_by_id(session['user_id'])
        
        if user and check_password_hash(user['password_hash'], form.current_password.data):
            # Update password in database
            conn = get_db()
            new_password_hash = generate_password_hash(form.new_password.data)
            conn.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                        (new_password_hash, user['id']))
            conn.commit()
            conn.close()
            
            flash('Password changed successfully', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Current password is incorrect', 'danger')
    
    return render_template('admin/profile.html', form=form)

@admin.route('/api/stats')
@require_admin
def api_stats():
    """API endpoint for getting statistics for charts"""
    stats_data = stats.get_stats()
    
    # Prepare data for request chart
    daily_labels = []
    daily_data = []
    
    sorted_days = sorted(stats_data['daily_stats'].items())
    for day, day_stats in sorted_days[-7:]:  # Get last 7 days
        daily_labels.append(day)
        daily_data.append(day_stats['total'])
    
    return jsonify({
        'labels': daily_labels,
        'data': daily_data
    })

@admin.route('/api/activity')
@require_admin
def api_activity():
    """API endpoint for getting user activity with pagination"""
    page = request.args.get('page', 1, type=int)
    activities, total = user_activity.get_activities(page=page, per_page=10)
    return jsonify({
        'items': activities,
        'total': total
    })

@admin.route('/activity/<int:activity_id>/delete', methods=['POST'])
@require_admin
def delete_activity(activity_id):
    """Delete a specific activity"""
    from database import delete_user_activity
    success = delete_user_activity(activity_id)
    return jsonify({'success': success})

@admin.route('/activity/delete-all', methods=['POST'])
@require_admin
def delete_activities():
    """Delete all activities or selected ones"""
    from database import delete_user_activities
    
    # Check if specific IDs were sent
    if request.is_json and request.json.get('ids'):
        activity_ids = request.json.get('ids')
        success = delete_user_activities(activity_ids)
    else:
        # Delete all activities if no IDs specified
        success = delete_user_activities()
        
    return jsonify({'success': success})
