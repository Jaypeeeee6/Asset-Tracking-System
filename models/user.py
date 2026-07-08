from flask_login import UserMixin

from utils.auth_roles import AUTH_ROLE_IT


class User(UserMixin):
    def __init__(self, id, email, role, full_name=''):
        self.id = id
        self.email = email
        self.role = role
        self.full_name = (full_name or '').strip()

    @property
    def display_name(self):
        """Human-readable label: full name when set, otherwise email."""
        return self.full_name or self.email

    def has_it_access(self):
        """Full app administration (same scope as the former ``admin`` role)."""
        return self.role == AUTH_ROLE_IT
