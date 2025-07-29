#!/usr/bin/env python3
"""
Password Management Utility
This script helps you decrypt and change passwords from the database manually.
Use this only for legitimate password recovery and management purposes.
"""

import sqlite3
from cryptography.fernet import Fernet
import os
import hashlib

def get_or_create_key():
    """Get the encryption key from file or create a new one"""
    key_file = 'encryption_key.key'
    if os.path.exists(key_file):
        with open(key_file, 'rb') as f:
            return f.read()
    else:
        print("Error: encryption_key.key file not found!")
        return None

def decrypt_password(encrypted_password):
    """Decrypt a password using Fernet"""
    key = get_or_create_key()
    if key is None:
        return None
    try:
        f = Fernet(key)
        return f.decrypt(encrypted_password.encode()).decode()
    except Exception as e:
        print(f"Error decrypting password: {e}")
        return None

def list_all_users():
    """List all users in the database with their encrypted passwords"""
    try:
        conn = sqlite3.connect('../production_assets.db')
        cur = conn.cursor()
        cur.execute('SELECT id, username, role, encrypted_password FROM users_auth')
        users = cur.fetchall()
        conn.close()
        
        print("=" * 60)
        print("USER PASSWORD RECOVERY UTILITY")
        print("=" * 60)
        print()
        
        if not users:
            print("No users found in the database.")
            return
        
        for user_id, username, role, encrypted_password in users:
            decrypted_password = decrypt_password(encrypted_password)
            if decrypted_password:
                print(f"User ID: {user_id}")
                print(f"Username: {username}")
                print(f"Role: {role}")
                print(f"Password: {decrypted_password}")
                print("-" * 40)
            else:
                print(f"User ID: {user_id}")
                print(f"Username: {username}")
                print(f"Role: {role}")
                print(f"Password: [DECRYPTION FAILED]")
                print("-" * 40)
                
    except Exception as e:
        print(f"Error accessing database: {e}")

def decrypt_specific_user(username):
    """Decrypt password for a specific user"""
    try:
        conn = sqlite3.connect('../production_assets.db')
        cur = conn.cursor()
        cur.execute('SELECT id, username, role, encrypted_password FROM users_auth WHERE username = ?', (username,))
        user = cur.fetchone()
        conn.close()
        
        if user:
            user_id, username, role, encrypted_password = user
            decrypted_password = decrypt_password(encrypted_password)
            if decrypted_password:
                print(f"Username: {username}")
                print(f"Role: {role}")
                print(f"Password: {decrypted_password}")
            else:
                print(f"Failed to decrypt password for user: {username}")
        else:
            print(f"User '{username}' not found in the database.")
            
    except Exception as e:
        print(f"Error: {e}")

def hash_password(password):
    """Create a hash of the password for verification"""
    return hashlib.sha256(password.encode()).hexdigest()

def encrypt_password(password):
    """Encrypt a password using Fernet"""
    key = get_or_create_key()
    if key is None:
        return None
    try:
        f = Fernet(key)
        return f.encrypt(password.encode()).decode()
    except Exception as e:
        print(f"Error encrypting password: {e}")
        return None

def change_user_password(username, new_password):
    """Change password for a specific user"""
    try:
        conn = sqlite3.connect('../production_assets.db')
        cur = conn.cursor()
        
        # Check if user exists
        cur.execute('SELECT id, username, role FROM users_auth WHERE username = ?', (username,))
        user = cur.fetchone()
        
        if not user:
            conn.close()
            print(f"User '{username}' not found in the database.")
            return False
        
        user_id, username, role = user
        
        # Create new password hash and encrypted password
        password_hash = hash_password(new_password)
        encrypted_password = encrypt_password(new_password)
        
        if encrypted_password is None:
            conn.close()
            print("Failed to encrypt new password.")
            return False
        
        # Update the user's password
        cur.execute('UPDATE users_auth SET password_hash = ?, encrypted_password = ? WHERE id = ?', 
                   (password_hash, encrypted_password, user_id))
        conn.commit()
        conn.close()
        
        print(f"Password for user '{username}' has been changed successfully.")
        print(f"New password: {new_password}")
        return True
        
    except Exception as e:
        print(f"Error changing password: {e}")
        return False

def interactive_password_change():
    """Interactive password change mode"""
    print("\n" + "=" * 60)
    print("INTERACTIVE PASSWORD CHANGE")
    print("=" * 60)
    
    # List all users first
    print("\nAvailable users:")
    try:
        conn = sqlite3.connect('../production_assets.db')
        cur = conn.cursor()
        cur.execute('SELECT username, role FROM users_auth ORDER BY username')
        users = cur.fetchall()
        conn.close()
        
        for i, (username, role) in enumerate(users, 1):
            print(f"{i}. {username} ({role})")
        
        print("\nEnter the username to change password for:")
        username = input("Username: ").strip()
        
        if not username:
            print("Username cannot be empty.")
            return
        
        # Get new password
        print("\nEnter the new password:")
        new_password = input("New password: ").strip()
        
        if not new_password:
            print("Password cannot be empty.")
            return
        
        # Confirm password
        confirm_password = input("Confirm password: ").strip()
        
        if new_password != confirm_password:
            print("Passwords do not match.")
            return
        
        # Change the password
        change_user_password(username, new_password)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--change" or sys.argv[1] == "-c":
            # Interactive password change mode
            interactive_password_change()
        elif len(sys.argv) == 3 and sys.argv[1] == "--change-password":
            # Direct password change: --change-password username newpassword
            username = sys.argv[2]
            new_password = input(f"Enter new password for {username}: ").strip()
            if new_password:
                change_user_password(username, new_password)
            else:
                print("Password cannot be empty.")
        else:
            # If username provided as argument
            username = sys.argv[1]
            print(f"Decrypting password for user: {username}")
            decrypt_specific_user(username)
    else:
        # List all users
        list_all_users()
        
    print("\n" + "=" * 60)
    print("USAGE:")
    print("  python decrypt_password.py                    # List all users")
    print("  python decrypt_password.py admin             # Decrypt specific user")
    print("  python decrypt_password.py --change          # Interactive password change")
    print("  python decrypt_password.py --change-password username  # Direct password change")
    print("=" * 60) 