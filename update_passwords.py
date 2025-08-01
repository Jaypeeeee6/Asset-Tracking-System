#!/usr/bin/env python3
"""
Password Security Update Script
This script helps migrate existing user passwords to use secure hashing.
"""

import sqlite3
import hashlib
import secrets
import os

# Import the same hashing functions from app.py
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
    print("✓ bcrypt available - using secure hashing")
except ImportError:
    BCRYPT_AVAILABLE = False
    print("⚠ bcrypt not available - using fallback hashing")
    print("Install bcrypt with: pip install bcrypt")

def hash_password(password):
    """Hash password using bcrypt or fallback to SHA256 with salt"""
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    else:
        # Fallback to SHA256 with salt
        salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256()
        hash_obj.update((password + salt).encode('utf-8'))
        return f"{salt}${hash_obj.hexdigest()}"

def verify_password(password, hashed):
    """Verify password against bcrypt or SHA256 hash"""
    if BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception:
            return False
    else:
        try:
            if '$' in hashed:
                salt, hash_value = hashed.split('$', 1)
                hash_obj = hashlib.sha256()
                hash_obj.update((password + salt).encode('utf-8'))
                return hash_obj.hexdigest() == hash_value
            else:
                return hashlib.sha256(password.encode()).hexdigest() == hashed
        except Exception:
            return False

def migrate_passwords():
    """Migrate existing user passwords to secure hashing"""
    db_path = 'production_assets.db'
    
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found!")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Get all users
        cur.execute('SELECT id, username, password_hash, encrypted_password FROM users_auth')
        users = cur.fetchall()
        
        if not users:
            print("No users found in database.")
            return True
        
        print(f"Found {len(users)} users to update...")
        print("=" * 50)
        
        updated_count = 0
        
        for user_id, username, password_hash, encrypted_password in users:
            print(f"Processing user: {username}")
            
            # Check if password is already in new format
            if BCRYPT_AVAILABLE and password_hash.startswith('$2b$'):
                print(f"  ✓ User '{username}' already uses bcrypt - skipping")
                continue
            
            # Try to decrypt the password to re-hash it
            try:
                from cryptography.fernet import Fernet
                
                # Get the encryption key
                key_file = 'login_system/encryption_key.key'
                if os.path.exists(key_file):
                    with open(key_file, 'rb') as f:
                        key = f.read()
                    
                    f = Fernet(key)
                    decrypted_password = f.decrypt(encrypted_password.encode()).decode()
                    
                    # Hash with new method
                    new_hash = hash_password(decrypted_password)
                    
                    # Update the user
                    cur.execute('UPDATE users_auth SET password_hash = ? WHERE id = ?', 
                               (new_hash, user_id))
                    
                    print(f"  ✓ Updated user '{username}' to secure hashing")
                    updated_count += 1
                    
                else:
                    print(f"  ⚠ Warning: Could not find encryption key for user '{username}'")
                    
            except Exception as e:
                print(f"  ✗ Error updating user '{username}': {e}")
        
        conn.commit()
        conn.close()
        
        print("=" * 50)
        print(f"Update completed! {updated_count} users updated.")
        
        if updated_count > 0:
            print("\nIMPORTANT: Users should change their passwords for maximum security.")
        
        return True
        
    except Exception as e:
        print(f"Error during update: {e}")
        return False

def create_secure_user():
    """Create a new user with secure password hashing"""
    db_path = 'production_assets.db'
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        username = input("Enter username: ").strip()
        if not username:
            print("Username cannot be empty!")
            return False
        
        password = input("Enter password: ").strip()
        if len(password) < 6:
            print("Password must be at least 6 characters long!")
            return False
        
        # Check if user already exists
        cur.execute('SELECT id FROM users_auth WHERE username = ?', (username,))
        if cur.fetchone():
            print(f"User '{username}' already exists!")
            return False
        
        # Hash password securely
        password_hash = hash_password(password)
        
        # No encrypted password needed (deprecated)
        encrypted_password = "DEPRECATED"
        
        # Insert user
        cur.execute('INSERT INTO users_auth (username, password_hash, encrypted_password, role) VALUES (?, ?, ?, ?)',
                   (username, password_hash, encrypted_password, 'admin'))
        
        conn.commit()
        conn.close()
        
        print(f"✓ User '{username}' created with secure password hashing!")
        return True
        
    except Exception as e:
        print(f"Error creating user: {e}")
        return False

def main():
    """Main function"""
    print("🔒 Password Security Update Tool")
    print("=" * 40)
    
    print("\nOptions:")
    print("1. Update existing user passwords to secure hashing")
    print("2. Create new user with secure password")
    print("3. Exit")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == '1':
        migrate_passwords()
    elif choice == '2':
        create_secure_user()
    elif choice == '3':
        print("Goodbye!")
    else:
        print("Invalid choice!")

if __name__ == "__main__":
    main() 