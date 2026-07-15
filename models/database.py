import sqlite3
import uuid
from flask import current_app

from utils.auth_roles import AUTH_ROLE_IT, AUTH_ROLE_MANAGEMENT

def get_db_connection():
    conn = sqlite3.connect(current_app.config['DATABASE'], timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Canonical branch label stored on assets for office-venue rows (must match admin/JS).
OFFICE_BRANCH_LABEL = 'Office'


def _asset_code_prefix(cur, branch, department):
    """Restaurant: branch_code from DB. Office: department name."""
    if branch == OFFICE_BRANCH_LABEL:
        return (department or '').strip()
    cur.execute('SELECT branch_code FROM branches WHERE name = ?', (branch,))
    row = cur.fetchone()
    if row and row[0] and str(row[0]).strip():
        return str(row[0]).strip().upper()
    return (branch or '').replace(' ', '').upper()


def _asset_code_rows_for_scope(cur, branch, department):
    """Active + archived asset codes for sequence calculation."""
    if branch == OFFICE_BRANCH_LABEL:
        cur.execute(
            'SELECT asset_code FROM assets WHERE branch=? AND department=?',
            (branch, department),
        )
        active = cur.fetchall()
        cur.execute(
            'SELECT asset_code FROM archived_assets WHERE branch=? AND department=?',
            (branch, department),
        )
    else:
        cur.execute('SELECT asset_code FROM assets WHERE branch=?', (branch,))
        active = cur.fetchall()
        cur.execute('SELECT asset_code FROM archived_assets WHERE branch=?', (branch,))
    return active + cur.fetchall()


def _sequence_from_asset_code(code, prefix):
    if not code:
        return None
    marker = f'{prefix}-'
    if code.upper().startswith(marker.upper()):
        suffix = code[len(marker):]
        if suffix.isdigit():
            return int(suffix)
    try:
        last = code.rsplit('-', 1)[-1]
        if last.isdigit():
            return int(last)
    except (ValueError, IndexError):
        pass
    return None


def _highest_asset_sequence(cur, branch, department, prefix):
    highest = 0
    for row in _asset_code_rows_for_scope(cur, branch, department):
        num = _sequence_from_asset_code(row[0], prefix)
        if num is not None and num > highest:
            highest = num
    return highest


def allocate_asset_codes(cur, branch, department, count):
    """Return the next `count` asset codes (restaurant: [BranchCode]-0001; office: [Dept]-0001)."""
    if count < 1:
        return []
    prefix = _asset_code_prefix(cur, branch, department)
    highest = _highest_asset_sequence(cur, branch, department, prefix)
    return [f'{prefix}-{highest + i + 1:04d}' for i in range(count)]


def generate_asset_code(branch, department, cur=None):
    conn = None
    if cur is None:
        conn = get_db_connection()
        cur = conn.cursor()
    codes = allocate_asset_codes(cur, branch, department, 1)
    if conn is not None:
        conn.close()
    return codes[0]


def _migrate_departments_nullable_branch_id(cur):
    """Allow office-only departments (no branch). Rebuild table if branch_id was NOT NULL."""
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='departments'")
    if not cur.fetchone():
        return
    cur.execute('PRAGMA table_info(departments)')
    cols = cur.fetchall()
    branch_row = next((c for c in cols if c[1] == 'branch_id'), None)
    if not branch_row or branch_row[3] == 0:
        return
    cur.executescript(
        '''
        PRAGMA foreign_keys=OFF;
        CREATE TABLE departments_rebuild (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            branch_id INTEGER REFERENCES branches(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO departments_rebuild (id, name, branch_id, created_at)
            SELECT id, name, branch_id, created_at FROM departments;
        DROP TABLE departments;
        ALTER TABLE departments_rebuild RENAME TO departments;
        PRAGMA foreign_keys=ON;
        '''
    )


def _ensure_department_venue_indexes(cur):
    """Uniqueness: office departments unique by name; branch departments unique by (name, branch_id)."""
    for stmt, err_note in (
        (
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_department_office_name '
            'ON departments(name) WHERE branch_id IS NULL',
            'office department name index',
        ),
        (
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_department_branch_pair '
            'ON departments(name, branch_id) WHERE branch_id IS NOT NULL',
            'branch department pair index',
        ),
    ):
        try:
            cur.execute(stmt)
        except sqlite3.OperationalError:
            pass


# Canonical placeholder department for every restaurant branch (assets / owners without section splits).
RESTAURANT_DEFAULT_DEPARTMENT_NAME = 'Restaurant'


def format_asset_location_display(branch, department):
    """Single location label for lists: hide Office/Restaurant venue placeholders."""
    branch = (branch or '').strip()
    department = (department or '').strip()
    if branch == OFFICE_BRANCH_LABEL:
        return department or '—'
    if not department or department == RESTAURANT_DEFAULT_DEPARTMENT_NAME:
        return branch or '—'
    return f'{branch} / {department}'


def ensure_restaurant_default_department_for_branch(cur, branch_id):
    """Ensure branch has a default 'Restaurant' department row (used when users only pick brand + branch)."""
    cur.execute(
        'SELECT 1 FROM departments WHERE branch_id = ? AND name = ?',
        (branch_id, RESTAURANT_DEFAULT_DEPARTMENT_NAME),
    )
    if cur.fetchone():
        return
    cur.execute(
        'INSERT INTO departments (name, branch_id) VALUES (?, ?)',
        (RESTAURANT_DEFAULT_DEPARTMENT_NAME, branch_id),
    )


def _migrate_asset_types_for_venue(cur):
    """Add for_venue (restaurant|office) with UNIQUE(name, for_venue)."""
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='asset_types'")
    if not cur.fetchone():
        return
    cur.execute('PRAGMA table_info(asset_types)')
    if 'for_venue' in [r[1] for r in cur.fetchall()]:
        return
    cur.executescript(
        '''
        PRAGMA foreign_keys=OFF;
        CREATE TABLE asset_types_rebuild (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            for_venue TEXT NOT NULL DEFAULT 'restaurant' CHECK (for_venue IN ('restaurant','office')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, for_venue)
        );
        INSERT INTO asset_types_rebuild (id, name, for_venue, created_at)
            SELECT id, name, 'restaurant', created_at FROM asset_types;
        DROP TABLE asset_types;
        ALTER TABLE asset_types_rebuild RENAME TO asset_types;
        PRAGMA foreign_keys=ON;
        '''
    )
    cur.execute('SELECT MAX(id) FROM asset_types')
    mx = cur.fetchone()[0]
    if mx:
        cur.execute("DELETE FROM sqlite_sequence WHERE name='asset_types'")
        cur.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('asset_types', ?)", (mx,))


def _migrate_asset_specifications(cur):
    """Specification field templates per asset name and values per asset instance."""
    cur.execute('''
        CREATE TABLE IF NOT EXISTS asset_name_spec_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_name_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asset_name_id) REFERENCES asset_names (id) ON DELETE CASCADE,
            UNIQUE(asset_name_id, label)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS asset_spec_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            spec_field_id INTEGER NOT NULL,
            value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asset_id) REFERENCES assets (id) ON DELETE CASCADE,
            FOREIGN KEY (spec_field_id) REFERENCES asset_name_spec_fields (id) ON DELETE CASCADE,
            UNIQUE(asset_id, spec_field_id)
        )
    ''')


def _migrate_asset_types_allow_both(cur):
    """Allow for_venue='both' (all restaurants and all office departments in one row)."""
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='asset_types'")
    if not cur.fetchone():
        return
    cur.execute('PRAGMA table_info(asset_types)')
    if 'for_venue' not in [r[1] for r in cur.fetchall()]:
        return
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='asset_types'")
    create_sql = (cur.fetchone() or [None])[0] or ''
    if "'both'" in create_sql:
        return
    cur.executescript(
        '''
        PRAGMA foreign_keys=OFF;
        CREATE TABLE asset_types_rebuild (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            for_venue TEXT NOT NULL DEFAULT 'restaurant'
                CHECK (for_venue IN ('restaurant','office','both')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, for_venue)
        );
        INSERT INTO asset_types_rebuild (id, name, for_venue, created_at)
            SELECT id, name, for_venue, created_at FROM asset_types;
        DROP TABLE asset_types;
        ALTER TABLE asset_types_rebuild RENAME TO asset_types;
        PRAGMA foreign_keys=ON;
        '''
    )
    cur.execute('SELECT MAX(id) FROM asset_types')
    mx = cur.fetchone()[0]
    if mx:
        cur.execute("DELETE FROM sqlite_sequence WHERE name='asset_types'")
        cur.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('asset_types', ?)", (mx,))


def asset_type_for_venue_matches(for_venue, asset_venue):
    """True when an asset type's scope includes the asset's restaurant/office venue."""
    fv = (for_venue or 'restaurant').strip().lower()
    v = (asset_venue or 'restaurant').strip().lower()
    if fv == 'both':
        return v in ('restaurant', 'office')
    return fv == v


def _migrate_legacy_building_schema(cur):
    """Rename legacy building* tables/columns to branch* for existing SQLite databases."""
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='buildings'")
    if cur.fetchone():
        cur.execute('ALTER TABLE buildings RENAME TO branches')

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='departments'")
    if cur.fetchone():
        cur.execute('PRAGMA table_info(departments)')
        dept_cols = [row[1] for row in cur.fetchall()]
        if 'building_id' in dept_cols and 'branch_id' not in dept_cols:
            cur.execute('ALTER TABLE departments RENAME COLUMN building_id TO branch_id')

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assets'")
    if cur.fetchone():
        cur.execute('PRAGMA table_info(assets)')
        asset_cols = [row[1] for row in cur.fetchall()]
        if 'building' in asset_cols and 'branch' not in asset_cols:
            cur.execute('ALTER TABLE assets RENAME COLUMN building TO branch')

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='archived_assets'")
    if cur.fetchone():
        cur.execute('PRAGMA table_info(archived_assets)')
        arch_cols = [row[1] for row in cur.fetchall()]
        if 'building' in arch_cols and 'branch' not in arch_cols:
            cur.execute('ALTER TABLE archived_assets RENAME COLUMN building TO branch')


def _migrate_users_employee_id(conn):
    """Add employee_id column to users (employees roster)."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cur.fetchone():
        return
    cur.execute('PRAGMA table_info(users)')
    col_names = [row[1] for row in cur.fetchall()]
    if 'employee_id' not in col_names:
        cur.execute('ALTER TABLE users ADD COLUMN employee_id TEXT')
        cur.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_users_employee_id '
            'ON users(employee_id) WHERE employee_id IS NOT NULL'
        )
        conn.commit()


def _migrate_users_contact_info(conn):
    """Add mobile and email columns to users (employees roster)."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cur.fetchone():
        return
    cur.execute('PRAGMA table_info(users)')
    col_names = [row[1] for row in cur.fetchall()]
    if 'mobile' not in col_names:
        cur.execute('ALTER TABLE users ADD COLUMN mobile TEXT')
    if 'email' not in col_names:
        cur.execute('ALTER TABLE users ADD COLUMN email TEXT')
    conn.commit()


def _migrate_users_auth_username_to_email(conn):
    """Rename legacy users_auth.username column to email."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users_auth'")
    if not cur.fetchone():
        return
    cur.execute('PRAGMA table_info(users_auth)')
    col_names = [row[1] for row in cur.fetchall()]
    if 'username' in col_names and 'email' not in col_names:
        cur.execute('ALTER TABLE users_auth RENAME COLUMN username TO email')
        conn.commit()


def _migrate_users_auth_schema(conn):
    """Add full_name, migrate admin/purchasing roles to IT/Management, and rebuild table when CHECK blocks updates."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users_auth'")
    if not cur.fetchone():
        return
    cur.execute('PRAGMA table_info(users_auth)')
    col_names = [row[1] for row in cur.fetchall()]
    has_full_name = 'full_name' in col_names
    cur.execute("SELECT COUNT(*) FROM users_auth WHERE role IN ('admin', 'purchasing')")
    needs_role_migration = cur.fetchone()[0] > 0
    if has_full_name and not needs_role_migration:
        return

    cur.execute('SELECT * FROM users_auth')
    rows = list(cur.fetchall())
    cur.execute('DROP TABLE users_auth')
    cur.execute(
        '''
        CREATE TABLE users_auth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            encrypted_password TEXT NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL CHECK (role IN ('IT', 'Management')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    for r in rows:
        email = r['email'] if 'email' in r.keys() else r['username']
        old_role = r['role']
        new_role = {'admin': AUTH_ROLE_IT, 'purchasing': AUTH_ROLE_MANAGEMENT}.get(old_role, old_role)
        if new_role not in (AUTH_ROLE_IT, AUTH_ROLE_MANAGEMENT):
            new_role = AUTH_ROLE_MANAGEMENT
        if has_full_name:
            fn = (r['full_name'] or '').strip()
        else:
            fn = ''
        if not fn and str(email).lower() == 'admin' and old_role == 'admin':
            fn = 'Super Admin'
        elif not fn:
            fn = str(email).strip().title() if str(email).strip() else 'User'
        cur.execute(
            '''
            INSERT INTO users_auth
            (id, email, password_hash, encrypted_password, full_name, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                r['id'],
                email,
                r['password_hash'],
                r['encrypted_password'],
                fn,
                new_role,
                r['created_at'],
            ),
        )
    cur.execute('SELECT MAX(id) FROM users_auth')
    mx = cur.fetchone()[0]
    if mx:
        cur.execute("DELETE FROM sqlite_sequence WHERE name='users_auth'")
        cur.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('users_auth', ?)", (mx,))
    conn.commit()


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    _migrate_legacy_building_schema(cur)
    conn.commit()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create branches table (replaces legacy "buildings")
    cur.execute('''
        CREATE TABLE IF NOT EXISTS branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('PRAGMA table_info(branches)')
    _branch_col_names = [row[1] for row in cur.fetchall()]
    if 'brand_id' not in _branch_col_names:
        cur.execute('ALTER TABLE branches ADD COLUMN brand_id INTEGER REFERENCES brands(id)')
    if 'branch_code' not in _branch_col_names:
        cur.execute('ALTER TABLE branches ADD COLUMN branch_code TEXT')
    cur.execute('SELECT COUNT(*) FROM branches WHERE brand_id IS NULL')
    if cur.fetchone()[0] > 0:
        cur.execute("INSERT OR IGNORE INTO brands (name) VALUES ('Default')")
        cur.execute("SELECT id FROM brands WHERE name = 'Default' LIMIT 1")
        _default_brand = cur.fetchone()
        if _default_brand:
            cur.execute(
                'UPDATE branches SET brand_id = ? WHERE brand_id IS NULL',
                (_default_brand[0],),
            )
    
    # Create departments table (branch_id NULL = office department)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            branch_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (branch_id) REFERENCES branches (id)
        )
    ''')
    _migrate_departments_nullable_branch_id(cur)
    _ensure_department_venue_indexes(cur)
    cur.execute('SELECT id FROM branches')
    for _br in cur.fetchall():
        ensure_restaurant_default_department_for_branch(cur, _br[0])
    
    # Create users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            employee_id TEXT,
            department_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (department_id) REFERENCES departments (id),
            UNIQUE(name, department_id)
        )
    ''')
    _migrate_users_employee_id(conn)
    _migrate_users_contact_info(conn)
    
    # Create users_auth table for login authentication
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users_auth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            encrypted_password TEXT NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL CHECK (role IN ('IT', 'Management')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    _migrate_users_auth_schema(conn)
    _migrate_users_auth_username_to_email(conn)
    
    # Create assets table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL DEFAULT 0.0,
            owner TEXT NOT NULL,
            branch TEXT NOT NULL,
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
    
    # Create asset_types table (for_venue added via migration on legacy DBs)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS asset_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    _migrate_asset_types_for_venue(cur)
    _migrate_asset_types_allow_both(cur)
    
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
    _migrate_asset_specifications(cur)

    # Create archived_assets table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS archived_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL DEFAULT 0.0,
            owner TEXT NOT NULL,
            branch TEXT NOT NULL,
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
    
    # Insert default asset types if they don't exist (restaurant venue)
    default_asset_types = ['Electronics', 'Furniture', 'Equipment', 'Vehicles', 'Others']
    for asset_type in default_asset_types:
        cur.execute(
            "INSERT OR IGNORE INTO asset_types (name, for_venue) VALUES (?, 'restaurant')",
            (asset_type,),
        )
    
    # Note: Default branches, departments, and users seeding has been removed
    # Users can now add their own branches, departments, and users as needed
    
    # Note: Default auth users seeding has been removed
    # IT users manage login accounts from Settings
    
    conn.commit()
    cur.execute("SELECT id FROM assets WHERE qr_random_code IS NULL OR qr_random_code = ''")
    rows = cur.fetchall()
    for row in rows:
        random_code = str(uuid.uuid4())
        cur.execute('UPDATE assets SET qr_random_code=? WHERE id=?', (random_code, row[0]))
    conn.commit()

    # QR label layouts: authoritative mm geometry for the application.
    #
    # The software owns label dimensions and every anchor (QR top-left & size; text anchors & tops; optional
    # print_offset_*). The print pipeline renders those as CSS mm + @page of the same outer size—not the printer
    # deciding where the QR sits. Multiple presets supported; production uses preset_key label_2x2 (2"×2" stock).
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS qr_label_layouts (
            preset_key TEXT PRIMARY KEY,
            label_width_mm REAL NOT NULL,
            label_height_mm REAL NOT NULL,
            qr_x_mm REAL NOT NULL,
            qr_y_mm REAL NOT NULL,
            qr_size_mm REAL NOT NULL,
            qr_reference_px INTEGER NOT NULL DEFAULT 80,
            primary_text_x_mm REAL NOT NULL,
            primary_text_y_mm REAL NOT NULL,
            secondary_text_x_mm REAL NOT NULL,
            secondary_text_y_mm REAL NOT NULL,
            primary_font_pt REAL NOT NULL DEFAULT 10,
            secondary_font_pt REAL NOT NULL DEFAULT 9,
            primary_text_align TEXT NOT NULL DEFAULT 'center',
            secondary_text_align TEXT NOT NULL DEFAULT 'center',
            primary_text_max_width_mm REAL,
            secondary_text_max_width_mm REAL,
            print_offset_qr_x_mm REAL DEFAULT 0,
            print_offset_qr_y_mm REAL DEFAULT 0,
            print_offset_primary_x_mm REAL DEFAULT 0,
            print_offset_primary_y_mm REAL DEFAULT 0,
            print_offset_secondary_x_mm REAL DEFAULT 0,
            print_offset_secondary_y_mm REAL DEFAULT 0
        )
        '''
    )

    # label_2x2: asset code (primary) above QR, item name (secondary) below; tight gaps; group left.
    # Routes pass (asset_code, name) as (primary, secondary).
    _lbl2_qr_x = 3.38
    _lbl2_qr_y = 5.95
    _lbl2_qr_size = 14.0
    _lbl2_qr_center_x = _lbl2_qr_x + (_lbl2_qr_size / 2)
    _lbl2_primary_text_y = 2.35
    _lbl2_secondary_text_y = _lbl2_qr_y + _lbl2_qr_size + 0.35

    # 50.8 mm === 2 inch; single layout for all QR prints (QR kept smaller via qr_size_mm)
    defaults = (
        (
            'label_2x2',
            50.8,
            50.8,
            _lbl2_qr_x,
            _lbl2_qr_y,
            _lbl2_qr_size,
            80,
            _lbl2_qr_center_x,
            _lbl2_primary_text_y,
            _lbl2_qr_center_x,
            _lbl2_secondary_text_y,
            7.0,
            6.0,
            'center',
            'center',
            22.0,
            22.0,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
    )
    cur.executemany(
        '''
        INSERT OR IGNORE INTO qr_label_layouts (
            preset_key, label_width_mm, label_height_mm, qr_x_mm, qr_y_mm, qr_size_mm, qr_reference_px,
            primary_text_x_mm, primary_text_y_mm, secondary_text_x_mm, secondary_text_y_mm,
            primary_font_pt, secondary_font_pt, primary_text_align, secondary_text_align,
            primary_text_max_width_mm, secondary_text_max_width_mm,
            print_offset_qr_x_mm, print_offset_qr_y_mm,
            print_offset_primary_x_mm, print_offset_primary_y_mm,
            print_offset_secondary_x_mm, print_offset_secondary_y_mm
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        )
        ''',
        defaults,
    )
    # Refresh prior shipped defaults (32 mm or 20 mm QR) to smaller, left-shifted QR + text
    # aligned to QR centerline; leaves custom layouts (other qr_size_mm) unchanged.
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_x_mm = ?,
            qr_y_mm = ?,
            qr_size_mm = ?,
            primary_text_x_mm = ?,
            primary_text_y_mm = ?,
            secondary_text_x_mm = ?,
            secondary_text_y_mm = ?,
            primary_font_pt = ?,
            secondary_font_pt = ?,
            primary_text_max_width_mm = ?,
            secondary_text_max_width_mm = ?
        WHERE preset_key = 'label_2x2'
          AND (
            ABS(qr_size_mm - 32.0) < 0.06
            OR ABS(qr_size_mm - 20.0) < 0.06
          )
        ''',
        (
            _lbl2_qr_x,
            _lbl2_qr_y,
            _lbl2_qr_size,
            _lbl2_qr_center_x,
            _lbl2_primary_text_y,
            _lbl2_qr_center_x,
            _lbl2_secondary_text_y,
            7.0,
            6.0,
            22.0,
            22.0,
        ),
    )
    # 17 mm era at qr_x = 11.8: text still anchored to label center (~25.4 mm).
    _legacy_qr172_x = 11.8
    _legacy_qr172_center_x = _legacy_qr172_x + (17.0 / 2)
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            primary_text_x_mm = ?,
            secondary_text_x_mm = ?,
            primary_text_max_width_mm = 22.0,
            secondary_text_max_width_mm = 22.0
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_x_mm - ?) < 0.12
          AND ABS(qr_size_mm - 17.0) < 0.12
          AND ABS(primary_text_x_mm - 25.4) < 0.2
        ''',
        (_legacy_qr172_center_x, _legacy_qr172_center_x, _legacy_qr172_x),
    )
    # Move off last shipped 17 mm presets (qr_x ~11.8 or ~9.8) onto 14 mm + stacked text + left group.
    _prev_ship_qr17_x_a = 11.8
    _prev_ship_qr17_x_b = 9.8
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_x_mm = ?,
            qr_y_mm = ?,
            qr_size_mm = ?,
            primary_text_x_mm = ?,
            primary_text_y_mm = ?,
            secondary_text_x_mm = ?,
            secondary_text_y_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - 17.0) < 0.12
          AND (
                ABS(qr_x_mm - ?) < 0.15
             OR ABS(qr_x_mm - ?) < 0.15
          )
        ''',
        (
            _lbl2_qr_x,
            _lbl2_qr_y,
            _lbl2_qr_size,
            _lbl2_qr_center_x,
            _lbl2_primary_text_y,
            _lbl2_qr_center_x,
            _lbl2_secondary_text_y,
            _prev_ship_qr17_x_a,
            _prev_ship_qr17_x_b,
        ),
    )
    # 14 mm era with primary text below the QR (~28 mm y); bring in current stack + left nudge.
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_x_mm = ?,
            qr_y_mm = ?,
            primary_text_x_mm = ?,
            primary_text_y_mm = ?,
            secondary_text_x_mm = ?,
            secondary_text_y_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - ?) < 0.15
          AND primary_text_y_mm > 12.0
        ''',
        (
            _lbl2_qr_x,
            _lbl2_qr_y,
            _lbl2_qr_center_x,
            _lbl2_primary_text_y,
            _lbl2_qr_center_x,
            _lbl2_secondary_text_y,
            _lbl2_qr_size,
        ),
    )
    # Prior stacked ship (6 mm x, 7 mm qr_y, code at 3 mm, name at ~21.55 mm) → tighter gaps + further left.
    _prev_stack_qr_x = 6.0
    _prev_stack_qr_y = 7.0
    _prev_stack_primary_y = 3.0
    _prev_stack_secondary_y = 21.55
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_x_mm = ?,
            qr_y_mm = ?,
            primary_text_x_mm = ?,
            primary_text_y_mm = ?,
            secondary_text_x_mm = ?,
            secondary_text_y_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - ?) < 0.15
          AND ABS(qr_x_mm - ?) < 0.25
          AND ABS(qr_y_mm - ?) < 0.4
          AND ABS(primary_text_y_mm - ?) < 0.45
          AND ABS(secondary_text_y_mm - ?) < 0.5
        ''',
        (
            _lbl2_qr_x,
            _lbl2_qr_y,
            _lbl2_qr_center_x,
            _lbl2_primary_text_y,
            _lbl2_qr_center_x,
            _lbl2_secondary_text_y,
            _lbl2_qr_size,
            _prev_stack_qr_x,
            _prev_stack_qr_y,
            _prev_stack_primary_y,
            _prev_stack_secondary_y,
        ),
    )
    # 14 mm stack already applied but qr_x still on prior 7.4 mm column — finish left + y alignment.
    _straggler_lbl2_qr_x = 7.4
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_x_mm = ?,
            qr_y_mm = ?,
            primary_text_x_mm = ?,
            primary_text_y_mm = ?,
            secondary_text_x_mm = ?,
            secondary_text_y_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - ?) < 0.15
          AND ABS(qr_x_mm - ?) < 0.2
          AND primary_text_y_mm <= 12.0
        ''',
        (
            _lbl2_qr_x,
            _lbl2_qr_y,
            _lbl2_qr_center_x,
            _lbl2_primary_text_y,
            _lbl2_qr_center_x,
            _lbl2_secondary_text_y,
            _lbl2_qr_size,
            _straggler_lbl2_qr_x,
        ),
    )
    # Prior ship at qr_x 5.6 mm — nudge QR + centred text anchors left again (y unchanged).
    _prior_ship_lbl2_x = 5.6
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_x_mm = ?,
            primary_text_x_mm = ?,
            secondary_text_x_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - ?) < 0.15
          AND ABS(qr_x_mm - ?) < 0.22
          AND ABS(qr_y_mm - ?) < 0.45
          AND ABS(primary_text_y_mm - ?) < 0.5
          AND ABS(secondary_text_y_mm - ?) < 0.55
        ''',
        (
            _lbl2_qr_x,
            _lbl2_qr_center_x,
            _lbl2_qr_center_x,
            _lbl2_qr_size,
            _prior_ship_lbl2_x,
            _lbl2_qr_y,
            _lbl2_primary_text_y,
            _lbl2_secondary_text_y,
        ),
    )
    # Shipped qr_x 5.0 mm — move QR + text anchors slightly further left (same stacked layout).
    _ship_lbl2_qr_x_5_0 = 5.0
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_x_mm = ?,
            primary_text_x_mm = ?,
            secondary_text_x_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - ?) < 0.15
          AND ABS(qr_x_mm - ?) < 0.25
        ''',
        (
            _lbl2_qr_x,
            _lbl2_qr_center_x,
            _lbl2_qr_center_x,
            _lbl2_qr_size,
            _ship_lbl2_qr_x_5_0,
        ),
    )
    # One-step left nudge for older ships (4.2 / 3.8 / 3.5 mm) onto current _lbl2_qr_x (x only).
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_x_mm = ?,
            primary_text_x_mm = ?,
            secondary_text_x_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - ?) < 0.15
          AND (
                ABS(qr_x_mm - 4.2) < 0.28
             OR ABS(qr_x_mm - 3.8) < 0.22
             OR ABS(qr_x_mm - 3.55) < 0.18
             OR ABS(qr_x_mm - 3.5) < 0.15
          )
        ''',
        (
            _lbl2_qr_x,
            _lbl2_qr_center_x,
            _lbl2_qr_center_x,
            _lbl2_qr_size,
        ),
    )
    # Normalize vertical stack for 14 mm preset at current qr_x (fixes legacy qr_y 6.7 / 7.4 mm, etc.).
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_y_mm = ?,
            primary_text_y_mm = ?,
            secondary_text_y_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - ?) < 0.15
          AND ABS(qr_x_mm - ?) < 0.25
          AND (
                ABS(qr_y_mm - 6.7) < 0.45
             OR ABS(qr_y_mm - 7.4) < 0.35
          )
        ''',
        (
            _lbl2_qr_y,
            _lbl2_primary_text_y,
            _lbl2_secondary_text_y,
            _lbl2_qr_size,
            _lbl2_qr_x,
        ),
    )
    # Slight upward nudge for current 14 mm stack (was qr_y 6.25 mm).
    _prev_lbl2_qr_y_ship = 6.25
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_y_mm = ?,
            secondary_text_y_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - ?) < 0.15
          AND ABS(qr_x_mm - ?) < 0.25
          AND ABS(qr_y_mm - ?) < 0.12
        ''',
        (
            _lbl2_qr_y,
            _lbl2_secondary_text_y,
            _lbl2_qr_size,
            _lbl2_qr_x,
            _prev_lbl2_qr_y_ship,
        ),
    )
    # Slight left nudge for current 14 mm stack (was qr_x 3.68 mm).
    _prev_lbl2_qr_x_ship = 3.68
    cur.execute(
        '''
        UPDATE qr_label_layouts SET
            qr_x_mm = ?,
            primary_text_x_mm = ?,
            secondary_text_x_mm = ?
        WHERE preset_key = 'label_2x2'
          AND ABS(qr_size_mm - ?) < 0.15
          AND ABS(qr_y_mm - ?) < 0.12
          AND ABS(qr_x_mm - ?) < 0.12
        ''',
        (
            _lbl2_qr_x,
            _lbl2_qr_center_x,
            _lbl2_qr_center_x,
            _lbl2_qr_size,
            _lbl2_qr_y,
            _prev_lbl2_qr_x_ship,
        ),
    )
    conn.commit()
    conn.close()


def normalize_department_display_code(branch, department, cur=None):
    """Label text for department QR codes (restaurant: branch code; office: MAA-{department})."""
    branch = (branch or '').strip()
    department = (department or '').strip()
    if branch == OFFICE_BRANCH_LABEL:
        return f'MAA-{department}'

    conn = None
    if cur is None:
        conn = get_db_connection()
        cur = conn.cursor()
    cur.execute('SELECT branch_code FROM branches WHERE name = ?', (branch,))
    row = cur.fetchone()
    if conn is not None:
        conn.close()
    if row and row[0] and str(row[0]).strip():
        return str(row[0]).strip().upper()
    return branch.replace(' ', '').upper()


def get_qr_label_layout_dict(conn, preset_key):
    """Return layout as dict or None. Caller should use existing connection."""
    cur = conn.cursor()
    cur.execute('SELECT * FROM qr_label_layouts WHERE preset_key = ?', (preset_key,))
    row = cur.fetchone()
    if not row:
        return None
    desc = [c[0] for c in cur.description]
    return dict(zip(desc, row))


ALLOWED_LAYOUT_UPDATE_FIELDS = frozenset({
    'label_width_mm', 'label_height_mm', 'qr_x_mm', 'qr_y_mm', 'qr_size_mm', 'qr_reference_px',
    'primary_text_x_mm', 'primary_text_y_mm', 'secondary_text_x_mm', 'secondary_text_y_mm',
    'primary_font_pt', 'secondary_font_pt',
    'primary_text_align', 'secondary_text_align',
    'primary_text_max_width_mm', 'secondary_text_max_width_mm',
    'print_offset_qr_x_mm', 'print_offset_qr_y_mm',
    'print_offset_primary_x_mm', 'print_offset_primary_y_mm',
    'print_offset_secondary_x_mm', 'print_offset_secondary_y_mm',
})


def upsert_qr_label_layout_updates(conn, preset_key, payload):
    """
    Merge JSON payload into qr_label_layouts for preset_key. Only admin-validated fields applied.
    Returns updated row dict or None if preset missing before update.
    """
    cur = conn.cursor()
    cur.execute('SELECT 1 FROM qr_label_layouts WHERE preset_key = ?', (preset_key,))
    if not cur.fetchone():
        return None
    sets = []
    values = []
    for key, raw in payload.items():
        if key not in ALLOWED_LAYOUT_UPDATE_FIELDS or raw is None:
            continue
        if key in ('primary_text_align', 'secondary_text_align'):
            if raw not in ('left', 'center', 'right'):
                continue
            sets.append(f'{key} = ?')
            values.append(raw)
        elif key == 'qr_reference_px':
            sets.append(f'{key} = ?')
            values.append(int(raw))
        else:
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            sets.append(f'{key} = ?')
            values.append(v)
    if sets:
        values.append(preset_key)
        cur.execute(f"UPDATE qr_label_layouts SET {', '.join(sets)} WHERE preset_key = ?", values)
        conn.commit()
    return get_qr_label_layout_dict(conn, preset_key)


def qr_layout_to_api_dict(layout):
    """SQLite row dict -> compact JSON-safe layout."""
    if not layout:
        return None
    return {
        'preset_key': layout['preset_key'],
        'label_width_mm': layout['label_width_mm'],
        'label_height_mm': layout['label_height_mm'],
        'qr_x_mm': layout['qr_x_mm'],
        'qr_y_mm': layout['qr_y_mm'],
        'qr_size_mm': layout['qr_size_mm'],
        'qr_reference_px': layout['qr_reference_px'],
        'primary_text_x_mm': layout['primary_text_x_mm'],
        'primary_text_y_mm': layout['primary_text_y_mm'],
        'secondary_text_x_mm': layout['secondary_text_x_mm'],
        'secondary_text_y_mm': layout['secondary_text_y_mm'],
        'primary_font_pt': layout['primary_font_pt'],
        'secondary_font_pt': layout['secondary_font_pt'],
        'primary_text_align': layout['primary_text_align'],
        'secondary_text_align': layout['secondary_text_align'],
        'primary_text_max_width_mm': layout['primary_text_max_width_mm'],
        'secondary_text_max_width_mm': layout['secondary_text_max_width_mm'],
        'print_offset_qr_x_mm': layout['print_offset_qr_x_mm'] or 0,
        'print_offset_qr_y_mm': layout['print_offset_qr_y_mm'] or 0,
        'print_offset_primary_x_mm': layout['print_offset_primary_x_mm'] or 0,
        'print_offset_primary_y_mm': layout['print_offset_primary_y_mm'] or 0,
        'print_offset_secondary_x_mm': layout['print_offset_secondary_x_mm'] or 0,
        'print_offset_secondary_y_mm': layout['print_offset_secondary_y_mm'] or 0,
    }