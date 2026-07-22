import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_login import LoginManager
from models.database import get_db_connection, init_db
from models.user import User

load_dotenv(Path(__file__).resolve().parent / '.env')

def create_app():
    app = Flask(__name__)
    app.config['DATABASE'] = 'production_assets.db'
    # SECURITY: Use environment variable for secret key with fallback
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    # Supporting documents (multiple files per asset); keep under ~50 MB per request
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
    
    # Enable debug mode for development
    app.config['DEBUG'] = True
    
    # Disable caching for static files in development
    if app.debug:
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    
    # Add built-in functions to Jinja2 environment
    app.jinja_env.globals.update(max=max, min=min)

    from utils.formatting import format_int, format_omr
    from models.database import format_asset_location_display

    app.jinja_env.filters['fmt_num'] = format_int
    app.jinja_env.filters['fmt_omr'] = format_omr
    app.jinja_env.filters['fmt_location'] = format_asset_location_display

    @app.template_global()
    def has_it_access():
        """Jinja: same checks as ``User.has_it_access()`` (legacy admin-equivalent)."""
        from flask_login import current_user

        if not current_user.is_authenticated:
            return False
        return current_user.has_it_access()
    
    # SECURITY: Add security headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'

    # -------------------------------------------------------------------------
    # TEMPORARY: set DISABLE_AUTH=1 in .env to skip login (auto-login as first
    # IT user, or first user). Auth routes/decorators stay in place — just unset
    # DISABLE_AUTH (or set to 0) to restore normal login. Do not use in production
    # longer than needed.
    # -------------------------------------------------------------------------
    _disable_auth = os.environ.get('DISABLE_AUTH', '').strip().lower() in (
        '1',
        'true',
        'yes',
        'on',
    )
    app.config['DISABLE_AUTH'] = _disable_auth

    @login_manager.user_loader
    def load_user(user_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'SELECT id, email, role, full_name FROM users_auth WHERE id = ?',
            (user_id,),
        )
        user_data = cur.fetchone()
        conn.close()
        if user_data:
            try:
                fn = user_data['full_name'] or ''
            except (KeyError, IndexError):
                fn = ''
            return User(user_data[0], user_data[1], user_data[2], fn)
        return None

    if _disable_auth:
        @login_manager.request_loader
        def _temp_auto_login(_request):
            """TEMPORARY bypass: treat every request as logged-in."""
            conn = get_db_connection()
            cur = conn.cursor()
            from utils.auth_roles import AUTH_ROLE_IT

            cur.execute(
                "SELECT id, email, role, full_name FROM users_auth "
                "WHERE role = ? ORDER BY id ASC LIMIT 1",
                (AUTH_ROLE_IT,),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    'SELECT id, email, role, full_name FROM users_auth '
                    'ORDER BY id ASC LIMIT 1'
                )
                row = cur.fetchone()
            conn.close()
            if not row:
                return None
            try:
                fn = row['full_name'] or ''
            except (KeyError, IndexError):
                fn = ''
            return User(row[0], row[1], row[2], fn)

        @app.before_request
        def _temp_skip_login_page():
            """TEMPORARY: send / and /auth/login straight to the dashboard."""
            from flask import redirect, request, url_for

            if request.endpoint in ('root', 'auth.login'):
                return redirect(url_for('assets.dashboard'))
    # -------------------------------------------------------------------------
    # END TEMPORARY DISABLE_AUTH
    # -------------------------------------------------------------------------
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.assets import assets_bp
    from routes.admin import admin_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(assets_bp, url_prefix='/assets')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Root route redirects to login (or dashboard when DISABLE_AUTH is on)
    @app.route('/')
    def root():
        from flask import redirect, url_for
        if app.config.get('DISABLE_AUTH'):
            return redirect(url_for('assets.dashboard'))
        return redirect(url_for('auth.login'))
    
    # Asset info route at root level for QR code compatibility
    @app.route('/asset/<asset_code>')
    def asset_info_root(asset_code):
        from flask import redirect, url_for
        return redirect(url_for('assets.asset_info', asset_code=asset_code))
    
    # Initialize database
    with app.app_context():
        init_db()
    
    return app 