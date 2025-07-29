# Asset Tracking System - Login System

## Overview
The Asset Tracking System now includes a secure login system with user roles and encrypted password storage.

## User Roles

### 1. Admin Role
- **Username**: `admin`
- **Password**: `admin123`
- **Permissions**: Full access to all features
- **Capabilities**: 
  - View all assets
  - Add/edit/delete assets
  - Manage buildings and departments
  - Access all system features

### 2. Purchasing Role
- **Username**: `purchasing`
- **Password**: `purchasing123`
- **Permissions**: Full access to all features
- **Capabilities**: 
  - View all assets
  - Add/edit/delete assets
  - Manage buildings and departments
  - Access all system features

## Password Security

### Encryption Method
- Passwords are encrypted using **Fernet** (symmetric encryption)
- Each password is stored in two formats:
  1. **Hash**: SHA-256 hash for login verification
  2. **Encrypted**: Fernet-encrypted for recovery purposes

### Encryption Key
- The encryption key is stored in `encryption_key.key`
- **IMPORTANT**: Keep this file secure and backed up
- If the key file is lost, encrypted passwords cannot be recovered

## Password Recovery

### Method 1: Web Interface (Admin Only)
1. Log in as an administrator
2. Click "Password Recovery" button in the top navigation
3. Enter the username to recover
4. The system will display the decrypted password

**Note**: Only administrators can access the password recovery feature.

## Password Change

### Using Command Line Utility
The `decrypt_password.py` script also supports password changes:

```bash
# Interactive password change (recommended)
python decrypt_password.py --change

# Direct password change for specific user
python decrypt_password.py --change-password admin
```

### Password Change Process
1. **Interactive Mode**: Shows all users and lets you choose which one to change
2. **Direct Mode**: Specify the username and enter the new password
3. **Security**: Passwords are automatically encrypted and hashed
4. **Confirmation**: Interactive mode requires password confirmation

### Method 2: Command Line Utility
Use the provided `decrypt_password.py` script:

```bash
# List all users and their passwords
python decrypt_password.py

# Decrypt password for specific user
python decrypt_password.py admin
python decrypt_password.py purchasing

# Change passwords (Interactive mode)
python decrypt_password.py --change

# Change password for specific user
python decrypt_password.py --change-password admin
```

### Method 3: Manual Database Query
You can also query the database directly:

```sql
-- View all users
SELECT id, username, role, encrypted_password FROM users_auth;

-- View specific user
SELECT id, username, role, encrypted_password FROM users_auth WHERE username = 'admin';
```

Then use the `decrypt_password()` function in Python:

```python
from cryptography.fernet import Fernet

# Load the key
with open('encryption_key.key', 'rb') as f:
    key = f.read()

# Decrypt password
f = Fernet(key)
decrypted = f.decrypt(encrypted_password.encode()).decode()
print(decrypted)
```

## Database Schema

### users_auth Table
```sql
CREATE TABLE users_auth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,           -- SHA-256 hash for login
    encrypted_password TEXT NOT NULL,      -- Fernet-encrypted for recovery
    role TEXT NOT NULL CHECK (role IN ('admin', 'purchasing')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Security Features

### 1. Session Management
- Uses Flask-Login for secure session management
- Automatic session timeout
- Secure logout functionality

### 2. Password Protection
- Passwords are never stored in plain text
- SHA-256 hashing for login verification
- Fernet encryption for password recovery
- Unique encryption key per installation

### 3. Access Control
- All main routes require authentication
- Role-based access control for password recovery and user management
- Only admin users can access password recovery and user management features
- Secure redirects for unauthenticated users

### 4. User Management
- Admin users can create new user accounts
- Admin users can view all users in the system
- Admin users can delete user accounts (except default admin/purchasing)
- Bulk delete functionality for multiple users
- User creation includes role assignment
- Password requirements and security guidelines provided

## Installation and Setup

### 1. Install Dependencies
```bash
pip install Flask-Login cryptography
```

### 2. Initialize Database
The system will automatically create the login tables when you first run the application:

```bash
python app.py
```

### 3. Default Users
The system creates two default users:
- **admin** / **admin123**
- **purchasing** / **purchasing123**

## Adding New Users

### Method 1: Web Interface (Admin Only)
1. Log in as an administrator
2. Click "Add User" button in the top navigation
3. Fill in the user details:
   - Username (required)
   - Password (required)
   - Role: Admin or Purchasing
4. Click "Create User"

**Route**: `/add_auth_user` (for authentication users)

### Method 2: Manage Users Page
1. Log in as an administrator
2. Click "Manage Users" to view all users
3. Click "Add New User" button
4. Fill in the user details and create

### Method 3: Direct Database Insert
```sql
INSERT INTO users_auth (username, password_hash, encrypted_password, role) 
VALUES ('newuser', 'hash_value', 'encrypted_value', 'admin');
```

### Method 4: Python Script
```python
from app import hash_password, encrypt_password

# Create new user
username = "newuser"
password = "newpassword123"
role = "admin"

password_hash = hash_password(password)
encrypted_password = encrypt_password(password)

# Insert into database
conn = get_db_connection()
cur = conn.cursor()
cur.execute('INSERT INTO users_auth (username, password_hash, encrypted_password, role) VALUES (?, ?, ?, ?)', 
           (username, password_hash, encrypted_password, role))
conn.commit()
conn.close()
```

## Troubleshooting

### Common Issues

1. **"Invalid username or password"**
   - Check if the user exists in the database
   - Verify the password is correct
   - Ensure the database is properly initialized

2. **"Error decrypting password"**
   - Check if `encryption_key.key` file exists
   - Verify the key file is not corrupted
   - Ensure the encrypted password is valid

3. **"User not found"**
   - Check if the user exists in `users_auth` table
   - Verify the username spelling
   - Check database connection

### Database Verification
```sql
-- Check if users_auth table exists
SELECT name FROM sqlite_master WHERE type='table' AND name='users_auth';

-- List all users
SELECT * FROM users_auth;

-- Check encryption key file
-- Look for 'encryption_key.key' in the project directory
```

## Security Best Practices

1. **Change Default Passwords**
   - Change the default admin and purchasing passwords
   - Use strong, unique passwords

2. **Secure the Encryption Key**
   - Keep `encryption_key.key` secure
   - Back up the key file
   - Don't commit it to version control

3. **Regular Password Updates**
   - Implement password expiration policies
   - Encourage strong password usage

4. **Monitor Access**
   - Log login attempts
   - Monitor for suspicious activity

## Future Enhancements

1. **Password Policies**
   - Minimum length requirements
   - Complexity requirements
   - Password expiration

2. **Advanced Roles**
   - Read-only users
   - Department-specific access
   - Audit logging

3. **Two-Factor Authentication**
   - SMS verification
   - Email verification
   - TOTP support

## Support

For issues with the login system:
1. Check the database connection
2. Verify the encryption key file
3. Review the application logs
4. Test with the provided utility scripts 