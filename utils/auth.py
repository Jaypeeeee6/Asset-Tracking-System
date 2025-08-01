import hashlib
import secrets

# Try to import bcrypt for secure password hashing
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    print("Warning: bcrypt not available. Install with: pip install bcrypt")

def hash_password(password):
    """Hash password using bcrypt or fallback to SHA256 with salt"""
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    else:
        # Fallback to SHA256 with salt (more secure than plain SHA256)
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
        # Fallback verification for SHA256 with salt
        try:
            if '$' in hashed:
                salt, hash_value = hashed.split('$', 1)
                hash_obj = hashlib.sha256()
                hash_obj.update((password + salt).encode('utf-8'))
                return hash_obj.hexdigest() == hash_value
            else:
                # Legacy SHA256 without salt (for existing passwords)
                return hashlib.sha256(password.encode()).hexdigest() == hashed
        except Exception:
            return False 