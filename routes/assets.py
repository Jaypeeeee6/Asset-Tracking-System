from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    abort,
    send_file,
    make_response,
    flash,
)
from flask_login import login_required, current_user
import base64
from models.database import (
    get_db_connection,
    generate_asset_code,
    allocate_asset_codes,
    normalize_department_display_code,
    get_qr_label_layout_dict,
    qr_layout_to_api_dict,
    upsert_qr_label_layout_updates,
    RESTAURANT_DEFAULT_DEPARTMENT_NAME,
    RESTAURANT_AREA_OPTIONS,
    ensure_restaurant_area_department_for_branch,
    OFFICE_BRANCH_LABEL,
    ASSET_KIND_SHARED,
    ASSET_KIND_BRANCH,
    ASSET_KINDS,
    asset_type_for_venue_matches,
    format_branch_with_code,
    format_asset_location_display,
)
from utils.asset_documents import (
    list_documents_for_asset,
    list_documents_grouped_by_asset_ids,
    save_uploaded_files_for_assets,
    delete_document_record,
    delete_all_documents_for_assets,
    document_path,
)
import qrcode
from io import BytesIO
import uuid
import json
import datetime

assets_bp = Blueprint('assets', __name__)


def _parse_asset_date(raw_value):
    """Return YYYY-MM-DD or today's date if missing/invalid."""
    value = (raw_value or '').strip()
    if value:
        try:
            return datetime.date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return datetime.date.today().isoformat()


def _parse_csv_list(raw):
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(',') if part.strip()]


def _parse_int_csv(raw):
    ids = []
    for part in _parse_csv_list(raw):
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


def _parse_asset_kind(raw):
    kind = (raw or ASSET_KIND_BRANCH).strip().lower()
    return kind if kind in ASSET_KINDS else ASSET_KIND_BRANCH


def _branch_code_map(cur):
    cur.execute('SELECT name, branch_code FROM branches')
    return {
        row[0]: (str(row[1]).strip() if row[1] else '')
        for row in cur.fetchall()
    }


def _attach_asset_location_displays(cur, assets):
    """Set location_lines on each asset (branch code + name; all branches for shared)."""
    if not assets:
        return
    codes = _branch_code_map(cur)

    group_ids = sorted({
        (a.get('shared_group_id') or '').strip()
        for a in assets
        if (a.get('asset_kind') or ASSET_KIND_BRANCH) == ASSET_KIND_SHARED
        and (a.get('shared_group_id') or '').strip()
    })
    branches_by_group = {}
    if group_ids:
        placeholders = ','.join('?' * len(group_ids))
        cur.execute(
            f'''
            SELECT shared_group_id, branch
            FROM assets
            WHERE shared_group_id IN ({placeholders})
            ORDER BY branch
            ''',
            group_ids,
        )
        for gid, branch in cur.fetchall():
            branches_by_group.setdefault(gid, [])
            if branch not in branches_by_group[gid]:
                branches_by_group[gid].append(branch)

    # Fallback for legacy shared rows without shared_group_id
    legacy_keys = []
    for a in assets:
        if (a.get('asset_kind') or ASSET_KIND_BRANCH) != ASSET_KIND_SHARED:
            continue
        if (a.get('shared_group_id') or '').strip():
            continue
        legacy_keys.append((a.get('name'), a.get('asset_type'), a.get('owner')))
    branches_by_legacy = {}
    for name, asset_type, owner in set(legacy_keys):
        cur.execute(
            '''
            SELECT DISTINCT branch FROM assets
            WHERE asset_kind = ? AND name = ? AND IFNULL(asset_type, '') = IFNULL(?, '')
              AND IFNULL(owner, '') = IFNULL(?, '')
            ORDER BY branch
            ''',
            (ASSET_KIND_SHARED, name, asset_type, owner),
        )
        branches_by_legacy[(name, asset_type, owner)] = [row[0] for row in cur.fetchall()]

    for asset in assets:
        branch = asset.get('branch') or ''
        department = asset.get('department') or ''
        kind = asset.get('asset_kind') or ASSET_KIND_BRANCH
        if kind == ASSET_KIND_SHARED and branch != OFFICE_BRANCH_LABEL:
            gid = (asset.get('shared_group_id') or '').strip()
            if gid and gid in branches_by_group:
                branch_names = branches_by_group[gid]
            else:
                branch_names = branches_by_legacy.get(
                    (asset.get('name'), asset.get('asset_type'), asset.get('owner')),
                    [branch],
                )
            asset['location_lines'] = [
                format_branch_with_code(b, codes.get(b))
                for b in branch_names
            ]
        else:
            asset['location_lines'] = [
                format_asset_location_display(branch, department, codes.get(branch))
            ]


def _parse_brand_ids(raw_values):
    brand_ids = []
    for raw_id in raw_values or []:
        try:
            brand_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    return brand_ids


def _normalize_restaurant_area(raw_area):
    """Return a valid restaurant area name, or None if missing/invalid."""
    area = (raw_area or '').strip()
    if not area:
        return None
    if area == RESTAURANT_DEFAULT_DEPARTMENT_NAME:
        return area
    allowed = {opt.casefold(): opt for opt in RESTAURANT_AREA_OPTIONS}
    canonical = allowed.get(area.casefold())
    return canonical


def _validate_asset_venue_location(cur, venue, branch, department, brand_id=None, brand_ids=None):
    """Ensure branch/department match restaurant vs office rules."""
    v = (venue or 'restaurant').strip().lower()
    if v not in ('restaurant', 'office'):
        return 'Invalid location type.'
    if v == 'office':
        if branch != OFFICE_BRANCH_LABEL:
            return 'Office assets must use the Office location.'
        cur.execute(
            'SELECT 1 FROM departments WHERE branch_id IS NULL AND name = ?',
            (department,),
        )
        if not cur.fetchone():
            return 'Select a valid office department.'
        return None
    area = _normalize_restaurant_area(department)
    if not area:
        return 'Select a restaurant area (Kitchen, Dining, Cashier, etc.).'
    cur.execute('SELECT id FROM branches WHERE name = ?', (branch,))
    row = cur.fetchone()
    if not row:
        return 'Select a valid restaurant branch.'
    bid = row[0]
    ensure_restaurant_area_department_for_branch(cur, bid, area)
    return None


def _upsert_asset_row(cur, asset_name, price, owner, branch, department, used_status, asset_type, asset_kind, shared_group_id=None, asset_date=None):
    """Insert or update one asset row; return asset id."""
    cur.execute(
        'SELECT id, asset_code, qr_random_code FROM assets WHERE name=? AND branch=? AND department=?',
        (asset_name, branch, department),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            'UPDATE assets SET used_status=?, asset_type=?, asset_kind=?, shared_group_id=?, owner=?, price=? WHERE id=?',
            (used_status, asset_type, asset_kind, shared_group_id, owner, price, row[0]),
        )
        return row[0]
    asset_code = generate_asset_code(branch, department, cur=cur)
    qr_random_code = str(uuid.uuid4())
    date_value = (asset_date or '').strip() or datetime.date.today().isoformat()
    cur.execute(
        '''
        INSERT INTO assets
        (name, price, owner, branch, department, asset_code, qr_random_code, used_status, asset_type, asset_kind, shared_group_id, asset_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            asset_name, price, owner, branch, department, asset_code, qr_random_code,
            used_status, asset_type, asset_kind, shared_group_id, date_value,
        ),
    )
    return cur.lastrowid


def _get_asset_name_id(cur, asset_name, asset_type):
    cur.execute(
        '''
        SELECT an.id FROM asset_names an
        JOIN asset_types at ON an.asset_type_id = at.id
        WHERE an.name = ? AND at.name = ?
        ''',
        (asset_name, asset_type),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _get_spec_fields_for_asset_name(cur, asset_name_id):
    cur.execute(
        '''
        SELECT id, label FROM asset_name_spec_fields
        WHERE asset_name_id = ?
        ORDER BY sort_order, id
        ''',
        (asset_name_id,),
    )
    return [{'id': row[0], 'label': row[1]} for row in cur.fetchall()]


def _parse_asset_spec_values_json(raw):
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _validate_spec_values_for_asset_names(cur, asset_type, asset_names, spec_values_by_name):
    return None


def _save_spec_values_for_asset(cur, asset_id, asset_name, asset_type, spec_values_by_name):
    asset_name_id = _get_asset_name_id(cur, asset_name, asset_type)
    if not asset_name_id:
        return
    name_values = spec_values_by_name.get(asset_name, {})
    if not isinstance(name_values, dict):
        return
    spec_fields = _get_spec_fields_for_asset_name(cur, asset_name_id)
    cur.execute('DELETE FROM asset_spec_values WHERE asset_id = ?', (asset_id,))
    for field in spec_fields:
        val = (name_values.get(str(field['id'])) or name_values.get(field['id']) or '').strip()
        if val:
            cur.execute(
                'INSERT INTO asset_spec_values (asset_id, spec_field_id, value) VALUES (?, ?, ?)',
                (asset_id, field['id'], val),
            )


def _validate_spec_values_for_single_asset(cur, asset_type, asset_name, spec_values):
    if not isinstance(spec_values, dict):
        spec_values = {}
    asset_name_id = _get_asset_name_id(cur, asset_name, asset_type)
    if not asset_name_id:
        return None
    spec_fields = _get_spec_fields_for_asset_name(cur, asset_name_id)
    for field in spec_fields:
        val = (spec_values.get(str(field['id'])) or spec_values.get(field['id']) or '').strip()
        if not val:
            return f'"{field["label"]}" is required.'
    return None


def _save_spec_values_for_single_asset(cur, asset_id, asset_name, asset_type, spec_values):
    if not isinstance(spec_values, dict):
        spec_values = {}
    wrapped = {asset_name: spec_values}
    _save_spec_values_for_asset(cur, asset_id, asset_name, asset_type, wrapped)


def _get_inclusions_for_asset_name(cur, asset_name_id):
    cur.execute(
        '''
        SELECT id, label FROM asset_name_inclusions
        WHERE asset_name_id = ?
        ORDER BY sort_order, id
        ''',
        (asset_name_id,),
    )
    return [{'id': row[0], 'label': row[1]} for row in cur.fetchall()]


def _parse_asset_inclusion_values_json(raw):
    """Parse checked inclusions: {asset_name: [inclusion_id, ...]}."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _parse_inclusion_ids_list_json(raw):
    """Parse a flat list of checked inclusion ids for a single asset."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return data


def _save_inclusion_values_for_asset(cur, asset_id, asset_name, asset_type, inclusion_values_by_name):
    asset_name_id = _get_asset_name_id(cur, asset_name, asset_type)
    if not asset_name_id:
        return
    checked = inclusion_values_by_name.get(asset_name, [])
    checked_ids = set()
    if isinstance(checked, list):
        for cid in checked:
            try:
                checked_ids.add(int(cid))
            except (TypeError, ValueError):
                continue
    inclusions = _get_inclusions_for_asset_name(cur, asset_name_id)
    valid_ids = {inc['id'] for inc in inclusions}
    cur.execute('DELETE FROM asset_inclusion_values WHERE asset_id = ?', (asset_id,))
    for inc_id in checked_ids:
        if inc_id in valid_ids:
            cur.execute(
                'INSERT INTO asset_inclusion_values (asset_id, inclusion_id) VALUES (?, ?)',
                (asset_id, inc_id),
            )


def _save_inclusion_values_for_single_asset(cur, asset_id, asset_name, asset_type, checked_ids):
    if not isinstance(checked_ids, list):
        checked_ids = []
    wrapped = {asset_name: checked_ids}
    _save_inclusion_values_for_asset(cur, asset_id, asset_name, asset_type, wrapped)


def _compute_chart_data_from_asset_rows(rows):
    """Aggregate branch/department/value stats from asset rows (tuple or dict)."""
    status_counts = {'Used': 0, 'Not Used': 0, 'Out of Service': 0}
    branch_counts = {}
    branch_prices = {}
    department_counts = {}
    department_prices = {}
    total_system_value = 0.0

    for asset in rows:
        if isinstance(asset, dict):
            status = asset.get('used_status')
            branch = asset.get('branch')
            department = asset.get('department')
            price = asset.get('price') or 0.0
        else:
            status, branch, department, price = (
                asset[0], asset[1], asset[2], asset[3]
            )
            price = price or 0.0

        total_price = float(price)
        if status in status_counts:
            status_counts[status] += 1

        if branch in branch_counts:
            branch_counts[branch] += 1
            branch_prices[branch] += total_price
        else:
            branch_counts[branch] = 1
            branch_prices[branch] = total_price

        dept_key = f'{branch}-{department}'
        if dept_key in department_counts:
            department_counts[dept_key] += 1
            department_prices[dept_key] += total_price
        else:
            department_counts[dept_key] = 1
            department_prices[dept_key] = total_price

        total_system_value += total_price

    return {
        'status_counts': status_counts,
        'branch_counts': branch_counts,
        'branch_prices': branch_prices,
        'department_counts': department_counts,
        'department_prices': department_prices,
        'total_system_value': total_system_value,
    }


@assets_bp.route('/dashboard')
@login_required
def dashboard():
    page = int(request.args.get('page', 1))
    sort_by = request.args.get('sort_by', 'id')
    sort_dir = request.args.get('sort_dir', 'asc')
    branch_filter = request.args.get('branch') or request.args.get('building', '')
    department_filter = request.args.get('department', '')
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    asset_type_filter = request.args.get('asset_type', '')
    per_page = int(request.args.get('per_page', 10))
    
    offset = (page - 1) * per_page
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Load branches from database
    cur.execute('SELECT name FROM branches ORDER BY name')
    branches = [row[0] for row in cur.fetchall()]
    
    cur.execute('SELECT DISTINCT department FROM assets')
    departments = [row[0] for row in cur.fetchall()]
    
    # Build WHERE clause
    where_clauses = []
    params = []
    
    if branch_filter:
        where_clauses.append('branch = ?')
        params.append(branch_filter)
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
            'branch LIKE ?',
            'department LIKE ?',
            'asset_type LIKE ?'
        ]
        where_clauses.append(f"({' OR '.join(search_clauses)})")
        search_param = f'%{search_query}%'
        params.extend([search_param] * 6)
    
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
    valid_sort_fields = ['id', 'name', 'price', 'owner', 'branch', 'department', 'used_status', 'asset_type', 'asset_date']
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

    cur.execute('''
        SELECT u.name, d.name as department, u.mobile, u.email
        FROM users u
        JOIN departments d ON u.department_id = d.id
    ''')
    owner_contacts = {
        (row[0], row[1]): {'mobile': row[2] or '', 'email': row[3] or ''}
        for row in cur.fetchall()
    }
    for asset in assets:
        if asset.get('owner') == 'No Owner':
            asset['owner_mobile'] = ''
            asset['owner_email'] = ''
        else:
            contact = owner_contacts.get((asset.get('owner'), asset.get('department')), {})
            asset['owner_mobile'] = contact.get('mobile', '')
            asset['owner_email'] = contact.get('email', '')

    docs_by_asset = list_documents_grouped_by_asset_ids(
        cur, [asset['id'] for asset in assets]
    )
    for asset in assets:
        asset['supporting_documents'] = docs_by_asset.get(asset['id'], [])

    _attach_asset_location_displays(cur, assets)
    
    cur.execute('SELECT used_status, branch, department, price FROM assets')
    chart_data = _compute_chart_data_from_asset_rows(cur.fetchall())
    conn.close()
    
    return render_template('index.html', 
                         assets=assets, 
                         page=page, 
                         total_pages=total_pages, 
                         total_assets=total_assets,
                         per_page=per_page,
                         sort_by=sort_by, 
                         sort_dir=sort_dir, 
                         branches=branches, 
                         departments=departments, 
                         branch_filter=branch_filter, 
                         department_filter=department_filter,
                         search_query=search_query,
                         status_filter=status_filter,
                         asset_type_filter=asset_type_filter,
                         chart_data=chart_data)


def _register_filter_where_from_request():
    """Build WHERE clause + params for active assets list (same rules as dashboard)."""
    args = request.args
    branch_filter = (args.get('branch') or args.get('building') or '').strip()
    department_filter = (args.get('department') or '').strip()
    search_query = (args.get('search') or '').strip()
    status_filter = (args.get('status') or '').strip()
    asset_type_filter = (args.get('asset_type') or '').strip()
    where_clauses = []
    params = []
    if branch_filter:
        where_clauses.append('branch = ?')
        params.append(branch_filter)
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
            'branch LIKE ?',
            'department LIKE ?',
            'asset_type LIKE ?'
        ]
        where_clauses.append(f"({' OR '.join(search_clauses)})")
        search_param = f'%{search_query}%'
        params.extend([search_param] * 6)
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
    return where_sql, params


@assets_bp.route('/matching-register-ids')
@login_required
def matching_register_ids():
    """All active asset ids+names matching current dashboard filters (ignores pagination)."""
    where_sql, params = _register_filter_where_from_request()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f'SELECT id, name, asset_code FROM assets {where_sql} ORDER BY id ASC', params)
    rows = cur.fetchall()
    conn.close()
    assets = [{'id': row[0], 'name': row[1], 'code': row[2] or ''} for row in rows]
    return jsonify({'assets': assets, 'total': len(assets)})


def _archived_filter_where_from_request():
    args = request.args
    search_query = (args.get('search') or '').strip()
    where_clauses = []
    params = []
    if search_query:
        search_clauses = [
            'name LIKE ?',
            'owner LIKE ?',
            'asset_code LIKE ?',
            'branch LIKE ?',
            'department LIKE ?',
            'asset_type LIKE ?',
            'archived_by LIKE ?',
            'archive_reason LIKE ?'
        ]
        where_clauses.append(f"({' OR '.join(search_clauses)})")
        search_param = f'%{search_query}%'
        params.extend([search_param] * 8)
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
    return where_sql, params


@assets_bp.route('/matching-archived-ids')
@login_required
def matching_archived_ids():
    """All archived asset ids+names matching current archive search (ignores pagination)."""
    if not current_user.has_it_access():
        return jsonify({'error': 'Forbidden'}), 403
    where_sql, params = _archived_filter_where_from_request()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f'SELECT id, name FROM archived_assets {where_sql} ORDER BY id ASC', params)
    rows = cur.fetchall()
    conn.close()
    assets = [{'id': row[0], 'name': row[1]} for row in rows]
    return jsonify({'assets': assets, 'total': len(assets)})


_SETTINGS_CHART_DATA = {
    'status_counts': {'Used': 0, 'Not Used': 0, 'Out of Service': 0},
    'branch_counts': {},
    'branch_prices': {},
    'department_counts': {},
    'department_prices': {},
    'total_system_value': 0.0,
}


@assets_bp.route('/settings')
@login_required
def settings():
    if not current_user.has_it_access():
        flash('Access denied. Only IT users can open settings.', 'error')
        return redirect(url_for('assets.dashboard'))
    tab = (request.args.get('tab') or 'users').strip().lower()
    if tab not in ('users', 'branches', 'departments', 'employees', 'assets'):
        tab = 'users'
    auth_users = []
    if tab == 'users':
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT ua.id, ua.email, ua.full_name, ua.role, ua.created_at
            FROM users_auth ua
            ORDER BY ua.created_at DESC
            '''
        )
        auth_users = cur.fetchall()
        conn.close()
    return render_template(
        'settings.html',
        active_tab=tab,
        users=auth_users,
        chart_data=_SETTINGS_CHART_DATA,
    )


@assets_bp.route('/add', methods=['POST'])
@login_required
def add_asset():
    selected_asset_names = request.form.get('selected_asset_names', '')
    asset_type = request.form.get('asset_type', '')
    asset_kind = _parse_asset_kind(request.form.get('asset_kind'))
    owner = request.form.get('owner', '')
    venue = (request.form.get('asset_venue') or 'restaurant').strip().lower()
    price_raw = (request.form.get('price') or '').strip()
    try:
        price = float(price_raw) if price_raw else 0.0
    except ValueError:
        flash('Invalid price.', 'error')
        return redirect(url_for('assets.dashboard'))
    used_status = request.form.get('used_status', 'Not Used')
    no_owner = request.form.get('no_owner') == 'on'
    asset_date = _parse_asset_date(request.form.get('asset_date'))

    if no_owner:
        owner = 'No Owner'

    if venue == 'office':
        department = request.form.get('department', '')
        branch_names = [OFFICE_BRANCH_LABEL]
        # Office has no multi-branch concept; treat as branch asset.
        asset_kind = ASSET_KIND_BRANCH
    else:
        department = _normalize_restaurant_area(request.form.get('department', '')) or ''
        if asset_kind == ASSET_KIND_SHARED:
            branch_names = [
                (b or '').strip()
                for b in request.form.getlist('branch')
                if (b or '').strip()
            ]
            # Deduplicate while preserving order
            seen = set()
            unique_branches = []
            for b in branch_names:
                if b not in seen:
                    seen.add(b)
                    unique_branches.append(b)
            branch_names = unique_branches
        else:
            single_branch = (request.form.get('branch') or request.form.get('building') or '').strip()
            branch_names = [single_branch] if single_branch else []

    asset_names = [name.strip() for name in selected_asset_names.split(',') if name.strip()]

    if not asset_names:
        return redirect(url_for('assets.dashboard'))

    if venue == 'restaurant' and not department:
        flash('Please select a restaurant area (Kitchen, Dining, Cashier, etc.).', 'error')
        return redirect(url_for('assets.dashboard'))

    if venue == 'restaurant' and not branch_names:
        flash('Please select at least one branch.', 'error')
        return redirect(url_for('assets.dashboard'))

    if venue == 'restaurant' and asset_kind == ASSET_KIND_SHARED and len(branch_names) < 1:
        flash('Shared assets require at least one branch.', 'error')
        return redirect(url_for('assets.dashboard'))

    spec_values_by_name = _parse_asset_spec_values_json(request.form.get('asset_spec_values_json', ''))
    if spec_values_by_name is None:
        flash('Invalid asset specification data.', 'error')
        return redirect(url_for('assets.dashboard'))

    inclusion_values_by_name = _parse_asset_inclusion_values_json(request.form.get('asset_inclusion_values_json', ''))
    if inclusion_values_by_name is None:
        flash('Invalid asset inclusion data.', 'error')
        return redirect(url_for('assets.dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()

    if asset_type:
        cur.execute('SELECT for_venue FROM asset_types WHERE name = ?', (asset_type,))
        vt_rows = cur.fetchall()
        if not vt_rows:
            conn.close()
            flash('Invalid asset category.', 'error')
            return redirect(url_for('assets.dashboard'))
        if not any(asset_type_for_venue_matches(r[0], venue) for r in vt_rows):
            conn.close()
            flash('Asset category does not match Restaurant / Office selection.', 'error')
            return redirect(url_for('assets.dashboard'))

    for branch in branch_names:
        err = _validate_asset_venue_location(cur, venue, branch, department)
        if err:
            conn.close()
            flash(err, 'error')
            return redirect(url_for('assets.dashboard'))

    created_asset_ids = []
    shared_group_id = str(uuid.uuid4()) if asset_kind == ASSET_KIND_SHARED and venue == 'restaurant' else None

    for branch in branch_names:
        for asset_name in asset_names:
            asset_id = _upsert_asset_row(
                cur, asset_name, price, owner, branch, department, used_status, asset_type, asset_kind,
                shared_group_id=shared_group_id,
                asset_date=asset_date,
            )
            created_asset_ids.append(asset_id)
            _save_spec_values_for_asset(cur, asset_id, asset_name, asset_type, spec_values_by_name)
            _save_inclusion_values_for_asset(cur, asset_id, asset_name, asset_type, inclusion_values_by_name)

    uploaded_files = request.files.getlist('supporting_documents')
    if uploaded_files and created_asset_ids:
        unique_ids = list(dict.fromkeys(created_asset_ids))
        _, doc_err = save_uploaded_files_for_assets(cur, unique_ids, uploaded_files)
        if doc_err:
            conn.rollback()
            conn.close()
            flash(doc_err, 'error')
            return redirect(url_for('assets.dashboard'))

    conn.commit()
    conn.close()
    return redirect(url_for('assets.dashboard'))

@assets_bp.route('/<int:asset_id>/spec-values', methods=['GET'])
@login_required
def get_asset_spec_values(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT asv.spec_field_id, asv.value, sf.label
        FROM asset_spec_values asv
        JOIN asset_name_spec_fields sf ON sf.id = asv.spec_field_id
        WHERE asv.asset_id = ?
        ORDER BY sf.sort_order, sf.id
        ''',
        (asset_id,),
    )
    values = [
        {'spec_field_id': row[0], 'value': row[1], 'label': row[2]}
        for row in cur.fetchall()
    ]
    cur.execute(
        'SELECT inclusion_id FROM asset_inclusion_values WHERE asset_id = ?',
        (asset_id,),
    )
    inclusion_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return jsonify({'values': values, 'inclusion_ids': inclusion_ids})

@assets_bp.route('/update/<int:asset_id>', methods=['POST'])
@login_required
def update_asset(asset_id):
    name = request.form['name']
    asset_type = request.form.get('asset_type', '')
    asset_kind = _parse_asset_kind(request.form.get('asset_kind'))
    owner = request.form.get('owner', '')
    branch = request.form.get('branch') or request.form.get('building')
    venue = (request.form.get('asset_venue') or 'restaurant').strip().lower()
    if venue == 'office':
        department = request.form.get('department', '')
        asset_kind = ASSET_KIND_BRANCH
    else:
        department = _normalize_restaurant_area(request.form.get('department', '')) or ''
    price_raw = (request.form.get('price') or '').strip()
    try:
        price = float(price_raw) if price_raw else 0.0
    except ValueError:
        return jsonify({'error': 'Invalid price.'}), 400
    used_status = request.form.get('used_status', 'Not Used')
    no_owner = request.form.get('no_owner') == 'on'

    if no_owner:
        owner = 'No Owner'

    if venue == 'office':
        branch = OFFICE_BRANCH_LABEL
    
    conn = get_db_connection()
    cur = conn.cursor()

    err = _validate_asset_venue_location(cur, venue, branch, department)
    if err:
        conn.close()
        return jsonify({'error': err}), 400

    if asset_type:
        cur.execute('SELECT for_venue FROM asset_types WHERE name = ?', (asset_type,))
        vt_rows = cur.fetchall()
        if not vt_rows:
            conn.close()
            return jsonify({'error': 'Invalid asset category.'}), 400
        if not any(asset_type_for_venue_matches(r[0], venue) for r in vt_rows):
            conn.close()
            return jsonify({'error': 'Asset category does not match Restaurant / Office selection.'}), 400

    spec_values = _parse_asset_spec_values_json(request.form.get('asset_spec_values_json', ''))
    if spec_values is None:
        conn.close()
        return jsonify({'error': 'Invalid asset specification data.'}), 400
    spec_err = _validate_spec_values_for_single_asset(cur, asset_type, name, spec_values)
    if spec_err:
        conn.close()
        return jsonify({'error': spec_err}), 400

    inclusion_ids = _parse_inclusion_ids_list_json(request.form.get('asset_inclusion_values_json', ''))
    if inclusion_ids is None:
        conn.close()
        return jsonify({'error': 'Invalid asset inclusion data.'}), 400
    
    try:
        # Get current asset data to check if branch or department changed
        cur.execute('SELECT branch, department, asset_code FROM assets WHERE id=?', (asset_id,))
        current_asset = cur.fetchone()
        
        if not current_asset:
            conn.close()
            return jsonify({'error': 'Asset not found'}), 404
        
        current_branch = current_asset['branch']
        current_department = current_asset['department']
        current_asset_code = current_asset['asset_code']
        
        # Check if branch or department has changed
        branch_changed = current_branch != branch
        department_changed = current_department != department
        
        # Generate new asset code if branch or department changed
        new_asset_code = current_asset_code
        if branch_changed or department_changed:
            new_asset_code = generate_asset_code(branch, department, cur=cur)
            print(f"Asset code updated: {current_asset_code} -> {new_asset_code}")
        
        # Update the asset with new asset code if needed
        cur.execute('''
            UPDATE assets 
            SET name=?, asset_type=?, asset_kind=?, price=?, owner=?, branch=?, department=?, used_status=?, asset_code=?
            WHERE id=?
        ''', (name, asset_type, asset_kind, price, owner, branch, department, used_status, new_asset_code, asset_id))

        _save_spec_values_for_single_asset(cur, asset_id, name, asset_type, spec_values)
        _save_inclusion_values_for_single_asset(cur, asset_id, name, asset_type, inclusion_ids)

        uploaded_files = request.files.getlist('supporting_documents')
        if uploaded_files:
            _, doc_err = save_uploaded_files_for_assets(cur, [asset_id], uploaded_files)
            if doc_err:
                conn.rollback()
                conn.close()
                return jsonify({'error': doc_err}), 400
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'asset_code_changed': branch_changed or department_changed,
            'old_asset_code': current_asset_code,
            'new_asset_code': new_asset_code
        })
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500


@assets_bp.route('/<int:asset_id>/documents', methods=['GET'])
@login_required
def get_asset_documents(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id FROM assets WHERE id = ?', (asset_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({'error': 'Asset not found'}), 404
    docs = list_documents_for_asset(cur, asset_id)
    conn.close()
    return jsonify({'documents': docs})


@assets_bp.route('/<int:asset_id>/documents', methods=['POST'])
@login_required
def upload_asset_documents(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id FROM assets WHERE id = ?', (asset_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({'error': 'Asset not found'}), 404
    uploaded_files = request.files.getlist('supporting_documents')
    if not uploaded_files:
        conn.close()
        return jsonify({'error': 'No files selected.'}), 400
    _, doc_err = save_uploaded_files_for_assets(cur, [asset_id], uploaded_files)
    if doc_err:
        conn.rollback()
        conn.close()
        return jsonify({'error': doc_err}), 400
    docs = list_documents_for_asset(cur, asset_id)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'documents': docs})


@assets_bp.route('/<int:asset_id>/documents/<int:document_id>', methods=['DELETE', 'POST'])
@login_required
def delete_asset_document(asset_id, document_id):
    # Allow POST with _method=DELETE for broader client support
    if request.method == 'POST' and (request.form.get('_method') or '').upper() != 'DELETE':
        # Still allow plain POST delete for simplicity from fetch
        pass
    conn = get_db_connection()
    cur = conn.cursor()
    if not delete_document_record(cur, asset_id, document_id):
        conn.close()
        return jsonify({'error': 'Document not found'}), 404
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@assets_bp.route('/<int:asset_id>/documents/<int:document_id>/download', methods=['GET'])
@login_required
def download_asset_document(asset_id, document_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT original_filename, stored_filename, content_type
        FROM asset_documents
        WHERE id = ? AND asset_id = ?
        ''',
        (document_id, asset_id),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        abort(404)
    path = document_path(row[1])
    if not path.is_file():
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name=row[0],
        mimetype=row[2] or 'application/octet-stream',
    )


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
        (original_id, name, price, owner, branch, department, asset_code, qr_random_code, used_status, asset_type, asset_kind, shared_group_id, asset_date, archived_by, archive_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        asset['id'], asset['name'], asset['price'] if asset['price'] is not None else 0.0, asset['owner'], 
        asset['branch'], asset['department'], asset['asset_code'], 
        asset['qr_random_code'], asset['used_status'], asset['asset_type'],
        asset['asset_kind'] if asset['asset_kind'] else ASSET_KIND_BRANCH,
        asset['shared_group_id'] if 'shared_group_id' in asset.keys() else None,
        asset['asset_date'] if 'asset_date' in asset.keys() else None,
        current_user.display_name, archive_reason
    ))

    delete_all_documents_for_assets(cur, [asset_id])
    
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
    
    try:
        # Get all assets to be deleted
        placeholders = ','.join(['?'] * len(asset_ids))
        cur.execute(f'SELECT * FROM assets WHERE id IN ({placeholders})', asset_ids)
        assets = cur.fetchall()
        
        if not assets:
            conn.close()
            return jsonify({'error': 'No valid assets found to archive'}), 404
        
        # Insert into archived_assets table
        for asset in assets:
            cur.execute('''
                INSERT INTO archived_assets 
                (original_id, name, price, owner, branch, department, asset_code, qr_random_code, used_status, asset_type, asset_kind, shared_group_id, asset_date, archived_by, archive_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                asset['id'], asset['name'], asset['price'] if asset['price'] is not None else 0.0, asset['owner'], 
                asset['branch'], asset['department'], asset['asset_code'], 
                asset['qr_random_code'], asset['used_status'], asset['asset_type'],
                asset['asset_kind'] if asset['asset_kind'] else ASSET_KIND_BRANCH,
                asset['shared_group_id'] if 'shared_group_id' in asset.keys() else None,
                asset['asset_date'] if 'asset_date' in asset.keys() else None,
                current_user.display_name, archive_reason
            ))

        delete_all_documents_for_assets(cur, [a['id'] for a in assets])
        
        # Delete from assets table
        cur.execute(f'DELETE FROM assets WHERE id IN ({placeholders})', asset_ids)
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'archived': len(assets), 'message': f'Successfully archived {len(assets)} assets'})
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Failed to archive assets: {str(e)}'}), 500

def _png_qr_for_string(link_url):
    """Render link_url as a compact black-on-white PNG (shared by image + print views)."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=3,
        border=1,
    )
    qr.add_data(link_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white')
    buf = BytesIO()
    qr_img.save(buf, format='PNG')
    return buf.getvalue()


def _png_bytes_asset_qrcode(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT asset_code FROM assets WHERE id=?', (asset_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row['asset_code']:
        return None
    base_url = request.host_url.rstrip('/')
    target = f"{base_url}/asset/{row['asset_code']}"
    return _png_qr_for_string(target)


def _png_bytes_department_qrcode(decoded_branch, decoded_department):
    base_url = request.host_url.rstrip('/')
    target = f"{base_url}/assets/department_items/{decoded_branch}/{decoded_department}"
    return _png_qr_for_string(target)


def _png_data_uri(png_bytes):
    return 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii')


@assets_bp.route('/qrcode/<int:asset_id>')
def qrcode_image(asset_id):
    """Generate simple QR code for a specific asset"""
    png = _png_bytes_asset_qrcode(asset_id)
    if not png:
        abort(404)
    return send_file(BytesIO(png), mimetype='image/png')


@assets_bp.route('/department_qr/<branch>/<department>')
def department_qrcode_image(branch, department):
    """Generate simple QR code for department items"""
    from urllib.parse import unquote

    branch = unquote(branch)
    department = unquote(department)
    png = _png_bytes_department_qrcode(branch, department)
    return send_file(BytesIO(png), mimetype='image/png')

@assets_bp.route('/department_items/<branch>/<department>')
def department_items(branch, department):
    # Decode URL-encoded parameters
    from urllib.parse import unquote
    branch = unquote(branch)
    department = unquote(department)
    
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', '')
    per_page = int(request.args.get('per_page', 10))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Build WHERE clause
    where_clauses = ['branch = ?', 'department = ?']
    params = [branch, department]
    
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
    cur.execute(f'SELECT SUM(price) FROM assets {where_sql}', params)
    total_department_value = cur.fetchone()[0] or 0.0
    
    conn.close()
    
    if rows:
        assets = [dict(zip(columns, row)) for row in rows]
    else:
        assets = []
    
    return render_template('department_items.html', 
                         assets=assets, 
                         branch=branch, 
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
            'branch': asset['branch'],
            'department': asset['department'],
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
            'branch': asset['branch'],
            'department': asset['department'],
            'used_status': asset.get('used_status', 'Not Used')
        })
    return jsonify({'error': 'Not found'}), 404

@assets_bp.route('/archived_qrcode/<int:archived_id>')
def archived_qrcode_image(archived_id):
    """Generate simple QR code for a specific archived asset"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT asset_code FROM archived_assets WHERE id=?', (archived_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row['asset_code']:
        abort(404)
    
    # Create URL for the asset
    base_url = request.host_url.rstrip('/')
    qr_url = f"{base_url}/asset/{row['asset_code']}"
    
    # Create simple QR code with compact pattern for printing
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=3,
        border=1
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    
    # Generate simple QR code image in black and white
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
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
    cur.execute('SELECT id, name, branch, department, asset_code FROM assets')
    assets = [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]
    conn.close()
    return jsonify(assets) 

@assets_bp.route('/price-analysis')
@login_required
def price_analysis():
    if not current_user.has_it_access():
        flash('Access denied. Only IT users can view price analysis.', 'error')
        return redirect(url_for('assets.dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM assets ORDER BY branch ASC, department ASC, name ASC')
    assets = [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]
    chart_data = _compute_chart_data_from_asset_rows(assets)
    conn.close()

    return render_template(
        'price_analysis.html',
        assets=assets,
        chart_data=chart_data,
        total_assets=len(assets),
        branch_count=len(chart_data['branch_counts']),
        department_count=len(chart_data['department_counts']),
    )


@assets_bp.route('/archive')
@login_required
def archive():
    if not current_user.has_it_access():
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
            'branch LIKE ?',
            'department LIKE ?',
            'asset_type LIKE ?',
            'archived_by LIKE ?',
            'archive_reason LIKE ?'
        ]
        where_clauses.append(f"({' OR '.join(search_clauses)})")
        search_param = f'%{search_query}%'
        params.extend([search_param] * 8)
    
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
    valid_sort_fields = ['id', 'name', 'owner', 'branch', 'department', 'used_status', 'asset_type', 'archived_at', 'archived_by']
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
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can restore assets.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get the archived asset data
    cur.execute('SELECT * FROM archived_assets WHERE id=?', (archived_id,))
    archived_asset = cur.fetchone()
    
    if not archived_asset:
        conn.close()
        return jsonify({'error': 'Archived asset not found'}), 404
    
    try:
        # Check if an asset with the same asset code already exists
        cur.execute('SELECT id FROM assets WHERE asset_code=?', (archived_asset['asset_code'],))
        existing_asset_by_code = cur.fetchone()
        
        if existing_asset_by_code:
            # Asset code already exists, update the existing asset
            cur.execute(
                'UPDATE assets SET used_status=?, asset_type=?, asset_kind=?, shared_group_id=?, price=? WHERE id=?',
                (
                    archived_asset['used_status'],
                    archived_asset['asset_type'],
                    archived_asset['asset_kind'] if archived_asset['asset_kind'] else ASSET_KIND_BRANCH,
                    archived_asset['shared_group_id'] if 'shared_group_id' in archived_asset.keys() else None,
                    archived_asset['price'] if archived_asset['price'] is not None else 0.0,
                    existing_asset_by_code[0],
                ),
            )
        else:
            # Create new asset with original asset code
            asset_code = archived_asset['asset_code']  # Use the original asset code
            qr_random_code = archived_asset['qr_random_code'] if archived_asset['qr_random_code'] else str(uuid.uuid4())
            cur.execute('''
                INSERT INTO assets (name, price, owner, branch, department, asset_code, qr_random_code, used_status, asset_type, asset_kind, shared_group_id, asset_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                    archived_asset['name'], archived_asset['price'] if archived_asset['price'] is not None else 0.0, archived_asset['owner'],
                    archived_asset['branch'], archived_asset['department'], asset_code, qr_random_code,
                    archived_asset['used_status'], archived_asset['asset_type'],
                    archived_asset['asset_kind'] if archived_asset['asset_kind'] else ASSET_KIND_BRANCH,
                    archived_asset['shared_group_id'] if 'shared_group_id' in archived_asset.keys() else None,
                    archived_asset['asset_date'] if 'asset_date' in archived_asset.keys() else None,
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
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can restore assets.'}), 403
    
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
            
            # Check if an asset with the same asset code already exists
            cur.execute('SELECT id FROM assets WHERE asset_code=?', (archived_asset['asset_code'],))
            existing_asset_by_code = cur.fetchone()
            
            if existing_asset_by_code:
                # Asset code already exists, update the existing asset
                cur.execute(
                    'UPDATE assets SET used_status=?, asset_type=?, asset_kind=?, shared_group_id=?, price=? WHERE id=?',
                    (
                        archived_asset['used_status'],
                        archived_asset['asset_type'],
                        archived_asset['asset_kind'] if archived_asset['asset_kind'] else ASSET_KIND_BRANCH,
                        archived_asset['shared_group_id'] if 'shared_group_id' in archived_asset.keys() else None,
                        archived_asset['price'] if archived_asset['price'] is not None else 0.0,
                        existing_asset_by_code[0],
                    ),
                )
            else:
                # Create new asset with original asset code
                asset_code = archived_asset['asset_code']  # Use the original asset code
                qr_random_code = archived_asset['qr_random_code'] if archived_asset['qr_random_code'] else str(uuid.uuid4())
                cur.execute('''
                    INSERT INTO assets (name, price, owner, branch, department, asset_code, qr_random_code, used_status, asset_type, asset_kind, shared_group_id, asset_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                        archived_asset['name'], archived_asset['price'] if archived_asset['price'] is not None else 0.0, archived_asset['owner'],
                        archived_asset['branch'], archived_asset['department'], asset_code, qr_random_code,
                        archived_asset['used_status'], archived_asset['asset_type'],
                        archived_asset['asset_kind'] if archived_asset['asset_kind'] else ASSET_KIND_BRANCH,
                        archived_asset['shared_group_id'] if 'shared_group_id' in archived_asset.keys() else None,
                        archived_asset['asset_date'] if 'asset_date' in archived_asset.keys() else None,
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
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can permanently delete assets.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get the archived asset data for confirmation
    cur.execute('SELECT name, branch, department FROM archived_assets WHERE id=?', (archived_id,))
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
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can permanently delete assets.'}), 403
    
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

@assets_bp.route('/get-all-assets-for-export')
@login_required
def get_all_assets_for_export():
    """Get all assets for export functionality"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all assets with their details
        cur.execute('''
            SELECT name, asset_code, branch, department, price, used_status, asset_type, asset_kind, owner
            FROM assets 
            ORDER BY branch, department, name
        ''')
        all_assets = cur.fetchall()
        
        # Convert to list of dictionaries
        assets_list = []
        for asset in all_assets:
            name, asset_code, branch, department, price, status, asset_type, asset_kind, owner = asset
            assets_list.append({
                'name': name,
                'asset_code': asset_code,
                'branch': branch,
                'department': department,
                'price': price or 0.0,
                'used_status': status or 'Not Specified',
                'asset_type': asset_type or 'Not Specified',
                'asset_kind': asset_kind or ASSET_KIND_BRANCH,
                'owner': owner or 'Not Specified'
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'assets': assets_list
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# --- QR label print (software-defined layout; printer does not choose positions) ---
#
# Contract (same idea as calibrated cheque prints):
#   • Label outer size comes from SQLite (label_width_mm × label_height_mm), e.g. label_2x2 = 50.8 × 50.8 mm.
#   • Every element uses explicit coordinates in mm: QR (qr_x_mm, qr_y_mm, qr_size_mm), text anchors and tops,
#     fonts, max widths. Insets/margins are those numbers—not driver "center on page" or similar.
#   • The print HTML sets @page { size: <w>mm <h>mm; margin: 0 } and position:absolute mm styles on QR and
#     text inside a matching mm-sized .label-page. The printer should faithfully reproduce geometry at 100%
#     scale / paper that matches @page (see qr_label_print.html banner).
#
# QR images use data: URIs so print never waits on a separate fetch
# (fixes blank labels when autoprint fires before images load or when absolute URLs mismatch the browser host).

def _nocache(html_str):
    """Print views must never be reused from disk cache (stale layouts look like preview ≠ paper)."""
    resp = make_response(html_str)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def _float_or(layout, key, default=0.0):
    v = layout.get(key)
    if v is None:
        return float(default)
    return float(v)


def _effective_qr_width_mm(layout, qr_px_raw):
    ref = layout.get('qr_reference_px') or 80
    try:
        px = float(qr_px_raw)
    except (TypeError, ValueError):
        px = float(ref)
    if px <= 0:
        px = float(ref)
    return float(layout['qr_size_mm']) * px / float(ref)


def _text_box_style(anchor_x_mm, top_mm, font_pt, box_width_mm, align):
    """
    Position text in millimetres — same units as @page size for this label.
    Keeps paper output aligned with the on-screen preview (some pipelines skew inch vs mm).

    anchor_x_mm: center x for align=center, right edge x for align=right, left x for align=left.
    """
    mx = float(box_width_mm)
    top = float(top_mm)
    fp = float(font_pt)
    ax = float(anchor_x_mm)

    sizing = (
        f'width:{mx:.3f}mm;max-width:{mx:.3f}mm;'
        f'box-sizing:border-box;font-size:{fp:.2f}pt;top:{top:.3f}mm;'
    )

    if align == 'center':
        left_edge_mm = max(0.0, ax - mx / 2.0)
        return f'left:{left_edge_mm:.3f}mm;{sizing}text-align:center;'
    if align == 'right':
        left_edge_mm = max(0.0, ax - mx)
        return f'left:{left_edge_mm:.3f}mm;{sizing}text-align:right;'
    left_edge_mm = max(0.0, ax)
    return f'left:{left_edge_mm:.3f}mm;{sizing}text-align:left;'


def _layout_class_align(align):
    return {'center': 'ta-c', 'left': 'ta-l', 'right': 'ta-r'}.get(align, 'ta-l')


def _compose_qr_rows(layout, qr_px, items):
    """
    Build one label row per item: absolute mm positions derived only from layout (DB) + print_offset_* fields.

    The printer/OS must not infer QR or text placement; these inline styles are the single source of truth.
    items = list of (qr_abs_url, primary, secondary).
    """
    lw = float(layout['label_width_mm'])
    lh = float(layout['label_height_mm'])

    fqrx = _float_or(layout, 'print_offset_qr_x_mm')
    fqry = _float_or(layout, 'print_offset_qr_y_mm')
    fpx = _float_or(layout, 'print_offset_primary_x_mm')
    fpy = _float_or(layout, 'print_offset_primary_y_mm')
    fsx = _float_or(layout, 'print_offset_secondary_x_mm')
    fsy = _float_or(layout, 'print_offset_secondary_y_mm')

    qr_w = _effective_qr_width_mm(layout, qr_px)

    qr_left = float(layout['qr_x_mm']) + fqrx
    qr_top = float(layout['qr_y_mm']) + fqry

    pmw_layout = layout.get('primary_text_max_width_mm')
    smw_layout = layout.get('secondary_text_max_width_mm')
    pmw = float(pmw_layout) if pmw_layout is not None else max(lw - 4.0, 4.0)
    smw = float(smw_layout) if smw_layout is not None else max(lw - 4.0, 4.0)

    primary_top = float(layout['primary_text_y_mm']) + fpy
    secondary_top = float(layout['secondary_text_y_mm']) + fsy

    # Horizontal: when primary/secondary share the same x anchor (usual case), derive that anchor
    # from the *rendered* QR center so print matches QR even if DB text columns were never migrated.
    ptx_mm = float(layout['primary_text_x_mm'])
    stx_mm = float(layout['secondary_text_x_mm'])
    qty_center_x = qr_left + qr_w / 2.0
    if abs(ptx_mm - stx_mm) < 0.2:
        primary_left = qty_center_x + fpx
        secondary_left = qty_center_x + fsx
    else:
        primary_left = ptx_mm + fpx
        secondary_left = stx_mm + fsx

    primary_align = (layout.get('primary_text_align') or 'center').lower()
    secondary_align = (layout.get('secondary_text_align') or 'center').lower()

    page_outer_style = f'width:{lw:.3f}mm;height:{lh:.3f}mm;'

    rows = []
    for qr_src, primary_text, secondary_text in items:
        qr_style = (
            f'left:{qr_left:.3f}mm;top:{qr_top:.3f}mm;'
            f'width:{qr_w:.3f}mm;height:{qr_w:.3f}mm;'
        )
        rows.append({
            'page_outer_style': page_outer_style,
            'qr_src': qr_src,
            'qr_style': qr_style,
            'primary_style': _text_box_style(
                primary_left, primary_top, layout['primary_font_pt'], pmw, primary_align,
            ),
            'secondary_style': _text_box_style(
                secondary_left, secondary_top, layout['secondary_font_pt'], smw, secondary_align,
            ),
            'primary_text': primary_text or '',
            'secondary_text': secondary_text or '',
            'primary_cls': _layout_class_align(primary_align),
            'secondary_cls': _layout_class_align(secondary_align),
        })
    return rows


def _render_qr_label_html(
    conn,
    preset_key,
    qr_px,
    items,
    autoprint=False,
    preview_outline=False,
    page_css_extra='',
    show_debug=False,
):
    """Render print HTML whose @page and absolute mm coords match SQLite layout (printer does not place elements)."""
    layout = get_qr_label_layout_dict(conn, preset_key)
    if not layout:
        return None
    rows = _compose_qr_rows(layout, qr_px, items)
    lw = float(layout['label_width_mm'])
    lh = float(layout['label_height_mm'])

    std_2in_mm = 50.8  # exact 2"
    square_2x2_label = (
        abs(lw - std_2in_mm) < 0.35
        and abs(lh - std_2in_mm) < 0.35
        and abs(lw - lh) < 0.35
    )
    # @page + root sizing in **mm** only. Mixing 2in wrappers with mm-positioned children caused blank
    # raster output on some Windows thermal/GDI stacks; max-height + overflow:hidden also clipped the job.
    #
    # Single label: root min-height = one sticker (thermal-friendly). Bulk (N>1): do **not** set
    # html/body min-height to N×label — some print stacks treat that as one off-page strip → blank feeds.
    n_rows = max(1, len(rows))
    total_doc_h_mm = lh * float(n_rows)
    page_size = f'{lw:.3f}mm {lh:.3f}mm'
    doc_w_css = f'{lw:.3f}mm'
    doc_h_css = f'{total_doc_h_mm:.3f}mm'
    lab_w_css = f'{lw:.3f}mm'
    lab_h_css = f'{lh:.3f}mm'
    if n_rows <= 1:
        root_block_v = f'''min-height: {doc_h_css} !important;
    height: auto !important;'''
    else:
        root_block_v = '''min-height: unset !important;
    height: auto !important;'''

    sheet = f'@page {{ margin: 0 !important; size: {page_size}; }}'
    # Avoid break-before/avoid-page on first/last — several thermal/GDI stacks emit an extra blank
    # or “outline only” page between stickers. One label per sheet: page-break-after always except last.
    print_frame_rules = f'''
@media print {{
  @page {{
    margin: 0 !important;
    size: {page_size} !important;
  }}
  html {{
    margin: 0 !important;
    padding: 0 !important;
    width: {doc_w_css} !important;
    {root_block_v}
    max-width: {doc_w_css} !important;
    background: #fff !important;
    box-sizing: border-box !important;
    overflow: visible !important;
  }}
  body {{
    margin: 0 !important;
    padding: 0 !important;
    width: {doc_w_css} !important;
    {root_block_v}
    max-width: {doc_w_css} !important;
    background: #fff !important;
    box-sizing: border-box !important;
    overflow: visible !important;
  }}
  #label-stack {{
    margin: 0 !important;
    padding: 0 !important;
    width: {doc_w_css} !important;
    {root_block_v}
    overflow: visible !important;
    box-sizing: border-box !important;
  }}
  .label-page {{
    width: {lab_w_css} !important;
    height: {lab_h_css} !important;
    max-width: {lab_w_css} !important;
    max-height: {lab_h_css} !important;
    min-width: {lab_w_css} !important;
    min-height: {lab_h_css} !important;
    margin: 0 !important;
    padding: 0 !important;
    position: relative !important;
    overflow: visible !important;
    box-sizing: border-box !important;
    break-inside: avoid !important;
    page-break-inside: avoid !important;
    page-break-after: always !important;
  }}
  /* :last-child misses last <section> when #label-stack has trailing whitespace text nodes */
  .label-page:last-of-type {{
    page-break-after: auto !important;
  }}
}}
'''

    if autoprint:
        if n_rows <= 1:
            autoprint_delay_ms = 850
        else:
            autoprint_delay_ms = min(5000, 700 + 220 * n_rows)
    else:
        autoprint_delay_ms = 200

    combined_css = sheet + '\n' + print_frame_rules + '\n' + (page_css_extra or '')
    return render_template(
        'qr_label_print.html',
        rows=rows,
        autoprint=autoprint,
        autoprint_delay_ms=autoprint_delay_ms,
        label_count=n_rows,
        preview_outline=preview_outline,
        page_css_extra=combined_css,
        show_debug=show_debug,
        layout_preset=preset_key,
        layout_mm=(lw, lh),
        print_paper_hint_2in2=square_2x2_label,
    )


@assets_bp.route('/api/qr-label-layout/<preset_key>', methods=('GET', 'PUT', 'PATCH'))
@login_required
def api_qr_label_layout(preset_key):
    if request.method == 'GET':
        conn = get_db_connection()
        layout = get_qr_label_layout_dict(conn, preset_key)
        conn.close()
        if not layout:
            return jsonify({'error': 'Unknown preset', 'layout': None}), 404
        return jsonify({'layout': qr_layout_to_api_dict(layout)})

    if not current_user.has_it_access():
        return jsonify({'error': 'Forbidden'}), 403
    body = request.get_json(silent=True) or {}
    conn = get_db_connection()
    updated = upsert_qr_label_layout_updates(conn, preset_key, body)
    conn.close()
    if not updated:
        return jsonify({'error': 'Preset not found', 'layout': None}), 404
    return jsonify({'success': True, 'layout': qr_layout_to_api_dict(updated)})


@assets_bp.route('/qr-label-print/asset')
@login_required
def qr_label_print_asset():
    autoprint = request.args.get('print', '1') != '0'
    preview_out = request.args.get('preview', '0') == '1'
    show_debug = request.args.get('debug', '0') == '1'

    preset = request.args.get('preset', '').strip()
    asset_id_raw = request.args.get('asset_id')
    qr_px_raw = request.args.get('qr_px', '80')

    if not preset:
        preset = 'label_2x2'
    try:
        asset_id = int(asset_id_raw)
    except (TypeError, ValueError):
        abort(400)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, asset_code, name FROM assets WHERE id = ?', (asset_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        abort(404)
    cols = [d[0] for d in cur.description]
    asset = dict(zip(cols, row))

    png = _png_bytes_asset_qrcode(asset_id)
    if not png:
        conn.close()
        abort(404)
    items = [(_png_data_uri(png), asset.get('asset_code') or '', asset.get('name') or '')]

    html = _render_qr_label_html(
        conn,
        preset,
        qr_px_raw,
        items,
        autoprint=autoprint,
        preview_outline=preview_out,
        show_debug=show_debug,
    )
    conn.close()
    if not html:
        abort(404)
    return _nocache(html)


@assets_bp.route('/qr-label-print/department')
@login_required
def qr_label_print_department():
    from urllib.parse import unquote

    autoprint = request.args.get('print', '1') != '0'
    preview_out = request.args.get('preview', '0') == '1'
    show_debug = request.args.get('debug', '0') == '1'

    preset = request.args.get('preset', '').strip() or 'label_2x2'
    qr_px_raw = request.args.get('qr_px', '80')
    branch = unquote(request.args.get('branch') or request.args.get('building') or '').strip()
    department = unquote(request.args.get('department') or '').strip()
    if not branch or not department:
        abort(400)

    conn = get_db_connection()
    cur = conn.cursor()
    code = normalize_department_display_code(branch, department, cur=cur)
    secondary = f'{department} - {branch}'

    png = _png_bytes_department_qrcode(branch, department)
    items = [(_png_data_uri(png), code, secondary)]
    html = _render_qr_label_html(
        conn,
        preset,
        qr_px_raw,
        items,
        autoprint=autoprint,
        preview_outline=preview_out,
        show_debug=show_debug,
    )
    conn.close()
    if not html:
        abort(404)
    return _nocache(html)


@assets_bp.route('/qr-label-print/batch', methods=['POST'])
@login_required
def qr_label_print_batch():
    data = request.get_json(silent=True) or {}
    preset = (data.get('preset') or '').strip() or 'label_2x2'
    qr_px_raw = data.get('qr_px', 80)

    autoprint = data.get('autoprint', True)
    preview_out = data.get('preview_outline', False)
    show_debug = bool(data.get('debug', False))
    preview_body = ''
    if preview_out:
        # Screen-only — padding on body in print falsely inflates page height on thermal printers.
        preview_body = '@media screen { body { background: #e8e8e8; padding: 12px 0 0 12px !important; } }'

    items_payload = data.get('items')
    if not isinstance(items_payload, list) or not items_payload:
        return jsonify({'error': 'items (non-empty array) required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    tuples = []

    for block in items_payload:
        kind = (block.get('kind') or '').lower()
        if kind == 'asset':
            aid = int(block['id'])
            cur.execute(
                'SELECT id, asset_code, name FROM assets WHERE id = ?',
                (aid,),
            )
            a = cur.fetchone()
            if not a:
                continue
            png = _png_bytes_asset_qrcode(aid)
            if not png:
                continue
            tuples.append((_png_data_uri(png), a['asset_code'] or '', a['name'] or ''))
        elif kind == 'department':
            b = str(block.get('branch') or block.get('building') or '').strip()
            d = str(block.get('department') or '').strip()
            if not b or not d:
                continue
            code = normalize_department_display_code(b, d, cur=cur)
            secondary = f'{d} - {b}'
            png = _png_bytes_department_qrcode(b, d)
            tuples.append((_png_data_uri(png), code, secondary))
        else:
            continue

    if not tuples:
        conn.close()
        return jsonify({'error': 'No valid entries to print'}), 400

    html = _render_qr_label_html(
        conn,
        preset,
        qr_px_raw,
        tuples,
        autoprint=bool(autoprint),
        preview_outline=bool(preview_out),
        page_css_extra=preview_body,
        show_debug=show_debug,
    )
    conn.close()
    if not html:
        return jsonify({'error': 'Unknown preset'}), 404
    return _nocache(html)