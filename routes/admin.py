from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.database import get_db_connection
import sqlite3

admin_bp = Blueprint('admin', __name__)

# ===== BRANCH MANAGEMENT API =====

@admin_bp.route('/branches', methods=['GET'])
@login_required
def get_branches():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM branches ORDER BY name')
    branches = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
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
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO branches (name) VALUES (?)', (name,))
        branch_id = cur.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': branch_id, 'name': name})
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
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT name FROM branches WHERE id = ?', (branch_id,))
        old_row = cur.fetchone()
        if not old_row:
            conn.close()
            return jsonify({'error': 'Branch not found'}), 404
        
        old_name = old_row[0]
        
        cur.execute('UPDATE branches SET name = ? WHERE id = ?', (name, branch_id))
        
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

# ===== DEPARTMENT MANAGEMENT API =====

@admin_bp.route('/departments', methods=['GET'])
@login_required
def get_departments():
    branch_id = request.args.get('branch_id') or request.args.get('building_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if branch_id:
        cur.execute('SELECT id, name FROM departments WHERE branch_id = ? ORDER BY name', (branch_id,))
    else:
        cur.execute('SELECT d.id, d.name, d.branch_id, b.name as branch_name FROM departments d JOIN branches b ON d.branch_id = b.id ORDER BY b.name, d.name')
    
    if branch_id:
        departments = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    else:
        departments = [{'id': row[0], 'name': row[1], 'branch_id': row[2], 'branch_name': row[3]} for row in cur.fetchall()]
    
    conn.close()
    return jsonify(departments)

@admin_bp.route('/departments', methods=['POST'])
@login_required
def add_department():
    # Only IT users (legacy admin-equivalent) can add departments
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add departments.'}), 403
    
    name = request.form.get('name', '').strip()
    branch_id = request.form.get('branch_id') or request.form.get('building_id')
    
    if not name:
        return jsonify({'error': 'Department name is required'}), 400
    
    if not branch_id:
        return jsonify({'error': 'Branch is required'}), 400
    
    try:
        branch_id = int(branch_id)
    except ValueError:
        return jsonify({'error': 'Invalid branch ID'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO departments (name, branch_id) VALUES (?, ?)', (name, branch_id))
        department_id = cur.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': department_id, 'name': name, 'branch_id': branch_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Department name already exists for this branch'}), 400

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
        # Check if department exists
        cur.execute('SELECT d.name, b.name FROM departments d JOIN branches b ON d.branch_id = b.id WHERE d.id = ?', (department_id,))
        result = cur.fetchone()
        if not result:
            conn.close()
            return jsonify({'error': 'Department not found'}), 404
        
        old_name, branch_name = result
        
        # Update department name
        cur.execute('UPDATE departments SET name = ? WHERE id = ?', (name, department_id))
        
        # Update all assets that reference this department and branch
        cur.execute('UPDATE assets SET department = ? WHERE department = ? AND branch = ?', (name, old_name, branch_name))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': department_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Department name already exists for this branch'}), 400

@admin_bp.route('/departments/<int:department_id>', methods=['DELETE'])
@login_required
def delete_department(department_id):
    # Only IT users can delete departments
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can delete departments.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if department exists
    cur.execute('SELECT d.name, b.name FROM departments d JOIN branches b ON d.branch_id = b.id WHERE d.id = ?', (department_id,))
    result = cur.fetchone()
    if not result:
        conn.close()
        return jsonify({'error': 'Department not found'}), 404
    
    department_name, branch_name = result
    
    # Check if department is being used by any assets
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

@admin_bp.route('/users', methods=['GET'])
@login_required
def get_users():
    conn = get_db_connection()
    cur = conn.cursor()
    
    department_id = request.args.get('department_id')
    if department_id:
        cur.execute('''
            SELECT u.id, u.name, u.department_id, d.name as department_name, b.name as branch_name 
            FROM users u 
            JOIN departments d ON u.department_id = d.id 
            JOIN branches b ON d.branch_id = b.id 
            WHERE u.department_id = ?
            ORDER BY u.name
        ''', (department_id,))
    else:
        cur.execute('''
            SELECT u.id, u.name, u.department_id, d.name as department_name, b.name as branch_name 
            FROM users u 
            JOIN departments d ON u.department_id = d.id 
            JOIN branches b ON d.branch_id = b.id 
            ORDER BY b.name, d.name, u.name
        ''')
    
    users = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(users)

@admin_bp.route('/users', methods=['POST'])
@login_required
def add_user():
    # Only IT users can add users
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add users.'}), 403
    
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

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    # Only IT users can delete users
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can delete users.'}), 403
    
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

# ===== ASSET TYPE MANAGEMENT API =====

@admin_bp.route('/asset-types', methods=['GET'])
@login_required
def get_asset_types():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM asset_types ORDER BY name')
    asset_types = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    conn.close()
    return jsonify(asset_types)

@admin_bp.route('/asset-types', methods=['POST'])
@login_required
def add_asset_type():
    # Only IT users can add asset types
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can add asset types.'}), 403
    
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Asset type name is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO asset_types (name) VALUES (?)', (name,))
        asset_type_id = cur.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': asset_type_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Asset type name already exists'}), 400

@admin_bp.route('/asset-types/<int:asset_type_id>', methods=['PUT'])
@login_required
def update_asset_type(asset_type_id):
    # Only IT users can update asset types
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can update asset types.'}), 403
    
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Asset type name is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if asset type exists
        cur.execute('SELECT name FROM asset_types WHERE id = ?', (asset_type_id,))
        old_asset_type = cur.fetchone()
        if not old_asset_type:
            conn.close()
            return jsonify({'error': 'Asset type not found'}), 404
        
        old_name = old_asset_type[0]
        
        # Update asset type name
        cur.execute('UPDATE asset_types SET name = ? WHERE id = ?', (name, asset_type_id))
        
        # Update all assets that reference this asset type
        cur.execute('UPDATE assets SET asset_type = ? WHERE asset_type = ?', (name, old_name))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': asset_type_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Asset type name already exists'}), 400

@admin_bp.route('/asset-types/<int:asset_type_id>', methods=['DELETE'])
@login_required
def delete_asset_type(asset_type_id):
    # Only IT users can delete asset types
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can delete asset types.'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if asset type exists
    cur.execute('SELECT name FROM asset_types WHERE id = ?', (asset_type_id,))
    asset_type = cur.fetchone()
    if not asset_type:
        conn.close()
        return jsonify({'error': 'Asset type not found'}), 404
    
    asset_type_name = asset_type[0]
    
    # Check if asset type is being used by any assets
    cur.execute('SELECT COUNT(*) FROM assets WHERE asset_type = ?', (asset_type_name,))
    asset_count = cur.fetchone()[0]
    
    if asset_count > 0:
        conn.close()
        return jsonify({'error': f'Cannot delete asset type. It is being used by {asset_count} asset(s)'}), 400
    
    # Delete the asset type and its asset names
    cur.execute('DELETE FROM asset_names WHERE asset_type_id = ?', (asset_type_id,))
    cur.execute('DELETE FROM asset_types WHERE id = ?', (asset_type_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# ===== ASSET NAME MANAGEMENT API =====

@admin_bp.route('/asset-names', methods=['GET'])
@login_required
def get_asset_names():
    asset_type_id = request.args.get('asset_type_id')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if asset_type_id:
        cur.execute('SELECT id, name FROM asset_names WHERE asset_type_id = ? ORDER BY name', (asset_type_id,))
    else:
        cur.execute('''
            SELECT an.id, an.name, an.asset_type_id, at.name as asset_type_name 
            FROM asset_names an 
            JOIN asset_types at ON an.asset_type_id = at.id 
            ORDER BY at.name, an.name
        ''')
    
    if asset_type_id:
        asset_names = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    else:
        asset_names = [{'id': row[0], 'name': row[1], 'asset_type_id': row[2], 'asset_type_name': row[3]} for row in cur.fetchall()]
    
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
        return jsonify({'error': 'Asset type is required'}), 400
    
    try:
        asset_type_id = int(asset_type_id)
    except ValueError:
        return jsonify({'error': 'Invalid asset type ID'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO asset_names (name, asset_type_id) VALUES (?, ?)', (name, asset_type_id))
        asset_name_id = cur.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': asset_name_id, 'name': name, 'asset_type_id': asset_type_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Asset name already exists for this asset type'}), 400

@admin_bp.route('/asset-names/<int:asset_name_id>', methods=['PUT'])
@login_required
def update_asset_name(asset_name_id):
    # Only IT users can update asset names
    if not current_user.has_it_access():
        return jsonify({'error': 'Access denied. Only IT users can update asset names.'}), 403
    
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Asset name is required'}), 400
    
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
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': asset_name_id, 'name': name})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Asset name already exists for this asset type'}), 400

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
    
    # Delete the asset name
    cur.execute('DELETE FROM asset_names WHERE id = ?', (asset_name_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True}) 