"""Login account roles and built-in account rules for users_auth."""

AUTH_ROLE_IT = 'IT'
AUTH_ROLE_MANAGEMENT = 'Management'
AUTH_ROLE_QC = 'QC'
AUTH_ROLE_OPERATIONS = 'Operations'
AUTH_ROLES = (
    AUTH_ROLE_IT,
    AUTH_ROLE_MANAGEMENT,
    AUTH_ROLE_QC,
    AUTH_ROLE_OPERATIONS,
)


def role_has_legacy_admin_access(role):
    """IT role carries the same site-wide access the old ``admin`` login role had."""
    return role == AUTH_ROLE_IT


def is_super_admin_account(full_name, role):
    """Built-in accounts: full name Super Admin with IT role (cannot be deleted; fields locked in UI)."""
    if role != AUTH_ROLE_IT:
        return False
    return (full_name or '').strip().lower() == 'super admin'


def normalize_full_name(name):
    return (name or '').strip()
