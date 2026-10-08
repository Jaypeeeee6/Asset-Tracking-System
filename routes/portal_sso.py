"""App Portal SSO + sync for Asset Tracking."""

from __future__ import annotations

import os
import secrets
from functools import wraps

from flask import Blueprint, current_app, jsonify, redirect, request
from flask_login import login_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from models.database import get_db_connection
from models.user import User
from utils.auth import hash_password
from utils.auth_roles import AUTH_ROLES

portal_bp = Blueprint('portal_sso', __name__)


def _portal_url():
    return (os.environ.get('PORTAL_URL') or 'http://localhost:5050').rstrip('/')


def _sso_secret():
    return (os.environ.get('SSO_SECRET') or '').strip()


def _sync_secret():
    return (os.environ.get('PORTAL_SYNC_SECRET') or '').strip()


def _ensure_is_active_column(conn):
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(users_auth)')
    cols = {r[1] for r in cur.fetchall()}
    if 'is_active' not in cols:
        cur.execute('ALTER TABLE users_auth ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1')
        conn.commit()


def require_sync(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = _sync_secret()
        if not expected:
            return jsonify({'error': 'PORTAL_SYNC_SECRET not configured'}), 503
        auth = request.headers.get('Authorization') or ''
        token = auth[7:].strip() if auth.lower().startswith('bearer ') else ''
        if not token or token != expected:
            return jsonify({'error': 'Unauthorized'}), 401
        return view(*args, **kwargs)

    return wrapped


def upsert_user(email: str, name: str, role: str, active: bool = True):
    email_n = (email or '').strip().lower()
    if not email_n or '@' not in email_n:
        raise ValueError('Valid email required')
    if role not in AUTH_ROLES:
        raise ValueError(f'Invalid role: {role}')
    display = (name or email_n.split('@')[0]).strip()
    conn = get_db_connection()
    try:
        _ensure_is_active_column(conn)
        cur = conn.cursor()
        cur.execute('SELECT id FROM users_auth WHERE lower(email) = ?', (email_n,))
        row = cur.fetchone()
        active_i = 1 if active else 0
        if row:
            cur.execute(
                '''
                UPDATE users_auth
                SET full_name = ?, role = ?, email = ?, is_active = ?
                WHERE id = ?
                ''',
                (display, role, email_n, active_i, row[0]),
            )
            user_id = row[0]
        else:
            cur.execute(
                '''
                INSERT INTO users_auth (email, password_hash, encrypted_password, full_name, role, is_active)
                VALUES (?, ?, 'DEPRECATED', ?, ?, ?)
                ''',
                (email_n, hash_password(secrets.token_urlsafe(32)), display, role, active_i),
            )
            user_id = cur.lastrowid
        conn.commit()
        return user_id
    finally:
        conn.close()


@portal_bp.route('/sso/consume')
def sso_consume():
    token = (request.args.get('token') or '').strip()
    if not token:
        return redirect(_portal_url() + '/login')
    secret = _sso_secret()
    if not secret:
        return redirect(_portal_url() + '/login')
    try:
        data = URLSafeTimedSerializer(secret, salt='maa-app-portal-sso').loads(token, max_age=120)
    except (SignatureExpired, BadSignature):
        return redirect(_portal_url() + '/login')
    if not isinstance(data, dict) or (data.get('app') and data.get('app') != 'assets'):
        return redirect(_portal_url() + '/login')
    email = (data.get('email') or '').strip().lower()
    name = (data.get('name') or '').strip()
    role = (data.get('role') or '').strip()
    if not email or not role:
        return redirect(_portal_url() + '/login')
    try:
        user_id = upsert_user(email, name, role, active=True)
    except Exception as exc:
        current_app.logger.error('Assets SSO upsert failed: %s', exc, exc_info=True)
        return redirect(_portal_url() + '/login')
    from flask import url_for

    user = User(user_id, email, role, name or email)
    login_user(user)
    return redirect(url_for('assets.dashboard'))


@portal_bp.route('/internal/portal/users/upsert', methods=['POST'])
@require_sync
def portal_upsert():
    payload = request.get_json(silent=True) or {}
    try:
        user_id = upsert_user(
            payload.get('email'),
            payload.get('name'),
            payload.get('role'),
            active=bool(payload.get('active', True)),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        current_app.logger.error('Assets upsert failed: %s', exc, exc_info=True)
        return jsonify({'error': 'Upsert failed'}), 500
    return jsonify({'ok': True, 'user_id': user_id})


@portal_bp.route('/internal/portal/users/revoke', methods=['POST'])
@require_sync
def portal_revoke():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    conn = get_db_connection()
    try:
        _ensure_is_active_column(conn)
        cur = conn.cursor()
        cur.execute(
            'UPDATE users_auth SET is_active = 0 WHERE lower(email) = ?',
            (email,),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({'ok': True})
