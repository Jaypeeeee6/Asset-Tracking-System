from flask_login import UserMixin

from utils.auth_roles import AUTH_ROLE_IT


class User(UserMixin):
    def __init__(self, id, username, role, full_name=''):
        self.id = id
        self.username = username
        self.role = role
        self.full_name = (full_name or '').strip()

    def has_it_access(self):
        """Full app administration (same scope as the former ``admin`` role)."""
        return self.role == AUTH_ROLE_IT