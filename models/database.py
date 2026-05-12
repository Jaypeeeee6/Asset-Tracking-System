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
    _lbl2_qr_x = 3.68
    _lbl2_qr_y = 6.25
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
    conn.commit()
    conn.close()


def normalize_department_display_code(building, department):
    """Build canonical MAA-{BUILDING}-{DEPT} segment used for labels (matches dashboard JS)."""
    b = ''.join(str(building).upper().split())
    d = ''.join(str(department).upper().split())
    return f'MAA-{b}-{d}'


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