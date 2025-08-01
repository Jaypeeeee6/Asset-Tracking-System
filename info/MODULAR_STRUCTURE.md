# Modular Structure Documentation

The application has been successfully refactored from a single `app.py` file into a modular structure with the following organization:

## Directory Structure

```
tracking_system/
├── app.py                    # Main entry point (simplified)
├── run.py                    # Application factory entry point
├── __init__.py              # Application factory
├── models/                  # Database models and user classes
│   ├── __init__.py
│   ├── user.py             # User model for Flask-Login
│   └── database.py         # Database connection and initialization
├── routes/                  # Route handlers organized by functionality
│   ├── __init__.py
│   ├── auth.py             # Authentication routes (login, logout, user management)
│   ├── assets.py           # Asset management routes (dashboard, CRUD operations)
│   └── admin.py            # Admin API routes (buildings, departments, users)
├── utils/                   # Utility functions
│   ├── __init__.py
│   └── auth.py             # Password hashing and verification utilities
└── templates/              # HTML templates (unchanged)
```

## Key Changes

### 1. Application Factory Pattern
- `__init__.py` contains the `create_app()` function that initializes the Flask application
- Uses Flask-Login for authentication
- Registers blueprints for different route categories
- Initializes database on startup

### 2. Blueprint Organization
- **Auth Blueprint** (`routes/auth.py`): Handles login, logout, and user management
  - Routes: `/auth/login`, `/auth/logout`, `/auth/add_auth_user`, `/auth/manage_users`, `/auth/delete_auth_user`
- **Assets Blueprint** (`routes/assets.py`): Handles asset management
  - Routes: `/assets/dashboard`, `/assets/add`, `/assets/delete`, etc.
- **Admin Blueprint** (`routes/admin.py`): Handles administrative API endpoints
  - Routes: `/admin/buildings`, `/admin/departments`, `/admin/users`
- **Root Route** (`__init__.py`): Redirects `/` to `/auth/login`

### 3. Model Separation
- **User Model** (`models/user.py`): Flask-Login user class
- **Database Module** (`models/database.py`): Database connection and initialization functions

### 4. Utility Functions
- **Auth Utils** (`utils/auth.py`): Password hashing and verification with bcrypt fallback

## Benefits of Modular Structure

1. **Maintainability**: Code is organized by functionality, making it easier to find and modify specific features
2. **Scalability**: New features can be added as new blueprints without cluttering existing code
3. **Testability**: Each module can be tested independently
4. **Reusability**: Utility functions and models can be reused across different parts of the application
5. **Separation of Concerns**: Authentication, asset management, and admin functions are clearly separated

## Running the Application

The application can still be run using either:
```bash
python app.py
# or
python run.py
```

Both entry points will work the same way, with `app.py` now being a simple import of the modular application.

## Migration Notes

- All existing functionality has been preserved
- Database schema remains unchanged
- Templates have been updated to use the new route structure
- API endpoints have been updated to use blueprint prefixes where appropriate

## File Backups

- `app_original.py`: Backup of the original monolithic `app.py` file
- All original functionality is preserved in the modular structure 