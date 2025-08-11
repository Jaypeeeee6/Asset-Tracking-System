import os
import secrets
from flask import Flask
from flask_login import LoginManager
from models.database import get_db_connection, init_db
from models.user import User

def create_app():
    app = Flask(__name__)
    app.config['DATABASE'] = 'production_assets.db'
    # SECURITY: Use environment variable for secret key with fallback
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # Enable debug mode for development
    app.config['DEBUG'] = True
    
    # Disable caching for static files in development
    if app.debug:
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    
    # Add built-in functions to Jinja2 environment
    app.jinja_env.globals.update(max=max, min=min)
    
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
    
    @login_manager.user_loader
    def load_user(user_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, username, role FROM users_auth WHERE id = ?', (user_id,))
        user_data = cur.fetchone()
        conn.close()
        if user_data:
            return User(user_data[0], user_data[1], user_data[2])
        return None
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.assets import assets_bp
    from routes.admin import admin_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(assets_bp, url_prefix='/assets')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Root route redirects to login
    @app.route('/')
    def root():
        from flask import redirect, url_for
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