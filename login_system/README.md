# Login System Files

This folder contains all the files related to the login system and password management for the Asset Tracking System.

## Files

### `decrypt_password.py`
A utility script for password management and recovery. This script can:
- List all users and their passwords
- Decrypt passwords for specific users
- Change user passwords interactively
- Change passwords for specific users directly

**Usage:**
```bash
# List all users and their passwords
python decrypt_password.py

# Decrypt password for specific user
python decrypt_password.py admin
python decrypt_password.py purchasing

# Interactive password change
python decrypt_password.py --change

# Direct password change for specific user
python decrypt_password.py --change-password admin
```

### `encryption_key.key`
The encryption key file used by the Fernet encryption system. This file is critical for:
- Encrypting new passwords
- Decrypting existing passwords
- Password recovery functionality

**⚠️ IMPORTANT:** Keep this file secure and backed up. If this file is lost, encrypted passwords cannot be recovered.

### `LOGIN_SYSTEM_README.md`
Comprehensive documentation for the login system including:
- User roles and permissions
- Password security features
- Database schema
- Installation and setup instructions
- Troubleshooting guide
- Security best practices

## Security Notes

1. **Encryption Key**: The `encryption_key.key` file contains the master encryption key. Keep this file secure and never commit it to version control.

2. **Password Storage**: Passwords are stored in two formats:
   - SHA-256 hash for login verification
   - Fernet-encrypted for recovery purposes

3. **Access Control**: Only administrators can access password recovery and user management features.

## File Locations

- **Database**: `../production_assets.db` (parent directory)
- **Main Application**: `../app.py` (parent directory)
- **Encryption Key**: `encryption_key.key` (this directory)

## Backup

The database backup created during the email column removal is stored as:
`../production_assets_backup_20250729_102131.db`

## Running the Application

The main application should be run from the parent directory:

```bash
cd ..
python app.py
```

The login system files are automatically referenced by the main application. 