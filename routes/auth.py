from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models.user import User
from models.database import get_db_connection
from utils.auth import verify_password, hash_password

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('login.html')
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, username, password_hash, role FROM users_auth WHERE username = ?', (username,))
        user_data = cur.fetchone()
        conn.close()
        
        if user_data and verify_password(password, user_data[2]):
            user = User(user_data[0], user_data[1], user_data[3])
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('assets.dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@auth_bp.route('/dashboard')
@login_required
def dashboard():
    return redirect(url_for('assets.dashboard'))

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/add_auth_user', methods=['GET', 'POST'])
@login_required
def add_auth_user():
    # Only admin users can add new users
    if current_user.role != 'admin':
        flash('Access denied. Only administrators can add new users.', 'error')
        return redirect(url_for('assets.dashboard'))
    
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        role = request.form['role']
        
        # Validation
        if not username or not password or not role:
            flash('All fields are required.', 'error')
            return render_template('add_user.html')
        
        if role not in ['admin', 'purchasing']:
            flash('Invalid role selected.', 'error')
            return render_template('add_user.html')
        
        # Check if username already exists
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id FROM users_auth WHERE username = ?', (username,))
        if cur.fetchone():
            conn.close()
            flash('Username already exists.', 'error')
            return render_template('add_user.html')
        
        # SECURITY: Create secure password hash (no encryption needed)
        password_hash = hash_password(password)
        # No encrypted password needed for new users (deprecated)
        encrypted_password = "DEPRECATED"
        
        # Insert new user
        try:
            cur.execute('INSERT INTO users_auth (username, password_hash, encrypted_password, role) VALUES (?, ?, ?, ?)', 
                       (username, password_hash, encrypted_password, role))
            conn.commit()
            conn.close()
            flash(f'User "{username}" created successfully with role "{role}".', 'success')
            return redirect(url_for('assets.dashboard'))
        except Exception as e:
            conn.close()
            flash(f'Error creating user: {str(e)}', 'error')
    
    return render_template('add_user.html')

@auth_bp.route('/manage_users')
@login_required
def manage_users():
    # Only admin users can manage users
    if current_user.role != 'admin':
        flash('Access denied. Only administrators can manage users.', 'error')
        return redirect(url_for('assets.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT ua.id, ua.username, ua.role, ua.created_at
        FROM users_auth ua
        ORDER BY ua.created_at DESC
    ''')
    users = cur.fetchall()
    conn.close()
    
    return render_template('manage_users.html', users=users)

@auth_bp.route('/delete_auth_user/<int:user_id>', methods=['POST'])
@login_required
def delete_auth_user(user_id):
    # Only admin users can delete users
    if current_user.role != 'admin':
        flash('Access denied. Only administrators can delete users.', 'error')
        return redirect(url_for('auth.manage_users'))
    
    # Prevent deletion of default admin and purchasing users
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT username FROM users_auth WHERE id = ?', (user_id,))
    user = cur.fetchone()
    
    if not user:
        conn.close()
        flash('User not found.', 'error')
        return redirect(url_for('auth.manage_users'))
    
    username = user[0]
    if username in ['admin', 'purchasing']:
        conn.close()
        flash('Cannot delete default admin or purchasing users.', 'error')
        return redirect(url_for('auth.manage_users'))
    
    # Delete the user
    try:
        cur.execute('DELETE FROM users_auth WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        flash(f'User "{username}" has been deleted successfully.', 'success')
    except Exception as e:
        conn.close()
        flash(f'Error deleting user: {str(e)}', 'error')
    
    return redirect(url_for('auth.manage_users')) 