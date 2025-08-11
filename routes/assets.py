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
    valid_sort_fields = ['id', 'name', 'quantity', 'price', 'owner', 'building', 'department', 'used_status', 'asset_type']
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
    
    # Get chart data (all assets, not paginated)
    cur.execute('SELECT used_status, building, department, price, quantity FROM assets')
    all_assets = cur.fetchall()
    
    # Calculate chart data
    status_counts = {'Used': 0, 'Not Used': 0, 'Out of Service': 0}
    building_counts = {}
    building_prices = {}
    department_prices = {}
    total_system_value = 0
    
    for asset in all_assets:
        status = asset[0]
        building = asset[1]
        department = asset[2]
        price = asset[3] or 0.0
        quantity = asset[4] or 1
        total_price = price * quantity
        
        if status in status_counts:
            status_counts[status] += 1
        
        if building in building_counts:
            building_counts[building] += 1
            building_prices[building] += total_price
        else:
            building_counts[building] = 1
            building_prices[building] = total_price
        
        # Department prices (key is building-department)
        dept_key = f"{building}-{department}"
        if dept_key in department_prices:
            department_prices[dept_key] += total_price
        else:
            department_prices[dept_key] = total_price
        
        total_system_value += total_price
    
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
                         search_query=search_query,
                         status_filter=status_filter,
                         asset_type_filter=asset_type_filter,
                         chart_data={
                             'status_counts': status_counts,
                             'building_counts': building_counts,
                             'building_prices': building_prices,
                             'department_prices': department_prices,
                             'total_system_value': total_system_value
                         })

@assets_bp.route('/add', methods=['POST'])
@login_required
def add_asset():
    selected_asset_names = request.form.get('selected_asset_names', '')
    asset_type = request.form.get('asset_type', '')
    owner = request.form.get('owner', '')
    building = request.form['building']
    department = request.form['department']
    quantity = int(request.form['quantity'])
    price = float(request.form.get('price', 0.0))
    used_status = request.form.get('used_status', 'Not Used')
    no_owner = request.form.get('no_owner') == 'on'
    
    # Handle no owner case
    if no_owner:
        owner = 'No Owner'
    
    # Parse selected asset names
    asset_names = [name.strip() for name in selected_asset_names.split(',') if name.strip()]
    
    if not asset_names:
        return redirect(url_for('assets.dashboard'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Pre-calculate asset codes for new assets to ensure sequential numbering
    new_asset_codes = []
    if len(asset_names) > 1:
        # Get the base asset code format
        building_code = building.replace(' ', '').upper()
        department_code = department.replace(' ', '').upper()
        
        # Get all existing asset codes for this building/department (both active and archived)
        cur.execute('SELECT asset_code FROM assets WHERE building=? AND department=? ORDER BY asset_code DESC', (building, department))
        active_codes = cur.fetchall()
        
        # Also get archived asset codes for this building/department
        cur.execute('SELECT asset_code FROM archived_assets WHERE building=? AND department=? ORDER BY asset_code DESC', (building, department))
        archived_codes = cur.fetchall()
        
        # Find the highest number from both active and archived assets
        highest_num = 0
        for row in active_codes + archived_codes:
            if row[0]:
                try:
                    num = int(row[0].split('-')[-1])
                    if num > highest_num:
                        highest_num = num
                except (ValueError, IndexError):
                    continue
        
        # Generate sequential codes starting from highest + 1
        next_num = highest_num + 1
        for i in range(len(asset_names)):
            asset_code = f"MAA-{building_code}-{department_code}-{next_num:03d}"
            new_asset_codes.append(asset_code)
            next_num += 1
    
    # Create individual assets for each selected asset name
    for i, asset_name in enumerate(asset_names):
        # Check for existing asset with same name, building, and department
        cur.execute('SELECT id, quantity, asset_code, qr_random_code FROM assets WHERE name=? AND building=? AND department=?', (asset_name, building, department))
        row = cur.fetchone()
        if row:
            new_quantity = row[1] + quantity
            cur.execute('UPDATE assets SET quantity=?, used_status=?, asset_type=?, owner=? WHERE id=?', (new_quantity, used_status, asset_type, owner, row[0]))
        else:
            # Use pre-calculated asset code or generate single one
            if len(asset_names) > 1:
                asset_code = new_asset_codes[i]
            else:
                asset_code = generate_asset_code(building, department)
            
            qr_random_code = str(uuid.uuid4())
            
            cur.execute('INSERT INTO assets (name, quantity, price, owner, building, department, asset_code, qr_random_code, used_status, asset_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (asset_name, quantity, price, owner, building, department, asset_code, qr_random_code, used_status, asset_type))
    
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
    price = float(request.form.get('price', 0.0))
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
            SET name=?, asset_type=?, quantity=?, price=?, owner=?, building=?, department=?, used_status=?
            WHERE id=?
        ''', (name, asset_type, quantity, price, owner, building, department, used_status, asset_id))
        
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
    archive_reason = request.form.get('archive_reason', 'Asset deleted by user')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get the asset data before deleting
    cur.execute('SELECT * FROM assets WHERE id=?', (asset_id,))
    asset = cur.fetchone()
    
    if not asset:
        conn.close()
        return jsonify({'error': 'Asset not found'}), 404
    
    # Insert into archived_assets table
    cur.execute('''
        INSERT INTO archived_assets 
        (original_id, name, quantity, price, owner, building, department, asset_code, qr_random_code, used_status, asset_type, archived_by, archive_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        asset['id'], asset['name'], asset['quantity'], asset.get('price', 0.0), asset['owner'], 
        asset['building'], asset['department'], asset['asset_code'], 
        asset['qr_random_code'], asset['used_status'], asset['asset_type'],
        current_user.username, archive_reason
    ))
    
    # Delete from assets table
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
    archive_reason = request.form.get('archive_reason', 'Assets bulk deleted by user')
    
    if not asset_ids:
        return jsonify({'error': 'No assets selected'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get all assets to be deleted
    placeholders = ','.join(['?'] * len(asset_ids))
    cur.execute(f'SELECT * FROM assets WHERE id IN ({placeholders})', asset_ids)
    assets = cur.fetchall()
    
    # Insert into archived_assets table
    for asset in assets:
        cur.execute('''
            INSERT INTO archived_assets 
            (original_id, name, quantity, owner, building, department, asset_code, qr_random_code, used_status, asset_type, archived_by, archive_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            asset['id'], asset['name'], asset['quantity'], asset['owner'], 
            asset['building'], asset['department'], asset['asset_code'], 
            asset['qr_random_code'], asset['used_status'], asset['asset_type'],
            current_user.username, archive_reason
        ))
    
    # Delete from assets table
    cur.execute(f'DELETE FROM assets WHERE id IN ({placeholders})', asset_ids)
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'archived': len(assets)})

@assets_bp.route('/qrcode/<int:asset_id>')
def qrcode_image(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT asset_code FROM assets WHERE id=?', (asset_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row['asset_code']:
        abort(404)
    
    # Use configurable base URL or fallback to request.host_url
    import os
    base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    qr_url = f"{base_url}/asset/{row['asset_code']}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=2
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#D4AF37", back_color="#181818")
    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@assets_bp.route('/department_qr/<building>/<department>')
def department_qrcode_image(building, department):
    # Decode URL-encoded parameters for QR generation
    from urllib.parse import unquote
    import os
    building = unquote(building)
    department = unquote(department)
    
    # Use configurable base URL or fallback to request.host_url
    base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    qr_url = f"{base_url}/assets/department_items/{building}/{department}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=2
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#D4AF37", back_color="#181818")
    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@assets_bp.route('/department_items/<building>/<department>')
def department_items(building, department):
    # Decode URL-encoded parameters
    from urllib.parse import unquote
    building = unquote(building)
    department = unquote(department)
    
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
    columns = [desc[0] for desc in cur.description]
    
    # Calculate total department value
    cur.execute(f'SELECT SUM(price * quantity) FROM assets {where_sql}', params)
    total_department_value = cur.fetchone()[0] or 0.0
    
    conn.close()
    
    if rows:
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
                         search_query=search_query,
                         total_department_value=total_department_value)

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

@assets_bp.route('/archived_qrdata/<int:archived_id>')
def archived_qrdata(archived_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM archived_assets WHERE id=?', (archived_id,))
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

@assets_bp.route('/archived_qrcode/<int:archived_id>')
def archived_qrcode_image(archived_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT asset_code FROM archived_assets WHERE id=?', (archived_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row['asset_code']:
        abort(404)
    
    # Use configurable base URL or fallback to request.host_url
    import os
    base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    qr_url = f"{base_url}/asset/{row['asset_code']}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=2
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#D4AF37", back_color="#181818")
    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@assets_bp.route('/asset/<asset_code>')
def asset_info(asset_code):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # First check active assets
    cur.execute('SELECT * FROM assets WHERE asset_code = ?', (asset_code,))
    row = cur.fetchone()
    
    if row:
        # Asset is active
        columns = [desc[0] for desc in cur.description]
        asset = dict(zip(columns, row))
        asset['is_archived'] = False
        conn.close()
        return render_template('asset_info.html', asset=asset)
    
    # If not found in active assets, check archived assets
    cur.execute('SELECT * FROM archived_assets WHERE asset_code = ?', (asset_code,))
    row = cur.fetchone()
    
    if row:
        # Asset is archived
        columns = [desc[0] for desc in cur.description]
        asset = dict(zip(columns, row))
        asset['is_archived'] = True
        conn.close()
        return render_template('asset_info.html', asset=asset)
    
    conn.close()
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

@assets_bp.route('/archive')
@login_required
def archive():
    if current_user.role != 'admin':
        return redirect(url_for('assets.dashboard'))
    
    page = int(request.args.get('page', 1))
    sort_by = request.args.get('sort_by', 'archived_at')
    sort_dir = request.args.get('sort_dir', 'desc')
    search_query = request.args.get('search', '')
    per_page = int(request.args.get('per_page', 10))
    
    offset = (page - 1) * per_page
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Build WHERE clause for search
    where_clauses = []
    params = []
    
    if search_query:
        search_clauses = [
            'name LIKE ?',
            'owner LIKE ?',
            'asset_code LIKE ?',
            'building LIKE ?',
            'department LIKE ?',
            'asset_type LIKE ?',
            'archived_by LIKE ?',
            'archive_reason LIKE ?'
        ]
        where_clauses.append(f"({' OR '.join(search_clauses)})")
        search_param = f'%{search_query}%'
        params.extend([search_param] * 8)
    
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
    valid_sort_fields = ['id', 'name', 'quantity', 'owner', 'building', 'department', 'used_status', 'asset_type', 'archived_at', 'archived_by']
    if sort_by not in valid_sort_fields:
        sort_by = 'archived_at'
    sort_dir = 'desc' if sort_dir == 'desc' else 'asc'
    
    # Get total count
    cur.execute(f'SELECT COUNT(*) FROM archived_assets {where_sql}', params)
    total_archived = cur.fetchone()[0]
    total_pages = (total_archived + per_page - 1) // per_page
    
    # Get paginated results
    cur.execute(f'SELECT * FROM archived_assets {where_sql} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?', params + [per_page, offset])
    archived_assets = [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]
    conn.close()
    
    return render_template('archive.html', 
                         archived_assets=archived_assets, 
                         page=page, 
                         total_pages=total_pages, 
                         total_archived=total_archived,
                         per_page=per_page,
                         sort_by=sort_by, 
                         sort_dir=sort_dir, 
                         search_query=search_query)

@assets_bp.route('/restore/<int:archived_id>', methods=['POST'])
@login_required
def restore_asset(archived_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied. Only administrators can restore assets.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get the archived asset data
    cur.execute('SELECT * FROM archived_assets WHERE id=?', (archived_id,))
    archived_asset = cur.fetchone()
    
    if not archived_asset:
        conn.close()
        return jsonify({'error': 'Archived asset not found'}), 404
    
    try:
        # Check if an asset with the same name, building, and department already exists
        cur.execute('SELECT id, quantity FROM assets WHERE name=? AND building=? AND department=?', 
                   (archived_asset['name'], archived_asset['building'], archived_asset['department']))
        existing_asset = cur.fetchone()
        
        if existing_asset:
            # Update existing asset quantity
            new_quantity = existing_asset[1] + archived_asset['quantity']
            cur.execute('UPDATE assets SET quantity=?, used_status=?, asset_type=? WHERE id=?', 
                       (new_quantity, archived_asset['used_status'], archived_asset['asset_type'], existing_asset[0]))
        else:
            # Create new asset
            asset_code = generate_asset_code(archived_asset['building'], archived_asset['department'])
            qr_random_code = str(uuid.uuid4())
            cur.execute('''
                INSERT INTO assets (name, quantity, owner, building, department, asset_code, qr_random_code, used_status, asset_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                archived_asset['name'], archived_asset['quantity'], archived_asset['owner'],
                archived_asset['building'], archived_asset['department'], asset_code, qr_random_code,
                archived_asset['used_status'], archived_asset['asset_type']
            ))
        
        # Delete from archived_assets table
        cur.execute('DELETE FROM archived_assets WHERE id=?', (archived_id,))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Asset restored successfully'})
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Failed to restore asset: {str(e)}'}), 500

@assets_bp.route('/bulk_restore', methods=['POST'])
@login_required
def bulk_restore_assets():
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied. Only administrators can restore assets.'}), 403
    
    archived_ids = request.form.getlist('archived_ids[]')
    
    if not archived_ids:
        return jsonify({'error': 'No assets selected for restoration'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    restored_count = 0
    errors = []
    
    try:
        for archived_id in archived_ids:
            # Get the archived asset data
            cur.execute('SELECT * FROM archived_assets WHERE id=?', (archived_id,))
            archived_asset = cur.fetchone()
            
            if not archived_asset:
                errors.append(f'Archived asset ID {archived_id} not found')
                continue
            
            # Check if an asset with the same name, building, and department already exists
            cur.execute('SELECT id, quantity FROM assets WHERE name=? AND building=? AND department=?', 
                       (archived_asset['name'], archived_asset['building'], archived_asset['department']))
            existing_asset = cur.fetchone()
            
            if existing_asset:
                # Update existing asset quantity
                new_quantity = existing_asset[1] + archived_asset['quantity']
                cur.execute('UPDATE assets SET quantity=?, used_status=?, asset_type=? WHERE id=?', 
                           (new_quantity, archived_asset['used_status'], archived_asset['asset_type'], existing_asset[0]))
            else:
                # Create new asset
                asset_code = generate_asset_code(archived_asset['building'], archived_asset['department'])
                qr_random_code = str(uuid.uuid4())
                cur.execute('''
                    INSERT INTO assets (name, quantity, owner, building, department, asset_code, qr_random_code, used_status, asset_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    archived_asset['name'], archived_asset['quantity'], archived_asset['owner'],
                    archived_asset['building'], archived_asset['department'], asset_code, qr_random_code,
                    archived_asset['used_status'], archived_asset['asset_type']
                ))
            
            # Delete from archived_assets table
            cur.execute('DELETE FROM archived_assets WHERE id=?', (archived_id,))
            restored_count += 1
        
        conn.commit()
        conn.close()
        
        if errors:
            return jsonify({
                'success': True, 
                'restored': restored_count, 
                'errors': errors,
                'message': f'Restored {restored_count} assets with {len(errors)} errors'
            })
        else:
            return jsonify({
                'success': True, 
                'restored': restored_count,
                'message': f'Successfully restored {restored_count} assets'
            })
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Failed to restore assets: {str(e)}'}), 500

@assets_bp.route('/permanent_delete/<int:archived_id>', methods=['POST'])
@login_required
def permanent_delete_archived_asset(archived_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied. Only administrators can permanently delete assets.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get the archived asset data for confirmation
    cur.execute('SELECT name, building, department FROM archived_assets WHERE id=?', (archived_id,))
    archived_asset = cur.fetchone()
    
    if not archived_asset:
        conn.close()
        return jsonify({'error': 'Archived asset not found'}), 404
    
    try:
        # Permanently delete from archived_assets table
        cur.execute('DELETE FROM archived_assets WHERE id=?', (archived_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Asset "{archived_asset["name"]}" permanently deleted'})
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Failed to permanently delete asset: {str(e)}'}), 500

@assets_bp.route('/bulk_permanent_delete', methods=['POST'])
@login_required
def bulk_permanent_delete_archived_assets():
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied. Only administrators can permanently delete assets.'}), 403
    
    archived_ids = request.form.getlist('archived_ids[]')
    
    if not archived_ids:
        return jsonify({'error': 'No assets selected for permanent deletion'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    deleted_count = 0
    errors = []
    
    try:
        for archived_id in archived_ids:
            # Get the archived asset data for confirmation
            cur.execute('SELECT name FROM archived_assets WHERE id=?', (archived_id,))
            archived_asset = cur.fetchone()
            
            if not archived_asset:
                errors.append(f'Archived asset ID {archived_id} not found')
                continue
            
            # Permanently delete from archived_assets table
            cur.execute('DELETE FROM archived_assets WHERE id=?', (archived_id,))
            deleted_count += 1
        
        conn.commit()
        conn.close()
        
        if errors:
            return jsonify({
                'success': True, 
                'deleted': deleted_count, 
                'errors': errors,
                'message': f'Permanently deleted {deleted_count} assets with {len(errors)} errors'
            })
        else:
            return jsonify({
                'success': True, 
                'deleted': deleted_count,
                'message': f'Successfully permanently deleted {deleted_count} assets'
            })
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Failed to permanently delete assets: {str(e)}'}), 500 