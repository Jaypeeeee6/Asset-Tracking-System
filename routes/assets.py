from flask import Blueprint, render_template, request, redirect, url_for, jsonify, abort, send_file
from flask_login import login_required, current_user
from models.database import get_db_connection, generate_asset_code
import qrcode
from io import BytesIO
import uuid

assets_bp = Blueprint('assets', __name__)

@assets_bp.route('/dashboard')
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

@assets_bp.route('/add', methods=['POST'])
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
    return redirect(url_for('assets.dashboard'))

@assets_bp.route('/update/<int:asset_id>', methods=['POST'])
@login_required
def update_asset(asset_id):
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
    
    try:
        cur.execute('''
            UPDATE assets 
            SET name=?, asset_type=?, quantity=?, owner=?, building=?, department=?, used_status=?
            WHERE id=?
        ''', (name, asset_type, quantity, owner, building, department, used_status, asset_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@assets_bp.route('/delete/<int:asset_id>', methods=['POST'])
@login_required
def delete_asset(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM assets WHERE id=?', (asset_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@assets_bp.route('/update_status/<int:asset_id>', methods=['POST'])
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

@assets_bp.route('/bulk_update_status', methods=['POST'])
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

@assets_bp.route('/bulk_delete', methods=['POST'])
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

@assets_bp.route('/qrcode/<int:asset_id>')
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

@assets_bp.route('/department_qr/<building>/<department>')
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

@assets_bp.route('/department_items/<building>/<department>')
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

@assets_bp.route('/qrdata/<int:asset_id>')
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

@assets_bp.route('/asset/<asset_code>')
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

@assets_bp.route('/assets')
@login_required
def get_assets():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name, building, department, asset_code FROM assets')
    assets = [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]
    conn.close()
    return jsonify(assets) 