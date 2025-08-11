import sqlite3
import uuid
from flask import current_app

def get_db_connection():
    conn = sqlite3.connect(current_app.config['DATABASE'], timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def generate_asset_code(building, department):
    conn = get_db_connection()
    cur = conn.cursor()
    building_code = building.replace(' ', '').upper()
    department_code = department.replace(' ', '').upper()
    
    # Get all existing asset codes for this building/department (both active and archived)
    cur.execute('SELECT asset_code FROM assets WHERE building=? AND department=? ORDER BY asset_code DESC', (building, department))
    active_codes = cur.fetchall()
    
    # Also get archived asset codes for this building/department
    cur.execute('SELECT asset_code FROM archived_assets WHERE building=? AND department=? ORDER BY asset_code DESC', (building, department))
    archived_codes = cur.fetchall()
    
    conn.close()
    
    # Find the highest number from both active and archived assets
    highest_num = 0
    for row in active_codes + archived_codes:
        if row[0]:
            try:
                # Extract number from asset code (e.g., "MAA-HO-IT-001" -> 1)
                num = int(row[0].split('-')[-1])
                if num > highest_num:
                    highest_num = num
            except (ValueError, IndexError):
                continue
    
    next_num = highest_num + 1
    
    return f"MAA-{building_code}-{department_code}-{next_num:03d}"

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
            price REAL DEFAULT 0.0,
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
    if 'price' not in columns:
        cur.execute('ALTER TABLE assets ADD COLUMN price REAL DEFAULT 0.0')
    
    # Create asset_types table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS asset_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create asset_names table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS asset_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            asset_type_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asset_type_id) REFERENCES asset_types (id),
            UNIQUE(name, asset_type_id)
        )
    ''')
    
    # Create archived_assets table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS archived_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL DEFAULT 0.0,
            owner TEXT NOT NULL,
            building TEXT NOT NULL,
            department TEXT NOT NULL,
            asset_code TEXT,
            qr_random_code TEXT,
            used_status TEXT DEFAULT 'Not Used',
            asset_type TEXT,
            archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            archived_by TEXT,
            archive_reason TEXT
        )
    ''')
    
    # Insert default asset types if they don't exist
    default_asset_types = ['Electronics', 'Furniture', 'Equipment', 'Vehicles', 'Others']
    for asset_type in default_asset_types:
        cur.execute('INSERT OR IGNORE INTO asset_types (name) VALUES (?)', (asset_type,))
    
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