import os
import sqlite3
import uuid
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, send_file, flash, session
import qrcode
from io import BytesIO
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from cryptography.fernet import Fernet
import base64
import hashlib
import secrets

app = Flask(__name__)
app.config['DATABASE'] = 'production_assets.db'
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
BASE_URL = 'http://localhost:5000'  # Change to your local IP if scanning from another device

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

# Password encryption functions
def generate_key():
    """Generate a new encryption key"""
    return Fernet.generate_key()

def encrypt_password(password):
    """Encrypt a password using Fernet"""
    key = get_or_create_key()
    f = Fernet(key)
    return f.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    """Decrypt a password using Fernet"""
    key = get_or_create_key()
    f = Fernet(key)
    return f.decrypt(encrypted_password.encode()).decode()

def get_or_create_key():
    """Get the encryption key from file or create a new one"""
    key_file = 'login_system/encryption_key.key'
    if os.path.exists(key_file):
        with open(key_file, 'rb') as f:
            return f.read()
    else:
        key = generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
        return key

def hash_password(password):
    """Create a hash of the password for verification"""
    return hashlib.sha256(password.encode()).hexdigest()

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

# Database connection
def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'], timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def generate_asset_code(building, department):
    conn = get_db_connection()
    cur = conn.cursor()
    building_code = building.replace(' ', '').upper()
    department_code = department.replace(' ', '').upper()
    cur.execute('SELECT asset_code FROM assets WHERE building=? AND department=? ORDER BY asset_code DESC', (building, department))
    last_code = cur.fetchone()
    conn.close()
    if last_code and last_code[0]:
        try:
            last_num = int(last_code[0].split('-')[-1])
            next_num = last_num + 1
        except:
            next_num = 1
    else:
        next_num = 1
    return f"MAA-{building_code}-{department_code}-{next_num:03d}"

# Initialize DB
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create buildings table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS buildings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create departments table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            building_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (building_id) REFERENCES buildings (id),
            UNIQUE(name, building_id)
        )
    ''')
    
    # Create users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (department_id) REFERENCES departments (id),
            UNIQUE(name, department_id)
        )
    ''')
    
    # Create users_auth table for login authentication
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users_auth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            encrypted_password TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'purchasing')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create assets table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            owner TEXT NOT NULL,
            building TEXT NOT NULL,
            department TEXT NOT NULL,
            asset_code TEXT,
            qr_random_code TEXT,
            used_status TEXT DEFAULT 'Not Used',
            asset_type TEXT
        )
    ''')
    cur.execute("PRAGMA table_info(assets)")
    columns = [row[1] for row in cur.fetchall()]
    if 'qr_random_code' not in columns:
        cur.execute('ALTER TABLE assets ADD COLUMN qr_random_code TEXT')
    if 'used_status' not in columns:
        cur.execute('ALTER TABLE assets ADD COLUMN used_status TEXT DEFAULT "Not Used"')
    if 'asset_type' not in columns:
        cur.execute('ALTER TABLE assets ADD COLUMN asset_type TEXT')
    
    # Note: Default buildings, departments, and users seeding has been removed
    # Users can now add their own buildings, departments, and users as needed
    
    # Note: Default auth users seeding has been removed
    # Users must create their own admin account through the web interface
    
    conn.commit()
    cur.execute("SELECT id FROM assets WHERE qr_random_code IS NULL OR qr_random_code = ''")
    rows = cur.fetchall()
    for row in rows:
        random_code = str(uuid.uuid4())
        cur.execute('UPDATE assets SET qr_random_code=? WHERE id=?', (random_code, row[0]))
    conn.commit()
    conn.close()

ASSETS_PER_PAGE = 10

# Authentication routes
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, username, password_hash, role FROM users_auth WHERE username = ?', (username,))
        user_data = cur.fetchone()
        conn.close()
        
        if user_data and user_data[2] == hash_password(password):
            user = User(user_data[0], user_data[1], user_data[3])
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
@login_required
def forgot_password():
    # Only admin users can access forgot password functionality
    if current_user.role != 'admin':
        flash('Access denied. Only administrators can access password recovery.', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, username, encrypted_password FROM users_auth WHERE username = ?', (username,))
        user_data = cur.fetchone()
        conn.close()
        
        if user_data:
            try:
                decrypted_password = decrypt_password(user_data[2])
                flash(f'Password for user "{username}": {decrypted_password}', 'success')
            except Exception as e:
                flash(f'Error decrypting password: {str(e)}', 'error')
        else:
            flash('User not found', 'error')
    
    return render_template('forgot_password.html')

@app.route('/add_auth_user', methods=['GET', 'POST'])
@login_required
def add_auth_user():
    # Only admin users can add new users
    if current_user.role != 'admin':
        flash('Access denied. Only administrators can add new users.', 'error')
        return redirect(url_for('dashboard'))
    
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
        
        # Create password hash and encrypted password
        password_hash = hash_password(password)
        encrypted_password = encrypt_password(password)
        
        # Insert new user
        try:
            cur.execute('INSERT INTO users_auth (username, password_hash, encrypted_password, role) VALUES (?, ?, ?, ?)', 
                       (username, password_hash, encrypted_password, role))
            conn.commit()
            conn.close()
            flash(f'User "{username}" created successfully with role "{role}".', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            conn.close()
            flash(f'Error creating user: {str(e)}', 'error')
    
    return render_template('add_user.html')

@app.route('/manage_users')
@login_required
def manage_users():
    # Only admin users can manage users
    if current_user.role != 'admin':
        flash('Access denied. Only administrators can manage users.', 'error')
        return redirect(url_for('dashboard'))
    
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

@app.route('/delete_auth_user/<int:user_id>', methods=['POST'])
@login_required
def delete_auth_user(user_id):
    # Only admin users can delete users
    if current_user.role != 'admin':
        flash('Access denied. Only administrators can delete users.', 'error')
        return redirect(url_for('manage_users'))
    
    # Prevent deletion of default admin and purchasing users
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT username FROM users_auth WHERE id = ?', (user_id,))
    user = cur.fetchone()
    
    if not user:
        conn.close()
        flash('User not found.', 'error')
        return redirect(url_for('manage_users'))
    
    username = user[0]
    if username in ['admin', 'purchasing']:
        conn.close()
        flash('Cannot delete default admin or purchasing users.', 'error')
        return redirect(url_for('manage_users'))
    
    # Delete the user
    try:
        cur.execute('DELETE FROM users_auth WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        flash(f'User "{username}" has been deleted successfully.', 'success')
    except Exception as e:
        conn.close()
        flash(f'Error deleting user: {str(e)}', 'error')
    
    return redirect(url_for('manage_users'))

@app.route('/dashboard')
@login_required
def dashboard():
    page = int(request.args.get('page', 1))
    sort_by = request.args.get('sort_by', 'id')
    sort_dir = request.args.get('sort_dir', 'asc')
    building_filter = request.args.get('building', '')
    department_filter = request.args.get('department', '')
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    asset_type_filter = request.args.get('asset_type', '')
    per_page = int(request.args.get('per_page', 10))
    
    offset = (page - 1) * per_page
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Load buildings from database
    cur.execute('SELECT name FROM buildings ORDER BY name')
    buildings = [row[0] for row in cur.fetchall()]
    
    cur.execute('SELECT DISTINCT department FROM assets')
    departments = [row[0] for row in cur.fetchall()]
    
    # Build WHERE clause
    where_clauses = []
    params = []
    
    if building_filter:
        where_clauses.append('building = ?')
        params.append(building_filter)
    if department_filter:
        where_clauses.append('department = ?')
        params.append(department_filter)
    if status_filter:
        where_clauses.append('used_status = ?')
        params.append(status_filter)
    if asset_type_filter:
        where_clauses.append('asset_type = ?')
        params.append(asset_type_filter)
    if search_query:
        search_clauses = [
            'name LIKE ?',
            'owner LIKE ?',
            'asset_code LIKE ?',
            'building LIKE ?',
            'department LIKE ?',
            'asset_type LIKE ?'
        ]
        where_clauses.append(f"({' OR '.join(search_clauses)})")
        search_param = f'%{search_query}%'
        params.extend([search_param] * 6)
    
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
    valid_sort_fields = ['id', 'name', 'quantity', 'owner', 'building', 'department', 'used_status', 'asset_type']
    if sort_by not in valid_sort_fields:
        sort_by = 'id'
    sort_dir = 'desc' if sort_dir == 'desc' else 'asc'
    
    # Get total count
    cur.execute(f'SELECT COUNT(*) FROM assets {where_sql}', params)
    total_assets = cur.fetchone()[0]
    total_pages = (total_assets + per_page - 1) // per_page
    
    # Get paginated results
    cur.execute(f'SELECT * FROM assets {where_sql} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?', params + [per_page, offset])
    assets = [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]
    conn.close()
    
    return render_template('index.html', 
                         assets=assets, 
                         page=page, 
                         total_pages=total_pages, 
                         total_assets=total_assets,
                         per_page=per_page,
                         sort_by=sort_by, 
                         sort_dir=sort_dir, 
                         buildings=buildings, 
                         departments=departments, 
                         building_filter=building_filter, 
                         department_filter=department_filter,
                         asset_type_filter=asset_type_filter)

@app.route('/add', methods=['POST'])
@login_required
def add_asset():
    name = request.form['name']
    asset_type = request.form.get('asset_type', '')
    owner = request.form.get('owner', '')
    building = request.form['building']
    department = request.form['department']
    quantity = int(request.form['quantity'])
    used_status = request.form.get('used_status', 'Not Used')
    no_owner = request.form.get('no_owner') == 'on'
    
    # Handle no owner case
    if no_owner:
        owner = 'No Owner'
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check for existing asset with same name, building, and department
    cur.execute('SELECT id, quantity, asset_code, qr_random_code FROM assets WHERE name=? AND building=? AND department=?', (name, building, department))
    row = cur.fetchone()
    if row:
        new_quantity = row[1] + quantity
        cur.execute('UPDATE assets SET quantity=?, used_status=?, asset_type=?, owner=? WHERE id=?', (new_quantity, used_status, asset_type, owner, row[0]))
        asset_id = row[0]
        asset_code = row[2]
        qr_random_code = row[3]
    else:
        asset_code = generate_asset_code(building, department)
        qr_random_code = str(uuid.uuid4())
        cur.execute('INSERT INTO assets (name, quantity, owner, building, department, asset_code, qr_random_code, used_status, asset_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (name, quantity, owner, building, department, asset_code, qr_random_code, used_status, asset_type))
        asset_id = cur.lastrowid
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/qrcode/<int:asset_id>')
def qrcode_image(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT asset_code FROM assets WHERE id=?', (asset_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row['asset_code']:
        abort(404)
    qr_url = f"{request.host_url.rstrip('/')}/asset/{row['asset_code']}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=2
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/department_qr/<building>/<department>')
def department_qrcode_image(building, department):
    qr_url = f"{request.host_url.rstrip('/')}/department_items/{building}/{department}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=2
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/department_items/<building>/<department>')
def department_items(building, department):
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', '')
    per_page = int(request.args.get('per_page', 10))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Build WHERE clause
    where_clauses = ['building = ?', 'department = ?']
    params = [building, department]
    
    if search_query:
        search_clauses = [
            'name LIKE ?',
            'owner LIKE ?',
            'asset_code LIKE ?'
        ]
        where_clauses.append(f"({' OR '.join(search_clauses)})")
        search_param = f'%{search_query}%'
        params.extend([search_param] * 3)
    
    where_sql = 'WHERE ' + ' AND '.join(where_clauses)
    
    # Get total count
    cur.execute(f'SELECT COUNT(*) FROM assets {where_sql}', params)
    total_assets = cur.fetchone()[0]
    total_pages = (total_assets + per_page - 1) // per_page
    
    # Get paginated results
    offset = (page - 1) * per_page
    cur.execute(f'SELECT * FROM assets {where_sql} ORDER BY name LIMIT ? OFFSET ?', params + [per_page, offset])
    rows = cur.fetchall()
    
    conn.close()
    
    if rows:
        columns = [desc[0] for desc in cur.description]
        assets = [dict(zip(columns, row)) for row in rows]
    else:
        assets = []
    
    return render_template('department_items.html', 
                         assets=assets, 
                         building=building, 
                         department=department,
                         page=page,
                         total_pages=total_pages,
                         total_assets=total_assets,
                         per_page=per_page,
                         search_query=search_query)

@app.route('/delete/<int:asset_id>', methods=['POST'])
@login_required
def delete_asset(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM assets WHERE id=?', (asset_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/qrdata/<int:asset_id>')
def qrdata(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM assets WHERE id=?', (asset_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        columns = [desc[0] for desc in cur.description]
        asset = dict(zip(columns, row))
        return jsonify({
            'asset_code': asset['asset_code'],
            'name': asset['name'],
            'owner': asset['owner'],
            'building': asset['building'],
            'department': asset['department'],
            'quantity': asset['quantity'],
            'used_status': asset.get('used_status', 'Not Used')
        })
    return jsonify({'error': 'Not found'}), 404

@app.route('/update_status/<int:asset_id>', methods=['POST'])
@login_required
def update_status(asset_id):
    used_status = request.form.get('used_status')
    valid_statuses = ['Used', 'Not Used', 'Out of Service']
    if used_status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE assets SET used_status=? WHERE id=?', (used_status, asset_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/bulk_update_status', methods=['POST'])
@login_required
def bulk_update_status():
    asset_ids = request.form.getlist('asset_ids[]')
    used_status = request.form.get('used_status')
    valid_statuses = ['Used', 'Not Used', 'Out of Service']
    
    if not asset_ids or used_status not in valid_statuses:
        return jsonify({'error': 'Invalid data'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    placeholders = ','.join(['?'] * len(asset_ids))
    cur.execute(f'UPDATE assets SET used_status=? WHERE id IN ({placeholders})', [used_status] + asset_ids)
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'updated': len(asset_ids)})

@app.route('/bulk_delete', methods=['POST'])
@login_required
def bulk_delete():
    asset_ids = request.form.getlist('asset_ids[]')
    
    if not asset_ids:
        return jsonify({'error': 'No assets selected'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    placeholders = ','.join(['?'] * len(asset_ids))
    cur.execute(f'DELETE FROM assets WHERE id IN ({placeholders})', asset_ids)
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'deleted': len(asset_ids)})

@app.route('/buildings', methods=['GET'])
def get_buildings():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM buildings ORDER BY name')
    buildings = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    conn.close()
    return jsonify(buildings)

@app.route('/buildings', methods=['POST'])
def add_building():
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Building name is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO buildings (name) VALUES (?)', (name,))
        building_id = cur.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': building_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Building name already exists'}), 400

@app.route('/buildings/<int:building_id>', methods=['PUT'])
def update_building(building_id):
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Building name is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if building exists
        cur.execute('SELECT name FROM buildings WHERE id = ?', (building_id,))
        old_building = cur.fetchone()
        if not old_building:
            conn.close()
            return jsonify({'error': 'Building not found'}), 404
        
        old_name = old_building[0]
        
        # Update building name
        cur.execute('UPDATE buildings SET name = ? WHERE id = ?', (name, building_id))
        
        # Update all assets that reference this building
        cur.execute('UPDATE assets SET building = ? WHERE building = ?', (name, old_name))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': building_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Building name already exists'}), 400

@app.route('/buildings/<int:building_id>', methods=['DELETE'])
def delete_building(building_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if building exists
    cur.execute('SELECT name FROM buildings WHERE id = ?', (building_id,))
    building = cur.fetchone()
    if not building:
        conn.close()
        return jsonify({'error': 'Building not found'}), 404
    
    building_name = building[0]
    
    # Check if building is being used by any assets
    cur.execute('SELECT COUNT(*) FROM assets WHERE building = ?', (building_name,))
    asset_count = cur.fetchone()[0]
    
    if asset_count > 0:
        conn.close()
        return jsonify({'error': f'Cannot delete building. It is being used by {asset_count} asset(s)'}), 400
    
    # Delete the building and its departments
    cur.execute('DELETE FROM departments WHERE building_id = ?', (building_id,))
    cur.execute('DELETE FROM buildings WHERE id = ?', (building_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/departments', methods=['GET'])
def get_departments():
    building_id = request.args.get('building_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if building_id:
        cur.execute('SELECT id, name FROM departments WHERE building_id = ? ORDER BY name', (building_id,))
    else:
        cur.execute('SELECT d.id, d.name, d.building_id, b.name as building_name FROM departments d JOIN buildings b ON d.building_id = b.id ORDER BY b.name, d.name')
    
    if building_id:
        departments = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    else:
        departments = [{'id': row[0], 'name': row[1], 'building_id': row[2], 'building_name': row[3]} for row in cur.fetchall()]
    
    conn.close()
    return jsonify(departments)

@app.route('/departments', methods=['POST'])
def add_department():
    name = request.form.get('name', '').strip()
    building_id = request.form.get('building_id')
    
    if not name:
        return jsonify({'error': 'Department name is required'}), 400
    
    if not building_id:
        return jsonify({'error': 'Building is required'}), 400
    
    try:
        building_id = int(building_id)
    except ValueError:
        return jsonify({'error': 'Invalid building ID'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO departments (name, building_id) VALUES (?, ?)', (name, building_id))
        department_id = cur.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': department_id, 'name': name, 'building_id': building_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Department name already exists for this building'}), 400

@app.route('/departments/<int:department_id>', methods=['PUT'])
def update_department(department_id):
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Department name is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if department exists
        cur.execute('SELECT d.name, b.name FROM departments d JOIN buildings b ON d.building_id = b.id WHERE d.id = ?', (department_id,))
        result = cur.fetchone()
        if not result:
            conn.close()
            return jsonify({'error': 'Department not found'}), 404
        
        old_name, building_name = result
        
        # Update department name
        cur.execute('UPDATE departments SET name = ? WHERE id = ?', (name, department_id))
        
        # Update all assets that reference this department and building
        cur.execute('UPDATE assets SET department = ? WHERE department = ? AND building = ?', (name, old_name, building_name))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': department_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Department name already exists for this building'}), 400

@app.route('/departments/<int:department_id>', methods=['DELETE'])
def delete_department(department_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if department exists
    cur.execute('SELECT d.name, b.name FROM departments d JOIN buildings b ON d.building_id = b.id WHERE d.id = ?', (department_id,))
    result = cur.fetchone()
    if not result:
        conn.close()
        return jsonify({'error': 'Department not found'}), 404
    
    department_name, building_name = result
    
    # Check if department is being used by any assets
    cur.execute('SELECT COUNT(*) FROM assets WHERE department = ? AND building = ?', (department_name, building_name))
    asset_count = cur.fetchone()[0]
    
    if asset_count > 0:
        conn.close()
        return jsonify({'error': f'Cannot delete department. It is being used by {asset_count} asset(s)'}), 400
    
    # Delete the department
    cur.execute('DELETE FROM departments WHERE id = ?', (department_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ===== USER MANAGEMENT API =====

@app.route('/users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    cur = conn.cursor()
    
    department_id = request.args.get('department_id')
    if department_id:
        cur.execute('''
            SELECT u.id, u.name, u.department_id, d.name as department_name, b.name as building_name 
            FROM users u 
            JOIN departments d ON u.department_id = d.id 
            JOIN buildings b ON d.building_id = b.id 
            WHERE u.department_id = ?
            ORDER BY u.name
        ''', (department_id,))
    else:
        cur.execute('''
            SELECT u.id, u.name, u.department_id, d.name as department_name, b.name as building_name 
            FROM users u 
            JOIN departments d ON u.department_id = d.id 
            JOIN buildings b ON d.building_id = b.id 
            ORDER BY b.name, d.name, u.name
        ''')
    
    users = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/users', methods=['POST'])
def add_user():
    data = request.get_json()
    name = data.get('name', '').strip()
    department_id = data.get('department_id')
    
    if not name or not department_id:
        return jsonify({'error': 'Name and department are required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if department exists
    cur.execute('SELECT id FROM departments WHERE id = ?', (department_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({'error': 'Department not found'}), 404
    
    # Check if user already exists in this department
    cur.execute('SELECT id FROM users WHERE name = ? AND department_id = ?', (name, department_id))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'User already exists in this department'}), 409
    
    cur.execute('INSERT INTO users (name, department_id) VALUES (?, ?)', (name, department_id))
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    
    return jsonify({'id': user_id, 'name': name, 'department_id': department_id})

@app.route('/users/bulk', methods=['POST'])
def add_bulk_users():
    data = request.get_json()
    users_data = data.get('users', [])
    department_id = data.get('department_id')
    
    if not users_data or not department_id:
        return jsonify({'error': 'Users list and department are required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if department exists
    cur.execute('SELECT id FROM departments WHERE id = ?', (department_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({'error': 'Department not found'}), 404
    
    added_users = []
    errors = []
    
    for i, user_name in enumerate(users_data):
        name = user_name.strip()
        if not name:
            errors.append(f"User {i+1}: Empty name")
            continue
            
        # Check if user already exists in this department
        cur.execute('SELECT id FROM users WHERE name = ? AND department_id = ?', (name, department_id))
        if cur.fetchone():
            errors.append(f"User {i+1} ({name}): Already exists in this department")
            continue
        
        try:
            cur.execute('INSERT INTO users (name, department_id) VALUES (?, ?)', (name, department_id))
            user_id = cur.lastrowid
            added_users.append({'id': user_id, 'name': name, 'department_id': department_id})
        except Exception as e:
            errors.append(f"User {i+1} ({name}): {str(e)}")
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'added_users': added_users,
        'errors': errors,
        'total_added': len(added_users),
        'total_errors': len(errors)
    })

@app.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.get_json()
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if user exists
    cur.execute('SELECT name, department_id FROM users WHERE id = ?', (user_id,))
    user = cur.fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    old_name = user[0]
    department_id = user[1]
    
    # Check if new name conflicts with existing user in same department
    cur.execute('SELECT id FROM users WHERE name = ? AND department_id = ? AND id != ?', (name, department_id, user_id))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'User name already exists in this department'}), 409
    
    # Update user name
    cur.execute('UPDATE users SET name = ? WHERE id = ?', (name, user_id))
    
    # Update assets that reference the old user name
    cur.execute('SELECT name FROM departments WHERE id = ?', (department_id,))
    dept_result = cur.fetchone()
    if dept_result:
        dept_name = dept_result[0]
        cur.execute('UPDATE assets SET owner = ? WHERE owner = ? AND department = ?', (name, old_name, dept_name))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if user exists and get user info
    cur.execute('''
        SELECT u.name, d.name as department_name 
        FROM users u 
        JOIN departments d ON u.department_id = d.id 
        WHERE u.id = ?
    ''', (user_id,))
    user = cur.fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    user_name = user[0]
    department_name = user[1]
    
    # Check if user is assigned to any assets
    cur.execute('SELECT COUNT(*) FROM assets WHERE owner = ? AND department = ?', (user_name, department_name))
    asset_count = cur.fetchone()[0]
    if asset_count > 0:
        conn.close()
        return jsonify({'error': f'Cannot delete user. {asset_count} asset(s) are assigned to this user.'}), 409
    
    # Delete the user
    cur.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/assets')
def get_assets():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name, building, department, asset_code FROM assets')
    assets = [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]
    conn.close()
    return jsonify(assets)

@app.route('/asset/<asset_code>')
def asset_info(asset_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM assets WHERE asset_code = ?', (asset_code,))
    row = cur.fetchone()
    conn.close()
    if row:
        columns = [desc[0] for desc in cur.description]
        asset = dict(zip(columns, row))
        return render_template('asset_info.html', asset=asset)
    return "Asset not found", 404

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)