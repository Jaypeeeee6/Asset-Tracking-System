from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models.user import User
from models.database import get_db_connection
from utils.auth import verify_password, hash_password
from utils.auth_roles import (
    AUTH_ROLE_IT,
    AUTH_ROLE_MANAGEMENT,
    AUTH_ROLES,
    is_super_admin_account,
    normalize_full_name,
)

auth_bp = Blueprint('auth', __name__)


def _normalize_email(email):
    return (email or '').strip().lower()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = _normalize_email(request.form.get('email', ''))
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('login.html')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'SELECT id, email, password_hash, role, full_name FROM users_auth WHERE email = ?',
            (email,),
        )
        user_data = cur.fetchone()
        conn.close()

        if user_data and verify_password(password, user_data[2]):
            fn = user_data[4] if len(user_data) > 4 else ''
            user = User(user_data[0], user_data[1], user_data[3], fn or '')
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('assets.dashboard'))
        else:
            flash('Invalid email or password', 'error')

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
    if not current_user.has_it_access():
        flash('Access denied. Only IT users can add new users.', 'error')
        return redirect(url_for('assets.dashboard'))

    if request.method == 'POST':
        email = _normalize_email(request.form.get('email', ''))
        full_name = normalize_full_name(request.form.get('full_name'))
        password = request.form['password']
        role = request.form['role']

        if not email or not password or not role or not full_name:
            flash('Full name, email, password, and role are required.', 'error')
            return render_template('add_user.html')

        if role not in AUTH_ROLES:
            flash('Invalid role selected.', 'error')
            return render_template('add_user.html')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id FROM users_auth WHERE email = ?', (email,))
        if cur.fetchone():
            conn.close()
            flash('Email already exists.', 'error')
            return render_template('add_user.html')

        password_hash = hash_password(password)
        encrypted_password = 'DEPRECATED'

        try:
            cur.execute(
                '''
                INSERT INTO users_auth (email, password_hash, encrypted_password, full_name, role)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (email, password_hash, encrypted_password, full_name, role),
            )
            conn.commit()
            conn.close()
            flash(f'User "{full_name}" ({email}) created successfully with role "{role}".', 'success')
            return redirect(url_for('assets.settings') + '?tab=users')
        except Exception as e:
            conn.close()
            flash(f'Error creating user: {str(e)}', 'error')

    return render_template('add_user.html')


@auth_bp.route('/edit_auth_user/<int:user_id>', methods=['POST'])
@login_required
def edit_auth_user(user_id):
    if not current_user.has_it_access():
        flash('Access denied. Only IT users can edit users.', 'error')
        return redirect(url_for('assets.settings') + '?tab=users')

    email_new = _normalize_email(request.form.get('email') or '')
    full_name_new = normalize_full_name(request.form.get('full_name'))
    role = (request.form.get('role') or '').strip()
    password = (request.form.get('password') or '').strip()

    if role not in AUTH_ROLES:
        flash('Invalid role selected.', 'error')
        return redirect(url_for('assets.settings') + '?tab=users')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'SELECT id, email, full_name, role FROM users_auth WHERE id = ?',
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        flash('User not found.', 'error')
        return redirect(url_for('assets.settings') + '?tab=users')

    old_email = row[1]
    old_full_name = (row[2] or '').strip()
    old_role = row[3]
    protected = is_super_admin_account(old_full_name, old_role)

    if protected:
        full_name_new = 'Super Admin'
        role = AUTH_ROLE_IT

    if not full_name_new:
        conn.close()
        flash('Full name is required.', 'error')
        return redirect(url_for('assets.settings') + '?tab=users')

    if not email_new:
        conn.close()
        flash('Email is required.', 'error')
        return redirect(url_for('assets.settings') + '?tab=users')

    if email_new != old_email:
        cur.execute(
            'SELECT id FROM users_auth WHERE email = ? AND id != ?',
            (email_new, user_id),
        )
        if cur.fetchone():
            conn.close()
            flash('Email already exists.', 'error')
            return redirect(url_for('assets.settings') + '?tab=users')

    if old_role == AUTH_ROLE_IT and role == AUTH_ROLE_MANAGEMENT:
        cur.execute(
            "SELECT COUNT(*) FROM users_auth WHERE role = ? AND id != ?",
            (AUTH_ROLE_IT, user_id),
        )
        if cur.fetchone()[0] == 0:
            conn.close()
            flash('Cannot remove the last IT account.', 'error')
            return redirect(url_for('assets.settings') + '?tab=users')

    try:
        if password:
            password_hash = hash_password(password)
            cur.execute(
                '''
                UPDATE users_auth
                SET email = ?, full_name = ?, role = ?, password_hash = ?, encrypted_password = ?
                WHERE id = ?
                ''',
                (email_new, full_name_new, role, password_hash, 'DEPRECATED', user_id),
            )
        else:
            cur.execute(
                'UPDATE users_auth SET email = ?, full_name = ?, role = ? WHERE id = ?',
                (email_new, full_name_new, role, user_id),
            )
        conn.commit()
    except Exception as e:
        conn.close()
        flash(f'Error updating user: {str(e)}', 'error')
        return redirect(url_for('assets.settings') + '?tab=users')

    conn.close()
    flash(f'User "{full_name_new}" has been updated successfully.', 'success')
    return redirect(url_for('assets.settings') + '?tab=users')


@auth_bp.route('/manage_users')
@login_required
def manage_users():
    if not current_user.has_it_access():
        flash('Access denied. Only IT users can manage users.', 'error')
        return redirect(url_for('assets.dashboard'))
    return redirect(url_for('assets.settings') + '?tab=users')


@auth_bp.route('/delete_auth_user/<int:user_id>', methods=['POST'])
@login_required
def delete_auth_user(user_id):
    if not current_user.has_it_access():
        flash('Access denied. Only IT users can delete users.', 'error')
        return redirect(url_for('assets.settings') + '?tab=users')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT email, full_name, role FROM users_auth WHERE id = ?', (user_id,))
    user = cur.fetchone()

    if not user:
        conn.close()
        flash('User not found.', 'error')
        return redirect(url_for('assets.settings') + '?tab=users')

    email = user[0]
    full_name = (user[1] or '').strip()
    role = user[2]
    if is_super_admin_account(full_name, role):
        conn.close()
        flash('Cannot delete built-in Super Admin (IT) accounts.', 'error')
        return redirect(url_for('assets.settings') + '?tab=users')

    display_name = full_name or email

    try:
        cur.execute('DELETE FROM users_auth WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        flash(f'User "{display_name}" has been deleted successfully.', 'success')
    except Exception as e:
        conn.close()
        flash(f'Error deleting user: {str(e)}', 'error')

    return redirect(url_for('assets.settings') + '?tab=users')
