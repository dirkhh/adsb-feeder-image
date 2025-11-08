"""
Web authentication utilities for Flask applications.

This module provides a simple authentication system that can be shared
between app.py and recovery-app.py.
"""

from functools import wraps
from typing import Callable

from flask import Flask, redirect, request
from flask.helpers import session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


class WebAuth:
    """Simple authentication manager for Flask apps."""

    def __init__(self, app: Flask, app_secret: str, user_name: Callable, password_hash: Callable, enabled: Callable):
        self.app = app
        self._secret = app_secret
        self._user_name_func = user_name
        self._password_hash_func = password_hash
        self._enabled_func = enabled

    def is_enabled(self) -> bool:
        return self._enabled_func()

    def user_name(self) -> str:
        return self._user_name_func()

    def password_hash(self) -> str:
        return self._password_hash_func()

    def is_authenticated(self) -> bool:
        if not self.is_enabled():
            return True
        return session.get("authenticated", False)

    def verify_password(self, username: str, password: str) -> bool:
        stored_username = self._user_name_func()
        stored_hash = self._password_hash_func()
        if not stored_username or not stored_hash:
            return False
        return username == stored_username and check_password_hash(stored_hash, password)

    def login(self, username: str, password: str) -> bool:
        if self.verify_password(username, password):
            session["authenticated"] = True
            session.permanent = True
            return True
        return False

    def logout(self):
        """Log out the current user."""
        session.pop("authenticated", None)

    def hash_password(self, password: str) -> str:
        return generate_password_hash(password)

    def require_auth(self, f):
        """Decorator to require authentication for a route.

        Usage:
            @auth.require_auth
            def protected_route():
                return "Protected content"
        """

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not self.is_authenticated():
                return redirect(url_for("login", next=request.url))
            return f(*args, **kwargs)

        return decorated_function


def create_auth_decorator(auth_instance: WebAuth):
    """Create a decorator that checks authentication using the given WebAuth instance.

    This is useful for methods in a class-based Flask app.

    Args:
        auth_instance: WebAuth instance to use for authentication

    Returns:
        A decorator function
    """

    def require_auth(f):
        @wraps(f)
        def decorated_function(self, *args, **kwargs):
            if not auth_instance.is_authenticated():
                return redirect(url_for("login", next=request.url))
            return f(self, *args, **kwargs)

        return decorated_function

    return require_auth
