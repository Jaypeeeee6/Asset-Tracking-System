from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.database import (
    get_db_connection,
    ensure_restaurant_default_department_for_branch,
    RESTAURANT_DEFAULT_DEPARTMENT_NAME,
)
from routes.assets import OFFICE_BRANCH_LABEL
import sqlite3

admin_bp = Blueprint('admin', __name__)

# ===== BRAND MANAGEMENT API =====

@admin_bp.route('/brands', methods=['GET'])
@login_required
def get_brands():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM brands ORDER BY name')
    brands = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    conn.close()
    return jsonify(brands)

@admin_bp.route('/brands', methods=['POST'])
@login_required
def add_brand():
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add brands.'}), 403

    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Brand name is required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO brands (name) VALUES (?)', (name,))
        brand_id = cur.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': brand_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Brand name already exists'}), 400

@admin_bp.route('/brands/<int:brand_id>', methods=['PUT'])
@login_required
def update_brand(brand_id):
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can update brands.'}), 403

    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Brand name is required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id FROM brands WHERE id = ?', (brand_id,))
        if not cur.fetchone():
            conn.close()
            return jsonify({'error': 'Brand not found'}), 404
        cur.execute('UPDATE brands SET name = ? WHERE id = ?', (name, brand_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': brand_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Brand name already exists'}), 400

@admin_bp.route('/brands/<int:brand_id>', methods=['DELETE'])
@login_required
def delete_brand(brand_id):
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can delete brands.'}), 403

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT name FROM brands WHERE id = ?', (brand_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Brand not found'}), 404

    cur.execute('SELECT COUNT(*) FROM branches WHERE brand_id = ?', (brand_id,))
    if cur.fetchone()[0] > 0:
        conn.close()
        return jsonify({'error': 'Cannot delete brand while branches are assigned to it.'}), 400

    cur.execute('DELETE FROM brands WHERE id = ?', (brand_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ===== BRANCH MANAGEMENT API =====

@admin_bp.route('/branches', methods=['GET'])
@login_required
def get_branches():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT b.id, b.name, b.brand_id, b.branch_code, br.name AS brand_name
        FROM branches b
        LEFT JOIN brands br ON b.brand_id = br.id
        ORDER BY b.name
        '''
    )
    branches = [
        {
            'id': row[0],
            'name': row[1],
            'brand_id': row[2],
            'branch_code': row[3],
            'brand_name': row[4],
        }
        for row in cur.fetchall()
    ]
    conn.close()
    return jsonify(branches)

@admin_bp.route('/branches', methods=['POST'])
@login_required
def add_branch():
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add branches.'}), 403
    
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Branch name is required'}), 400

    brand_id_raw = request.form.get('brand_id', '').strip()
    if not brand_id_raw:
        return jsonify({'error': 'Brand is required'}), 400
    try:
        brand_id = int(brand_id_raw)
    except ValueError:
        return jsonify({'error': 'Invalid brand'}), 400

    branch_code = request.form.get('branch_code', '').strip().upper() or None
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id FROM brands WHERE id = ?', (brand_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({'error': 'Brand not found'}), 404
    try:
        cur.execute(
            'INSERT INTO branches (name, brand_id, branch_code) VALUES (?, ?, ?)',
            (name, brand_id, branch_code),
        )
        branch_id = cur.lastrowid
        ensure_restaurant_default_department_for_branch(cur, branch_id)
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': branch_id, 'name': name, 'brand_id': brand_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Branch name already exists'}), 400

@admin_bp.route('/branches/<int:branch_id>', methods=['PUT'])
@login_required
def update_branch(branch_id):
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can update branches.'}), 403
    
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Branch name is required'}), 400

    brand_id_raw = (request.form.get('brand_id') or '').strip()
    brand_id = None
    if brand_id_raw:
        try:
            brand_id = int(brand_id_raw)
        except ValueError:
            return jsonify({'error': 'Invalid brand'}), 400

    branch_code = request.form.get('branch_code', '').strip().upper() or None
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT name FROM branches WHERE id = ?', (branch_id,))
        old_row = cur.fetchone()
        if not old_row:
            conn.close()
            return jsonify({'error': 'Branch not found'}), 404
        
        old_name = old_row[0]

        if brand_id is not None:
            cur.execute('SELECT id FROM brands WHERE id = ?', (brand_id,))
            if not cur.fetchone():
                conn.close()
                return jsonify({'error': 'Brand not found'}), 404
            cur.execute(
                'UPDATE branches SET name = ?, brand_id = ?, branch_code = ? WHERE id = ?',
                (name, brand_id, branch_code, branch_id),
            )
        else:
            cur.execute(
                'UPDATE branches SET name = ?, branch_code = ? WHERE id = ?',
                (name, branch_code, branch_id),
            )
        
        cur.execute('UPDATE assets SET branch = ? WHERE branch = ?', (name, old_name))
        cur.execute('UPDATE archived_assets SET branch = ? WHERE branch = ?', (name, old_name))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': branch_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Branch name already exists'}), 400

@admin_bp.route('/branches/<int:branch_id>', methods=['DELETE'])
@login_required
def delete_branch(branch_id):
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can delete branches.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT name FROM branches WHERE id = ?', (branch_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Branch not found'}), 404
    
    branch_name = row[0]
    
    cur.execute('SELECT COUNT(*) FROM assets WHERE branch = ?', (branch_name,))
    asset_count = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM archived_assets WHERE branch = ?', (branch_name,))
    archived_count = cur.fetchone()[0]
    
    if asset_count > 0 or archived_count > 0:
        conn.close()
        total = asset_count + archived_count
        return jsonify({'error': f'Cannot delete branch. It is referenced by {total} record(s) in active or archived assets.'}), 400
    
    cur.execute('DELETE FROM departments WHERE branch_id = ?', (branch_id,))
    cur.execute('DELETE FROM branches WHERE id = ?', (branch_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@admin_bp.route('/import-branches', methods=['POST'])
@login_required
def import_branches():
    """Bulk import brands, branches, and their branch managers (employees) from a parsed Excel file.

    Expects JSON: { "rows": [ {code, name, brand, manager, email}, ... ] }.
    Only rows the client identified as restaurant branches are sent. Existing
    brands/branches/employees are kept (matched by name); missing brand/branch_code
    on an existing branch is backfilled.
    """
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can import branches.'}), 403

    data = request.get_json(silent=True) or {}
    rows = data.get('rows')
    if not isinstance(rows, list) or not rows:
        return jsonify({'error': 'No branch rows found to import. Please check the file.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    summary = {
        'brands_created': 0,
        'branches_created': 0,
        'branches_skipped': 0,
        'employees_created': 0,
        'employees_skipped': 0,
        'errors': [],
    }

    brand_cache = {}

    def get_or_create_brand(brand_name):
        key = brand_name.lower()
        if key in brand_cache:
            return brand_cache[key]
        cur.execute('SELECT id FROM brands WHERE name = ?', (brand_name,))
        found = cur.fetchone()
        if found:
            brand_cache[key] = found[0]
            return found[0]
        cur.execute('INSERT INTO brands (name) VALUES (?)', (brand_name,))
        summary['brands_created'] += 1
        brand_cache[key] = cur.lastrowid
        return cur.lastrowid

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        name = (row.get('name') or '').strip()
        if not name:
            continue
        code = ((row.get('code') or '').strip().upper()) or None
        brand_name = (row.get('brand') or '').strip()
        manager = (row.get('manager') or '').strip()
        email = (row.get('email') or '').strip()

        try:
            brand_id = get_or_create_brand(brand_name) if brand_name else None

            cur.execute('SELECT id, brand_id, branch_code FROM branches WHERE name = ?', (name,))
            existing = cur.fetchone()
            if existing:
                branch_id = existing[0]
                summary['branches_skipped'] += 1
                backfills, params = [], []
                if brand_id and not existing[1]:
                    backfills.append('brand_id = ?')
                    params.append(brand_id)
                if code and not existing[2]:
                    backfills.append('branch_code = ?')
                    params.append(code)
                if backfills:
                    params.append(branch_id)
                    cur.execute('UPDATE branches SET ' + ', '.join(backfills) + ' WHERE id = ?', params)
            else:
                cur.execute(
                    'INSERT INTO branches (name, brand_id, branch_code) VALUES (?, ?, ?)',
                    (name, brand_id, code),
                )
                branch_id = cur.lastrowid
                summary['branches_created'] += 1

            ensure_restaurant_default_department_for_branch(cur, branch_id)

            if manager:
                cur.execute(
                    'SELECT id FROM departments WHERE branch_id = ? AND name = ?',
                    (branch_id, RESTAURANT_DEFAULT_DEPARTMENT_NAME),
                )
                dep = cur.fetchone()
                if dep:
                    dep_id = dep[0]
                    cur.execute(
                        'SELECT id, email FROM users WHERE name = ? AND department_id = ?',
                        (manager, dep_id),
                    )
                    existing_emp = cur.fetchone()
                    if existing_emp:
                        summary['employees_skipped'] += 1
                    else:
                        cur.execute(
                            'INSERT INTO users (name, employee_id, mobile, email, department_id) VALUES (?, ?, ?, ?, ?)',
                            (manager, None, None, email or None, dep_id),
                        )
                        summary['employees_created'] += 1
        except sqlite3.Error as e:
            summary['errors'].append(f'Row {idx + 1} ("{name}"): {str(e)}')

    conn.commit()
    conn.close()
    summary['success'] = True
    return jsonify(summary)


@admin_bp.route('/import-office-employees', methods=['POST'])
@login_required
def import_office_employees():
    """Bulk import employees from a parsed employee-directory Excel file.

    Expects JSON: { "rows": [ {employee_id, name, department, mobile, email, venue, branch_code}, ... ] }.
    The Employees tab may import both office employees and restaurant managers.
    Existing employees are skipped and blank spreadsheet cells stay blank.
    """
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can import employees.'}), 403

    data = request.get_json(silent=True) or {}
    rows = data.get('rows')
    if not isinstance(rows, list) or not rows:
        return jsonify({'error': 'No employee rows found to import. Please check the file.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    summary = {
        'departments_created': 0,
        'office_employees_created': 0,
        'restaurant_employees_created': 0,
        'employees_created': 0,
        'employees_skipped': 0,
        'employees_updated': 0,
        'errors': [],
    }

    dept_cache = {}
    branch_dept_cache = {}

    def get_or_create_office_department(dept_name):
        key = dept_name.lower()
        if key in dept_cache:
            return dept_cache[key]
        cur.execute(
            'SELECT id FROM departments WHERE name = ? AND branch_id IS NULL',
            (dept_name,),
        )
        found = cur.fetchone()
        if found:
            dept_cache[key] = found[0]
            return found[0]
        cur.execute(
            'INSERT INTO departments (name, branch_id) VALUES (?, NULL)',
            (dept_name,),
        )
        summary['departments_created'] += 1
        dept_cache[key] = cur.lastrowid
        return cur.lastrowid

    def optional_text(value):
        text = (value or '').strip()
        return text or None

    def find_restaurant_department(branch_code):
        key = (branch_code or '').strip().upper()
        if not key:
            return None
        if key in branch_dept_cache:
            return branch_dept_cache[key]
        cur.execute(
            '''
            SELECT d.id
            FROM departments d
            JOIN branches b ON d.branch_id = b.id
            WHERE UPPER(COALESCE(b.branch_code, '')) = ? AND d.name = ?
            ''',
            (key, RESTAURANT_DEFAULT_DEPARTMENT_NAME),
        )
        found = cur.fetchone()
        branch_dept_cache[key] = found[0] if found else None
        return branch_dept_cache[key]

    def is_office_department_name(dept_name):
        value = (dept_name or '').strip().lower()
        return value not in ('', 'restaurant', 'muscat', 'al batinah', 'al dakhilia', 'al sharqiah', 'al dhahira', 'office')

    def backfill_employee_rows(existing_rows, new_employee_id, new_mobile, new_email, new_department_id):
        changed = False
        for existing in existing_rows:
            existing_row_id, current_employee_id, current_mobile, current_email, current_department_id = existing
            updates = []
            params = []
            if new_employee_id and not current_employee_id:
                updates.append('employee_id = ?')
                params.append(new_employee_id)
            if new_mobile and not current_mobile:
                updates.append('mobile = ?')
                params.append(new_mobile)
            if new_email and not current_email:
                updates.append('email = ?')
                params.append(new_email)
            if new_department_id and not current_department_id:
                updates.append('department_id = ?')
                params.append(new_department_id)
            if not updates:
                continue
            params.append(existing_row_id)
            cur.execute('UPDATE users SET ' + ', '.join(updates) + ' WHERE id = ?', params)
            changed = True
        return changed

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        name = (row.get('name') or '').strip()
        if not name:
            continue
        department = (row.get('department') or '').strip()
        employee_id = optional_text(row.get('employee_id'))
        mobile = optional_text(row.get('mobile'))
        email = optional_text(row.get('email'))
        venue = ((row.get('venue') or 'office').strip().lower()) or 'office'
        branch_code = optional_text((row.get('branch_code') or '').upper())

        try:
            dep_id = None
            if venue == 'restaurant':
                dep_id = find_restaurant_department(branch_code) if branch_code else None
            elif is_office_department_name(department):
                dep_id = get_or_create_office_department(department)

            if employee_id:
                cur.execute(
                    'SELECT id, employee_id, mobile, email, department_id FROM users WHERE employee_id = ?',
                    (employee_id,),
                )
                existing_rows = cur.fetchall()
                if existing_rows:
                    if backfill_employee_rows(existing_rows, employee_id, mobile, email, dep_id):
                        summary['employees_updated'] += 1
                    summary['employees_skipped'] += 1
                    continue

            if dep_id:
                cur.execute(
                    'SELECT id, employee_id, mobile, email, department_id FROM users WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) AND department_id = ?',
                    (name, dep_id),
                )
                existing_rows = cur.fetchall()
            else:
                existing_rows = []
            if not existing_rows:
                if venue == 'restaurant':
                    cur.execute(
                        '''
                        SELECT u.id, u.employee_id, u.mobile, u.email, u.department_id
                        FROM users u
                        JOIN departments d ON u.department_id = d.id
                        WHERE LOWER(TRIM(u.name)) = LOWER(TRIM(?)) AND d.branch_id IS NOT NULL
                        ''',
                        (name,),
                    )
                else:
                    cur.execute(
                        '''
                        SELECT u.id, u.employee_id, u.mobile, u.email, u.department_id
                        FROM users u
                        LEFT JOIN departments d ON u.department_id = d.id
                        WHERE LOWER(TRIM(u.name)) = LOWER(TRIM(?))
                          AND (u.department_id IS NULL OR d.branch_id IS NULL)
                        ''',
                        (name,),
                    )
                existing_rows = cur.fetchall()
            if not existing_rows:
                cur.execute(
                    'SELECT id, employee_id, mobile, email, department_id FROM users WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))',
                    (name,),
                )
                existing_rows = cur.fetchall()
            if existing_rows:
                if backfill_employee_rows(existing_rows, employee_id, mobile, email, dep_id):
                    summary['employees_updated'] += 1
                summary['employees_skipped'] += 1
                continue

            if venue == 'restaurant' and not dep_id:
                summary['errors'].append(
                    f'Row {idx + 1} ("{name}"): could not determine the restaurant branch/location.'
                )
                continue

            cur.execute(
                'INSERT INTO users (name, employee_id, mobile, email, department_id) '
                'VALUES (?, ?, ?, ?, ?)',
                (name, employee_id, mobile, email, dep_id),
            )
            summary['employees_created'] += 1
            if venue == 'restaurant':
                summary['restaurant_employees_created'] += 1
            else:
                summary['office_employees_created'] += 1
        except sqlite3.Error as e:
            summary['errors'].append(f'Row {idx + 1} ("{name}"): {str(e)}')

    conn.commit()
    conn.close()
    summary['success'] = True
    return jsonify(summary)

# ===== DEPARTMENT MANAGEMENT API =====

@admin_bp.route('/departments', methods=['GET'])
@login_required
def get_departments():
    branch_id = request.args.get('branch_id') or request.args.get('building_id')
    office_only = (request.args.get('office_only') or '').strip().lower() in ('1', 'true', 'yes')
    conn = get_db_connection()
    cur = conn.cursor()

    if office_only:
        cur.execute(
            'SELECT id, name FROM departments WHERE branch_id IS NULL ORDER BY name',
        )
        departments = [
            {'id': row[0], 'name': row[1], 'branch_id': None, 'branch_name': OFFICE_BRANCH_LABEL}
            for row in cur.fetchall()
        ]
        conn.close()
        return jsonify(departments)

    if branch_id:
        cur.execute('SELECT id, name FROM departments WHERE branch_id = ? ORDER BY name', (branch_id,))
        departments = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
        conn.close()
        return jsonify(departments)

    cur.execute(
        '''
        SELECT d.id, d.name, d.branch_id,
               CASE WHEN d.branch_id IS NULL THEN ? ELSE b.name END AS branch_name,
               b.branch_code
        FROM departments d
        LEFT JOIN branches b ON d.branch_id = b.id
        ORDER BY branch_name, d.name
        ''',
        (OFFICE_BRANCH_LABEL,),
    )
    departments = [
        {
            'id': row[0],
            'name': row[1],
            'branch_id': row[2],
            'branch_name': row[3],
            'branch_code': row[4],
        }
        for row in cur.fetchall()
    ]
    conn.close()
    return jsonify(departments)

@admin_bp.route('/departments', methods=['POST'])
@login_required
def add_department():
    # Only IT users (legacy admin-equivalent) can add departments
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add departments.'}), 403
    
    name = request.form.get('name', '').strip()
    branch_id_raw = (request.form.get('branch_id') or request.form.get('building_id') or '').strip()

    if not name:
        return jsonify({'error': 'Department name is required'}), 400

    branch_id = None
    if branch_id_raw:
        try:
            branch_id = int(branch_id_raw)
        except ValueError:
            return jsonify({'error': 'Invalid branch ID'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    if branch_id is not None:
        cur.execute('SELECT id FROM branches WHERE id = ?', (branch_id,))
        if not cur.fetchone():
            conn.close()
            return jsonify({'error': 'Branch not found'}), 404
    try:
        cur.execute('INSERT INTO departments (name, branch_id) VALUES (?, ?)', (name, branch_id))
        department_id = cur.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': department_id, 'name': name, 'branch_id': branch_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'A department with this name already exists in this context'}), 400

@admin_bp.route('/departments/<int:department_id>', methods=['PUT'])
@login_required
def update_department(department_id):
    # Only IT users can update departments
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can update departments.'}), 403
    
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Department name is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            SELECT d.name, CASE WHEN d.branch_id IS NULL THEN ? ELSE b.name END
            FROM departments d
            LEFT JOIN branches b ON d.branch_id = b.id
            WHERE d.id = ?
            ''',
            (OFFICE_BRANCH_LABEL, department_id),
        )
        result = cur.fetchone()
        if not result:
            conn.close()
            return jsonify({'error': 'Department not found'}), 404

        old_name, branch_name = result

        cur.execute('UPDATE departments SET name = ? WHERE id = ?', (name, department_id))

        cur.execute(
            'UPDATE assets SET department = ? WHERE department = ? AND branch = ?',
            (name, old_name, branch_name),
        )
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': department_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'A department with this name already exists in this context'}), 400

@admin_bp.route('/departments/<int:department_id>', methods=['DELETE'])
@login_required
def delete_department(department_id):
    # Only IT users can delete departments
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can delete departments.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(
        '''
        SELECT d.name, CASE WHEN d.branch_id IS NULL THEN ? ELSE b.name END
        FROM departments d
        LEFT JOIN branches b ON d.branch_id = b.id
        WHERE d.id = ?
        ''',
        (OFFICE_BRANCH_LABEL, department_id),
    )
    result = cur.fetchone()
    if not result:
        conn.close()
        return jsonify({'error': 'Department not found'}), 404

    department_name, branch_name = result

    cur.execute('SELECT COUNT(*) FROM assets WHERE department = ? AND branch = ?', (department_name, branch_name))
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

def _employee_group_key(employee_id, name, is_office):
    """Stable key that groups the multiple rows of a single logical employee.

    Employees assigned to several branches are stored as one ``users`` row per
    branch. Rows that share an ``employee_id`` are the same person; rows without
    an employee_id (e.g. imported branch managers) are grouped by name within the
    same venue (restaurant vs office) so a manager of several branches collapses
    into one roster entry.
    """
    if employee_id:
        return 'E:' + str(employee_id)
    return ('O:' if is_office else 'R:') + (name or '').strip().lower()


def _load_employee_group(cur, user_id):
    """Return every ``users`` row belonging to the same logical employee as ``user_id``."""
    cur.execute(
        '''
        SELECT u.id, u.name, u.employee_id, u.department_id, d.name AS dept_name,
               d.branch_id, CASE WHEN u.department_id IS NULL THEN ? ELSE COALESCE(b.name, ?) END AS branch_name
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        LEFT JOIN branches b ON d.branch_id = b.id
        WHERE u.id = ?
        ''',
        (OFFICE_BRANCH_LABEL, OFFICE_BRANCH_LABEL, user_id),
    )
    base = cur.fetchone()
    if not base:
        return None
    base = dict(base)
    is_office = base['department_id'] is None or base['branch_id'] is None
    emp = base['employee_id']
    if emp:
        cur.execute(
            '''
            SELECT u.id, u.name, u.employee_id, u.department_id, d.name AS dept_name,
                   d.branch_id, COALESCE(b.name, ?) AS branch_name
            FROM users u
            JOIN departments d ON u.department_id = d.id
            LEFT JOIN branches b ON d.branch_id = b.id
            WHERE u.employee_id = ?
            ''',
            (OFFICE_BRANCH_LABEL, emp),
        )
    elif is_office:
        cur.execute(
            '''
            SELECT u.id, u.name, u.employee_id, u.department_id, d.name AS dept_name,
                   d.branch_id, CASE WHEN u.department_id IS NULL THEN ? ELSE COALESCE(b.name, ?) END AS branch_name
            FROM users u
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN branches b ON d.branch_id = b.id
            WHERE u.employee_id IS NULL AND LOWER(u.name) = LOWER(?)
              AND (u.department_id IS NULL OR d.branch_id IS NULL)
            ''',
            (OFFICE_BRANCH_LABEL, OFFICE_BRANCH_LABEL, base['name']),
        )
    else:
        cur.execute(
            '''
            SELECT u.id, u.name, u.employee_id, u.department_id, d.name AS dept_name,
                   d.branch_id, COALESCE(b.name, ?) AS branch_name
            FROM users u
            JOIN departments d ON u.department_id = d.id
            LEFT JOIN branches b ON d.branch_id = b.id
            WHERE u.employee_id IS NULL AND LOWER(u.name) = LOWER(?) AND d.branch_id IS NOT NULL
            ''',
            (OFFICE_BRANCH_LABEL, base['name']),
        )
    rows = [dict(r) for r in cur.fetchall()]
    return {'base': base, 'is_office': is_office, 'rows': rows}


@admin_bp.route('/users', methods=['GET'])
@login_required
def get_users():
    conn = get_db_connection()
    cur = conn.cursor()

    department_id = request.args.get('department_id')
    grouped = (request.args.get('grouped') or '').strip().lower() in ('1', 'true', 'yes')

    if not grouped:
        if department_id:
            cur.execute(
                '''
                SELECT u.id, u.name, u.employee_id, u.mobile, u.email, u.department_id,
                       d.name as department_name, COALESCE(b.name, ?) as branch_name
                FROM users u
                JOIN departments d ON u.department_id = d.id
                LEFT JOIN branches b ON d.branch_id = b.id
                WHERE u.department_id = ?
                ORDER BY u.name
                ''',
                (OFFICE_BRANCH_LABEL, department_id),
            )
        else:
            cur.execute(
                '''
                SELECT u.id, u.name, u.employee_id, u.mobile, u.email, u.department_id,
                       d.name as department_name, COALESCE(b.name, ?) as branch_name
                FROM users u
                JOIN departments d ON u.department_id = d.id
                LEFT JOIN branches b ON d.branch_id = b.id
                ORDER BY branch_name, d.name, u.name
                ''',
                (OFFICE_BRANCH_LABEL,),
            )
        users = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify(users)

    # Grouped roster: collapse an employee's per-branch rows into one entry.
    cur.execute(
        '''
        SELECT u.id, u.name, u.employee_id, u.mobile, u.email, u.department_id,
               d.name as department_name, d.branch_id,
               CASE WHEN u.department_id IS NULL THEN ? ELSE COALESCE(b.name, ?) END as branch_name
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        LEFT JOIN branches b ON d.branch_id = b.id
        ''',
        (OFFICE_BRANCH_LABEL, OFFICE_BRANCH_LABEL),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    groups = {}
    order = []
    for r in rows:
        is_office = r['department_id'] is None or r['branch_id'] is None
        key = _employee_group_key(r['employee_id'], r['name'], is_office)
        g = groups.get(key)
        if not g:
            g = {
                'id': r['id'],
                'name': r['name'],
                'employee_id': r['employee_id'],
                'mobile': r['mobile'],
                'email': r['email'],
                'is_office': is_office,
                'row_ids': [],
                'branch_ids': [],
                'branch_names': [],
                'department_ids': [],
                'department_names': [],
                'department_id': None,
            }
            groups[key] = g
            order.append(key)
        g['row_ids'].append(r['id'])
        if r['id'] < g['id']:
            g['id'] = r['id']
        if not g['employee_id'] and r['employee_id']:
            g['employee_id'] = r['employee_id']
        if not g['mobile'] and r['mobile']:
            g['mobile'] = r['mobile']
        if not g['email'] and r['email']:
            g['email'] = r['email']
        if r['branch_id'] is not None and r['branch_id'] not in g['branch_ids']:
            g['branch_ids'].append(r['branch_id'])
            g['branch_names'].append(r['branch_name'])
        if r['department_id'] is not None and r['department_id'] not in g['department_ids']:
            g['department_ids'].append(r['department_id'])
            g['department_names'].append(r['department_name'])
        if g['department_id'] is None:
            g['department_id'] = r['department_id']

    dept_filter = None
    if department_id:
        try:
            dept_filter = int(department_id)
        except (TypeError, ValueError):
            dept_filter = None

    result = []
    for key in order:
        g = groups[key]
        if dept_filter is not None and dept_filter not in g['department_ids']:
            continue
        if g['is_office']:
            g['branch_name'] = OFFICE_BRANCH_LABEL
        else:
            g['branch_name'] = ', '.join(sorted(g['branch_names']))
        g['department_name'] = ', '.join(sorted(set(n for n in g['department_names'] if n))) or '—'
        result.append(g)

    result.sort(key=lambda x: ((x['branch_name'] or '').lower(), (x['name'] or '').lower()))
    return jsonify(result)

@admin_bp.route('/users', methods=['POST'])
@login_required
def add_user():
    # Only IT users can add users
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add users.'}), 403
    
    data = request.get_json()
    name = (data.get('name') or '').strip()
    employee_id = (data.get('employee_id') or '').strip()
    mobile = (data.get('mobile') or '').strip()
    email = (data.get('email') or '').strip()
    department_id = data.get('department_id')
    branch_ids = data.get('branch_ids')

    conn = get_db_connection()
    cur = conn.cursor()

    # Restaurant employees may be assigned to multiple branches at once. Each branch
    # uses its default "Restaurant" department, stored as one users row per branch.
    if isinstance(branch_ids, list) and branch_ids:
        if not name or not employee_id:
            conn.close()
            return jsonify({'error': 'Employee ID and name are required'}), 400

        cur.execute('SELECT id FROM users WHERE employee_id = ?', (employee_id,))
        if cur.fetchone():
            conn.close()
            return jsonify({'error': 'Employee ID already exists'}), 409

        created_ids = []
        first_id = None
        for raw_bid in branch_ids:
            try:
                bid = int(raw_bid)
            except (TypeError, ValueError):
                continue
            cur.execute('SELECT id FROM branches WHERE id = ?', (bid,))
            if not cur.fetchone():
                continue
            ensure_restaurant_default_department_for_branch(cur, bid)
            cur.execute(
                'SELECT id FROM departments WHERE branch_id = ? AND name = ?',
                (bid, RESTAURANT_DEFAULT_DEPARTMENT_NAME),
            )
            dep = cur.fetchone()
            if not dep:
                continue
            dep_id = dep[0]
            cur.execute('SELECT id FROM users WHERE name = ? AND department_id = ?', (name, dep_id))
            if cur.fetchone():
                continue
            cur.execute(
                'INSERT INTO users (name, employee_id, mobile, email, department_id) VALUES (?, ?, ?, ?, ?)',
                (name, employee_id, mobile or None, email or None, dep_id),
            )
            rid = cur.lastrowid
            created_ids.append(rid)
            if first_id is None:
                first_id = rid

        if not created_ids:
            conn.close()
            return jsonify({'error': 'This employee is already assigned to the selected branch(es).'}), 409

        conn.commit()
        conn.close()
        return jsonify({
            'id': first_id,
            'success': True,
            'name': name,
            'employee_id': employee_id,
            'created': len(created_ids),
        })

    # Office (or single-department) employee.
    if not name or not employee_id or not department_id:
        conn.close()
        return jsonify({'error': 'Employee ID, name, and department are required'}), 400

    cur.execute('SELECT id FROM departments WHERE id = ?', (department_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({'error': 'Department not found'}), 404

    cur.execute('SELECT id FROM users WHERE employee_id = ?', (employee_id,))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'Employee ID already exists'}), 409

    cur.execute('SELECT id FROM users WHERE name = ? AND department_id = ?', (name, department_id))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'User already exists in this department'}), 409

    cur.execute(
        'INSERT INTO users (name, employee_id, mobile, email, department_id) VALUES (?, ?, ?, ?, ?)',
        (name, employee_id, mobile or None, email or None, department_id),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()

    return jsonify({
        'id': user_id,
        'name': name,
        'employee_id': employee_id,
        'mobile': mobile,
        'email': email,
        'department_id': department_id,
    })

@admin_bp.route('/users/bulk', methods=['POST'])
@login_required
def add_bulk_users():
    # Only IT users can add bulk users
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add bulk users.'}), 403
    
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

@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    # Only IT users can update users
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can update users.'}), 403
    
    data = request.get_json()
    name = (data.get('name') or '').strip()
    employee_id = (data.get('employee_id') or '').strip()
    mobile = (data.get('mobile') or '').strip()
    email = (data.get('email') or '').strip()
    branch_ids = data.get('branch_ids')

    if not name or not employee_id:
        return jsonify({'error': 'Employee ID and name are required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    group = _load_employee_group(cur, user_id)
    if not group:
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    old_name = group['base']['name']
    is_office = group['is_office']
    group_rows = group['rows']
    group_ids = [r['id'] for r in group_rows]
    placeholders = ','.join('?' * len(group_ids))

    # Employee ID must be unique to this person (not used by a different employee).
    cur.execute(
        'SELECT id FROM users WHERE employee_id = ? AND id NOT IN (%s)' % placeholders,
        (employee_id, *group_ids),
    )
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'Employee ID already exists'}), 409

    # New name must not collide with another employee in any of this person's departments.
    for r in group_rows:
        cur.execute(
            'SELECT id FROM users WHERE name = ? AND department_id = ? AND id NOT IN (%s)' % placeholders,
            (name, r['department_id'], *group_ids),
        )
        if cur.fetchone():
            conn.close()
            return jsonify({'error': 'Employee name already exists in one of the selected branches/departments.'}), 409

    # Update shared fields across every row of this employee.
    for gid in group_ids:
        cur.execute(
            'UPDATE users SET name = ?, employee_id = ?, mobile = ?, email = ? WHERE id = ?',
            (name, employee_id, mobile or None, email or None, gid),
        )

    # Cascade the rename to owned assets, scoped per department (and branch for restaurants).
    for r in group_rows:
        if r['branch_id'] is None:
            cur.execute(
                'UPDATE assets SET owner = ? WHERE owner = ? AND department = ?',
                (name, old_name, r['dept_name']),
            )
        else:
            cur.execute(
                'UPDATE assets SET owner = ? WHERE owner = ? AND department = ? AND branch = ?',
                (name, old_name, r['dept_name'], r['branch_name']),
            )

    warning = None
    # Restaurant employees can add/remove branches. Each branch = its Restaurant dept row.
    if not is_office and isinstance(branch_ids, list):
        desired = set()
        for raw_bid in branch_ids:
            try:
                desired.add(int(raw_bid))
            except (TypeError, ValueError):
                continue
        if not desired:
            conn.close()
            return jsonify({'error': 'Please select at least one branch.'}), 400

        current = {r['branch_id']: r for r in group_rows if r['branch_id'] is not None}

        blocked = []
        for bid in set(current) - desired:
            r = current[bid]
            cur.execute(
                'SELECT COUNT(*) FROM assets WHERE owner = ? AND department = ? AND branch = ?',
                (name, r['dept_name'], r['branch_name']),
            )
            if cur.fetchone()[0] > 0:
                blocked.append(r['branch_name'])
                continue
            cur.execute('DELETE FROM users WHERE id = ?', (r['id'],))

        for bid in desired - set(current):
            cur.execute('SELECT id FROM branches WHERE id = ?', (bid,))
            if not cur.fetchone():
                continue
            ensure_restaurant_default_department_for_branch(cur, bid)
            cur.execute(
                'SELECT id FROM departments WHERE branch_id = ? AND name = ?',
                (bid, RESTAURANT_DEFAULT_DEPARTMENT_NAME),
            )
            dep = cur.fetchone()
            if not dep:
                continue
            dep_id = dep[0]
            cur.execute('SELECT id FROM users WHERE name = ? AND department_id = ?', (name, dep_id))
            if cur.fetchone():
                continue
            cur.execute(
                'INSERT INTO users (name, employee_id, mobile, email, department_id) VALUES (?, ?, ?, ?, ?)',
                (name, employee_id, mobile or None, email or None, dep_id),
            )

        if blocked:
            warning = ('Could not remove these branches because assets are still assigned to '
                       'this employee there: ' + ', '.join(sorted(blocked)))

    conn.commit()
    conn.close()

    response = {'success': True}
    if warning:
        response['warning'] = warning
    return jsonify(response)

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    # Only IT users can delete users
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can delete users.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()

    group = _load_employee_group(cur, user_id)
    if not group:
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    user_name = group['base']['name']
    group_rows = group['rows']

    # Block deletion if the employee still owns assets in any of their branches.
    asset_count = 0
    for r in group_rows:
        if r['branch_id'] is None:
            cur.execute(
                'SELECT COUNT(*) FROM assets WHERE owner = ? AND department = ?',
                (user_name, r['dept_name']),
            )
        else:
            cur.execute(
                'SELECT COUNT(*) FROM assets WHERE owner = ? AND department = ? AND branch = ?',
                (user_name, r['dept_name'], r['branch_name']),
            )
        asset_count += cur.fetchone()[0]

    if asset_count > 0:
        conn.close()
        return jsonify({'error': f'Cannot delete user. {asset_count} asset(s) are assigned to this user.'}), 409

    for r in group_rows:
        cur.execute('DELETE FROM users WHERE id = ?', (r['id'],))
    conn.commit()
    conn.close()

    return jsonify({'success': True}) 

# ===== ASSET TYPE MANAGEMENT API =====

@admin_bp.route('/asset-types', methods=['GET'])
@login_required
def get_asset_types():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name, for_venue FROM asset_types ORDER BY for_venue, name')
    asset_types = [{'id': row[0], 'name': row[1], 'for_venue': row[2]} for row in cur.fetchall()]
    conn.close()
    return jsonify(asset_types)

@admin_bp.route('/asset-types', methods=['POST'])
@login_required
def add_asset_type():
    # Only IT users can add asset types
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add asset categories.'}), 403

    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Asset category name is required'}), 400

    all_restaurants = request.form.get('all_restaurants') in ('1', 'true', 'on', 'yes')
    all_office = request.form.get('all_office_departments') in ('1', 'true', 'on', 'yes')

    if not all_restaurants and not all_office:
        for_venue = (request.form.get('for_venue') or '').strip().lower()
        if for_venue == 'restaurant':
            all_restaurants = True
        elif for_venue == 'office':
            all_office = True

    if not all_restaurants and not all_office:
        return jsonify({
            'error': 'Select at least one location (all restaurants and/or all office departments).'
        }), 400

    if all_restaurants and all_office:
        for_venue = 'both'
    elif all_restaurants:
        for_venue = 'restaurant'
    else:
        for_venue = 'office'

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            'INSERT INTO asset_types (name, for_venue) VALUES (?, ?)',
            (name, for_venue),
        )
        asset_type_id = cur.lastrowid
        conn.commit()
        conn.close()
        return jsonify({
            'success': True,
            'name': name,
            'for_venue': for_venue,
            'created_count': 1,
            'skipped_count': 0,
            'ids': [asset_type_id],
        })
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({
            'error': 'An asset category with this name already exists for the selected location(s).'
        }), 400
    except Exception:
        conn.close()
        return jsonify({'error': 'Failed to add asset category.'}), 500

@admin_bp.route('/asset-types/<int:asset_type_id>', methods=['PUT'])
@login_required
def update_asset_type(asset_type_id):
    # Only IT users can update asset types
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can update asset categories.'}), 403
    
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Asset category name is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT name, for_venue FROM asset_types WHERE id = ?', (asset_type_id,))
        old_row = cur.fetchone()
        if not old_row:
            conn.close()
            return jsonify({'error': 'Asset category not found'}), 404

        old_name, old_venue = old_row[0], old_row[1]

        cur.execute('UPDATE asset_types SET name = ? WHERE id = ?', (name, asset_type_id))

        cur.execute('UPDATE assets SET asset_type = ? WHERE asset_type = ?', (name, old_name))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': asset_type_id, 'name': name, 'for_venue': old_venue})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'An asset category with this name already exists for that location'}), 400

@admin_bp.route('/asset-types/<int:asset_type_id>', methods=['DELETE'])
@login_required
def delete_asset_type(asset_type_id):
    # Only IT users can delete asset types
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can delete asset categories.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT name FROM asset_types WHERE id = ?', (asset_type_id,))
    asset_type = cur.fetchone()
    if not asset_type:
        conn.close()
        return jsonify({'error': 'Asset category not found'}), 404
    
    asset_type_name = asset_type[0]
    
    cur.execute('SELECT COUNT(*) FROM assets WHERE asset_type = ?', (asset_type_name,))
    asset_count = cur.fetchone()[0]
    
    if asset_count > 0:
        conn.close()
        return jsonify({'error': f'Cannot delete asset category. It is being used by {asset_count} asset(s)'}), 400
    
    cur.execute('DELETE FROM asset_names WHERE asset_type_id = ?', (asset_type_id,))
    cur.execute('DELETE FROM asset_types WHERE id = ?', (asset_type_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ===== ASSET NAME MANAGEMENT API =====

def _fetch_spec_fields_for_asset_names(cur, asset_name_ids):
    """Return {asset_name_id: [{id, label, sort_order}, ...]}."""
    if not asset_name_ids:
        return {}
    placeholders = ','.join('?' * len(asset_name_ids))
    cur.execute(
        f'''
        SELECT id, asset_name_id, label, sort_order
        FROM asset_name_spec_fields
        WHERE asset_name_id IN ({placeholders})
        ORDER BY sort_order, id
        ''',
        asset_name_ids,
    )
    grouped = {}
    for row in cur.fetchall():
        grouped.setdefault(row[1], []).append({
            'id': row[0],
            'label': row[2],
            'sort_order': row[3],
        })
    return grouped


def _parse_specification_labels():
    """Parse specification labels from form (specifications[] or JSON)."""
    labels = []
    if request.form.get('specifications_json'):
        import json
        try:
            raw = json.loads(request.form.get('specifications_json') or '[]')
            if isinstance(raw, list):
                labels = [str(item).strip() for item in raw if str(item).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    if not labels:
        labels = [label.strip() for label in request.form.getlist('specifications[]') if label.strip()]
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for label in labels:
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(label)
    return unique


def _parse_specification_updates():
    """Parse spec field updates from form JSON: [{id?, label}]."""
    import json
    raw = request.form.get('specifications_json', '').strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    updates = []
    seen_labels = set()
    for item in parsed:
        if isinstance(item, str):
            label = item.strip()
            spec_id = None
        elif isinstance(item, dict):
            label = str(item.get('label', '')).strip()
            spec_id = item.get('id')
            if spec_id is not None:
                try:
                    spec_id = int(spec_id)
                except (TypeError, ValueError):
                    spec_id = None
        else:
            continue
        if not label:
            continue
        key = label.lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        updates.append({'id': spec_id, 'label': label})
    return updates


def _save_spec_fields_for_asset_name(cur, asset_name_id, labels):
    """Insert specification field labels for a new asset name."""
    for i, label in enumerate(labels):
        cur.execute(
            'INSERT INTO asset_name_spec_fields (asset_name_id, label, sort_order) VALUES (?, ?, ?)',
            (asset_name_id, label, i),
        )


def _sync_spec_fields_for_asset_name(cur, asset_name_id, updates):
    """Sync specification fields: update labels, add new, remove missing."""
    cur.execute(
        'SELECT id, label FROM asset_name_spec_fields WHERE asset_name_id = ? ORDER BY sort_order, id',
        (asset_name_id,),
    )
    existing = {row[0]: row[1] for row in cur.fetchall()}
    keep_ids = set()
    for i, item in enumerate(updates):
        spec_id = item.get('id')
        label = item['label']
        if spec_id and spec_id in existing:
            cur.execute(
                'UPDATE asset_name_spec_fields SET label = ?, sort_order = ? WHERE id = ? AND asset_name_id = ?',
                (label, i, spec_id, asset_name_id),
            )
            keep_ids.add(spec_id)
        else:
            cur.execute(
                'INSERT INTO asset_name_spec_fields (asset_name_id, label, sort_order) VALUES (?, ?, ?)',
                (asset_name_id, label, i),
            )
            keep_ids.add(cur.lastrowid)
    for old_id in existing:
        if old_id not in keep_ids:
            cur.execute('DELETE FROM asset_spec_values WHERE spec_field_id = ?', (old_id,))
            cur.execute('DELETE FROM asset_name_spec_fields WHERE id = ?', (old_id,))


def _fetch_inclusions_for_asset_names(cur, asset_name_ids):
    """Return {asset_name_id: [{id, label, sort_order}, ...]}."""
    if not asset_name_ids:
        return {}
    placeholders = ','.join('?' * len(asset_name_ids))
    cur.execute(
        f'''
        SELECT id, asset_name_id, label, sort_order
        FROM asset_name_inclusions
        WHERE asset_name_id IN ({placeholders})
        ORDER BY sort_order, id
        ''',
        asset_name_ids,
    )
    grouped = {}
    for row in cur.fetchall():
        grouped.setdefault(row[1], []).append({
            'id': row[0],
            'label': row[2],
            'sort_order': row[3],
        })
    return grouped


def _parse_inclusion_labels():
    """Parse inclusion labels from form JSON (inclusions_json)."""
    labels = []
    if request.form.get('inclusions_json'):
        import json
        try:
            raw = json.loads(request.form.get('inclusions_json') or '[]')
            if isinstance(raw, list):
                labels = [str(item).strip() for item in raw if str(item).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for label in labels:
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(label)
    return unique


def _parse_inclusion_updates():
    """Parse inclusion updates from form JSON: [{id?, label}]."""
    import json
    raw = request.form.get('inclusions_json', '').strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    updates = []
    seen_labels = set()
    for item in parsed:
        if isinstance(item, str):
            label = item.strip()
            inc_id = None
        elif isinstance(item, dict):
            label = str(item.get('label', '')).strip()
            inc_id = item.get('id')
            if inc_id is not None:
                try:
                    inc_id = int(inc_id)
                except (TypeError, ValueError):
                    inc_id = None
        else:
            continue
        if not label:
            continue
        key = label.lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        updates.append({'id': inc_id, 'label': label})
    return updates


def _save_inclusions_for_asset_name(cur, asset_name_id, labels):
    """Insert inclusion labels for a new asset name."""
    for i, label in enumerate(labels):
        cur.execute(
            'INSERT INTO asset_name_inclusions (asset_name_id, label, sort_order) VALUES (?, ?, ?)',
            (asset_name_id, label, i),
        )


def _sync_inclusions_for_asset_name(cur, asset_name_id, updates):
    """Sync inclusions: update labels, add new, remove missing."""
    cur.execute(
        'SELECT id, label FROM asset_name_inclusions WHERE asset_name_id = ? ORDER BY sort_order, id',
        (asset_name_id,),
    )
    existing = {row[0]: row[1] for row in cur.fetchall()}
    keep_ids = set()
    for i, item in enumerate(updates):
        inc_id = item.get('id')
        label = item['label']
        if inc_id and inc_id in existing:
            cur.execute(
                'UPDATE asset_name_inclusions SET label = ?, sort_order = ? WHERE id = ? AND asset_name_id = ?',
                (label, i, inc_id, asset_name_id),
            )
            keep_ids.add(inc_id)
        else:
            cur.execute(
                'INSERT INTO asset_name_inclusions (asset_name_id, label, sort_order) VALUES (?, ?, ?)',
                (asset_name_id, label, i),
            )
            keep_ids.add(cur.lastrowid)
    for old_id in existing:
        if old_id not in keep_ids:
            cur.execute('DELETE FROM asset_inclusion_values WHERE inclusion_id = ?', (old_id,))
            cur.execute('DELETE FROM asset_name_inclusions WHERE id = ?', (old_id,))


@admin_bp.route('/asset-names', methods=['GET'])
@login_required
def get_asset_names():
    asset_type_id = request.args.get('asset_type_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if asset_type_id:
        cur.execute('SELECT id, name FROM asset_names WHERE asset_type_id = ? ORDER BY name', (asset_type_id,))
        rows = cur.fetchall()
        ids = [row[0] for row in rows]
        spec_map = _fetch_spec_fields_for_asset_names(cur, ids)
        inclusion_map = _fetch_inclusions_for_asset_names(cur, ids)
        asset_names = [
            {
                'id': row[0],
                'name': row[1],
                'spec_fields': spec_map.get(row[0], []),
                'inclusions': inclusion_map.get(row[0], []),
            }
            for row in rows
        ]
    else:
        cur.execute('''
            SELECT an.id, an.name, an.asset_type_id, at.name as asset_type_name 
            FROM asset_names an 
            JOIN asset_types at ON an.asset_type_id = at.id 
            ORDER BY at.name, an.name
        ''')
        rows = cur.fetchall()
        ids = [row[0] for row in rows]
        spec_map = _fetch_spec_fields_for_asset_names(cur, ids)
        inclusion_map = _fetch_inclusions_for_asset_names(cur, ids)
        asset_names = [
            {
                'id': row[0],
                'name': row[1],
                'asset_type_id': row[2],
                'asset_type_name': row[3],
                'spec_fields': spec_map.get(row[0], []),
                'inclusions': inclusion_map.get(row[0], []),
            }
            for row in rows
        ]
    
    conn.close()
    return jsonify(asset_names)

@admin_bp.route('/asset-names', methods=['POST'])
@login_required
def add_asset_name():
    # Only IT users can add asset names
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add asset names.'}), 403
    
    name = request.form.get('name', '').strip()
    asset_type_id = request.form.get('asset_type_id')
    
    if not name:
        return jsonify({'error': 'Asset name is required'}), 400
    
    if not asset_type_id:
        return jsonify({'error': 'Asset category is required'}), 400
    
    try:
        asset_type_id = int(asset_type_id)
    except ValueError:
        return jsonify({'error': 'Invalid asset category ID'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    spec_labels = _parse_specification_labels()
    inclusion_labels = _parse_inclusion_labels()
    try:
        cur.execute('INSERT INTO asset_names (name, asset_type_id) VALUES (?, ?)', (name, asset_type_id))
        asset_name_id = cur.lastrowid
        if spec_labels:
            _save_spec_fields_for_asset_name(cur, asset_name_id, spec_labels)
        if inclusion_labels:
            _save_inclusions_for_asset_name(cur, asset_name_id, inclusion_labels)
        conn.commit()
        conn.close()
        return jsonify({
            'success': True,
            'id': asset_name_id,
            'name': name,
            'asset_type_id': asset_type_id,
            'spec_fields': [{'label': label} for label in spec_labels],
            'inclusions': [{'label': label} for label in inclusion_labels],
        })
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Asset name already exists for this asset category'}), 400

@admin_bp.route('/asset-names/<int:asset_name_id>', methods=['PUT'])
@login_required
def update_asset_name(asset_name_id):
    # Only IT users can update asset names
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can update asset names.'}), 403
    
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Asset name is required'}), 400
    
    spec_updates = _parse_specification_updates()
    if spec_updates is None:
        return jsonify({'error': 'Invalid specifications data'}), 400
    
    inclusion_updates = _parse_inclusion_updates()
    if inclusion_updates is None:
        return jsonify({'error': 'Invalid inclusions data'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if asset name exists
        cur.execute('SELECT an.name, at.name as asset_type_name FROM asset_names an JOIN asset_types at ON an.asset_type_id = at.id WHERE an.id = ?', (asset_name_id,))
        result = cur.fetchone()
        if not result:
            conn.close()
            return jsonify({'error': 'Asset name not found'}), 404
        
        old_name, asset_type_name = result
        
        # Update asset name
        cur.execute('UPDATE asset_names SET name = ? WHERE id = ?', (name, asset_name_id))
        
        # Update all assets that reference this asset name and asset type
        cur.execute('UPDATE assets SET name = ? WHERE name = ? AND asset_type = ?', (name, old_name, asset_type_name))

        if request.form.get('specifications_json') is not None:
            _sync_spec_fields_for_asset_name(cur, asset_name_id, spec_updates)

        if request.form.get('inclusions_json') is not None:
            _sync_inclusions_for_asset_name(cur, asset_name_id, inclusion_updates)
        
        spec_map = _fetch_spec_fields_for_asset_names(cur, [asset_name_id])
        inclusion_map = _fetch_inclusions_for_asset_names(cur, [asset_name_id])
        
        conn.commit()
        conn.close()
        return jsonify({
            'success': True,
            'id': asset_name_id,
            'name': name,
            'spec_fields': spec_map.get(asset_name_id, []),
            'inclusions': inclusion_map.get(asset_name_id, []),
        })
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Asset name already exists for this asset category'}), 400

@admin_bp.route('/asset-names/<int:asset_name_id>', methods=['DELETE'])
@login_required
def delete_asset_name(asset_name_id):
    # Only IT users can delete asset names
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can delete asset names.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if asset name exists
    cur.execute('SELECT an.name, at.name as asset_type_name FROM asset_names an JOIN asset_types at ON an.asset_type_id = at.id WHERE an.id = ?', (asset_name_id,))
    result = cur.fetchone()
    if not result:
        conn.close()
        return jsonify({'error': 'Asset name not found'}), 404
    
    asset_name, asset_type_name = result
    
    # Check if asset name is being used by any assets
    cur.execute('SELECT COUNT(*) FROM assets WHERE name = ? AND asset_type = ?', (asset_name, asset_type_name))
    asset_count = cur.fetchone()[0]
    
    if asset_count > 0:
        conn.close()
        return jsonify({'error': f'Cannot delete asset name. It is being used by {asset_count} asset(s)'}), 400
    
    cur.execute('DELETE FROM asset_name_spec_fields WHERE asset_name_id = ?', (asset_name_id,))
    cur.execute('DELETE FROM asset_name_inclusions WHERE asset_name_id = ?', (asset_name_id,))
    # Delete the asset name
    cur.execute('DELETE FROM asset_names WHERE id = ?', (asset_name_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True}) 