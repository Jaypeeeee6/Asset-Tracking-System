import os
import sqlite3
import uuid
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
import qrcode
from PIL import Image
from io import BytesIO
from flask import send_file

app = Flask(__name__)
app.config['DATABASE'] = 'production_assets.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'qrcodes')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

BASE_URL = 'http://localhost:5000'

def get_db_connection():
    import sqlite3
    conn = sqlite3.connect(app.config['DATABASE'], timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Create table if not exists
    cur.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            owner TEXT NOT NULL,
            building TEXT NOT NULL,
            department TEXT NOT NULL,
            asset_code TEXT,
            qr_random_code TEXT
        )
    ''')
    # Add qr_random_code column if missing
    cur.execute("PRAGMA table_info(assets)")
    columns = [row[1] for row in cur.fetchall()]
    if 'qr_random_code' not in columns:
        cur.execute('ALTER TABLE assets ADD COLUMN qr_random_code TEXT')
    conn.commit()
    # Populate qr_random_code for rows where it is NULL or empty
    cur.execute("SELECT id FROM assets WHERE qr_random_code IS NULL OR qr_random_code = ''")
    rows = cur.fetchall()
    for row in rows:
        random_code = str(uuid.uuid4())
        cur.execute('UPDATE assets SET qr_random_code=? WHERE id=?', (random_code, row[0]))
    conn.commit()
    # Populate asset_code for rows where it is NULL or empty
    cur.execute("SELECT id, building, department FROM assets WHERE asset_code IS NULL OR asset_code = ''")
    rows = cur.fetchall()
    for row in rows:
        asset_code = generate_asset_code(row[1], row[2])
        cur.execute('UPDATE assets SET asset_code=? WHERE id=?', (asset_code, row[0]))
    conn.commit()
    conn.close()

def generate_asset_code(building, department):
    conn = get_db_connection()
    cur = conn.cursor()
    # Remove spaces and uppercase for code
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

ASSETS_PER_PAGE = 10

@app.route('/')
def index():
    page = int(request.args.get('page', 1))
    sort_by = request.args.get('sort_by', 'id')
    sort_dir = request.args.get('sort_dir', 'asc')
    building_filter = request.args.get('building', '')
    department_filter = request.args.get('department', '')
    offset = (page - 1) * ASSETS_PER_PAGE
    conn = get_db_connection()
    cur = conn.cursor()
    # Get unique buildings and departments for dropdowns
    cur.execute('SELECT DISTINCT building FROM assets')
    buildings = [row[0] for row in cur.fetchall()]
    cur.execute('SELECT DISTINCT department FROM assets')
    departments = [row[0] for row in cur.fetchall()]
    # Build WHERE clause for filters
    where_clauses = []
    params = []
    if building_filter:
        where_clauses.append('building = ?')
        params.append(building_filter)
    if department_filter:
        where_clauses.append('department = ?')
        params.append(department_filter)
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
    # Validate sort_by and sort_dir
    valid_sort_fields = ['id', 'name', 'quantity', 'owner', 'building', 'department']
    if sort_by not in valid_sort_fields:
        sort_by = 'id'
    sort_dir = 'desc' if sort_dir == 'desc' else 'asc'
    # Count total filtered assets
    cur.execute(f'SELECT COUNT(*) FROM assets {where_sql}', params)
    total_assets = cur.fetchone()[0]
    total_pages = (total_assets + ASSETS_PER_PAGE - 1) // ASSETS_PER_PAGE
    # Get filtered, sorted, paginated assets
    cur.execute(f'SELECT * FROM assets {where_sql} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?', params + [ASSETS_PER_PAGE, offset])
    assets = [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]
    conn.close()
    return render_template('index.html', assets=assets, page=page, total_pages=total_pages, sort_by=sort_by, sort_dir=sort_dir, buildings=buildings, departments=departments, building_filter=building_filter, department_filter=department_filter)

@app.route('/add', methods=['POST'])
def add_asset():
    name = request.form['name']
    owner = request.form['owner']
    building = request.form['building']
    department = request.form['department']
    quantity = int(request.form['quantity'])
    conn = get_db_connection()
    cur = conn.cursor()
    # Check if asset exists
    cur.execute('SELECT id, quantity, asset_code, qr_random_code FROM assets WHERE name=? AND owner=? AND building=? AND department=?',
                (name, owner, building, department))
    row = cur.fetchone()
    if row:
        # Update quantity
        new_quantity = row[1] + quantity
        cur.execute('UPDATE assets SET quantity=? WHERE id=?', (new_quantity, row[0]))
        asset_id = row[0]
        asset_code = row[2]
        qr_random_code = row[3]
    else:
        # Generate new asset code and random code
        asset_code = generate_asset_code(building, department)
        qr_random_code = str(uuid.uuid4())
        cur.execute('INSERT INTO assets (name, quantity, owner, building, department, asset_code, qr_random_code) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (name, quantity, owner, building, department, asset_code, qr_random_code))
        asset_id = cur.lastrowid
    conn.commit()
    conn.close()
    # Generate QR code with direct link
    qr_url = f"{BASE_URL}/asset/{asset_code}"
    qr_img = qrcode.make(qr_url)
    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    return redirect(url_for('index'))

@app.route('/delete/<int:asset_id>', methods=['POST'])
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
            'quantity': asset['quantity']
        })
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/asset_by_code/<asset_code>')
def api_asset_by_code(asset_code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM assets WHERE asset_code = ?', (asset_code,))
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
            'quantity': asset['quantity']
        })
    return jsonify({'error': True}), 404

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

@app.route('/qrcode/<int:asset_id>')
def qrcode_image(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT asset_code FROM assets WHERE id=?', (asset_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row['asset_code']:
        abort(404)
    qr_url = f"{BASE_URL}/asset/{row['asset_code']}"
    qr_img = qrcode.make(qr_url)
    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)