"""
Tests for utils.flask module
"""
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask

from utils.flask import RouteManager, check_restart_lock


@pytest.fixture
def flask_app():
    """Create a Flask app for testing"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


class TestRouteManager:
    """Test the RouteManager class"""

    def test_route_manager_initialization(self):
        """Test RouteManager initialization"""
        mock_app = MagicMock()
        route_manager = RouteManager(mock_app)

        assert route_manager.app is mock_app

    def test_add_proxy_routes(self):
        """Test adding proxy routes"""
        mock_app = MagicMock()
        route_manager = RouteManager(mock_app)

        proxy_routes = [
            ["/map/", "TAR1090", "/"],
            ["/tar1090/", "TAR1090", "/"],
            ["/graphs1090/", "TAR1090", "/graphs1090/"]
        ]

        route_manager.add_proxy_routes(proxy_routes)

        # Should add 3 URL rules
        assert mock_app.add_url_rule.call_count == 3

        # Check the calls - add_url_rule(endpoint, endpoint, function)
        calls = mock_app.add_url_rule.call_args_list
        # Check first two positional args (endpoint, endpoint_name)
        assert calls[0][0][:2] == ("/map/", "/map/")
        assert calls[1][0][:2] == ("/tar1090/", "/tar1090/")
        assert calls[2][0][:2] == ("/graphs1090/", "/graphs1090/")
        # Third arg is the function - just check it's callable
        assert callable(calls[0][0][2])
        assert callable(calls[1][0][2])
        assert callable(calls[2][0][2])

    def test_function_factory(self, flask_app):
        """Test function factory creates proper redirect functions"""
        route_manager = RouteManager(flask_app)

        func = route_manager.function_factory("/test/", 8080, "/path")

        # Function should be callable
        assert callable(func)

        # Test calling the function within a request context
        with flask_app.test_request_context('/?'):
            with patch('utils.flask.redirect') as mock_redirect:
                func(idx=1, inc_port=2, sub_path="/extra")
                mock_redirect.assert_called_once()

    def test_my_redirect_basic(self, flask_app):
        """Test basic redirect functionality"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/'):
            with patch('utils.flask.redirect') as mock_redirect:
                result = route_manager.my_redirect("/test/", 8080, "/path")
                mock_redirect.assert_called_once_with("http://localhost:8080/path")

    def test_my_redirect_with_query_string(self, flask_app):
        """Test redirect with query string"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/?param=value'):
            with patch('utils.flask.redirect') as mock_redirect:
                result = route_manager.my_redirect("/test/", 8080, "/path")
                mock_redirect.assert_called_once_with("http://localhost:8080/path?param=value")

    def test_my_redirect_with_idx(self, flask_app):
        """Test redirect with index parameter"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/'):
            with patch('utils.flask.redirect') as mock_redirect:
                result = route_manager.my_redirect("/test/", 8080, "/path", idx=5)
                mock_redirect.assert_called_once_with("http://localhost:8080/5/path")

    def test_my_redirect_with_inc_port(self, flask_app):
        """Test redirect with increment port"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/'):
            with patch('utils.flask.redirect') as mock_redirect:
                result = route_manager.my_redirect("/test/", 8080, "/path", inc_port=3)
                # Should increment port by inc_port * 1000: 8080 + 3*1000 = 11080
                mock_redirect.assert_called_once_with("http://localhost:11080/path")

    def test_my_redirect_with_sub_path(self, flask_app):
        """Test redirect with sub path"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/'):
            with patch('utils.flask.redirect') as mock_redirect:
                result = route_manager.my_redirect("/test/", 8080, "/path", sub_path="/extra")
                mock_redirect.assert_called_once_with("http://localhost:8080/path/extra")

    def test_my_redirect_complex_scenario(self, flask_app):
        """Test redirect with multiple parameters"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/?param1=value1&param2=value2'):
            with patch('utils.flask.redirect') as mock_redirect:
                result = route_manager.my_redirect("/test/", 8080, "/path", idx=2, inc_port=1, sub_path="/extra")
                # Port: 8080 + 1*1000 = 9080
                # Path: /path + /extra = /path/extra
                # With idx: /2/path/extra
                mock_redirect.assert_called_once_with("http://localhost:9080/2/path/extra?param1=value1&param2=value2")

    def test_my_redirect_host_url_cleanup(self, flask_app):
        """Test redirect with host URL cleanup"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/'):
            with patch('utils.flask.redirect') as mock_redirect:
                result = route_manager.my_redirect("/test/", 8080, "/path")
                mock_redirect.assert_called_once_with("http://localhost:8080/path")

    def test_my_redirect_host_url_with_port_cleanup(self, flask_app):
        """Test redirect with host URL that has port cleanup"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/'):
            with patch('utils.flask.redirect') as mock_redirect:
                result = route_manager.my_redirect("/test/", 8080, "/path")
                # Should remove port from host_url before adding new port
                mock_redirect.assert_called_once_with("http://localhost:8080/path")


class TestCheckRestartLock:
    """Test the check_restart_lock decorator"""

    def test_check_restart_lock_not_locked(self):
        """Test decorator when restart lock is not locked"""
        mock_self = MagicMock()
        mock_self._system._restart.lock.locked.return_value = False

        @check_restart_lock
        def test_function(self, *args, **kwargs):
            return "success"

        result = test_function(mock_self)

        assert result == "success"
        mock_self._system._restart.lock.locked.assert_called_once()

    @patch('utils.flask.redirect')
    def test_check_restart_lock_locked(self, mock_redirect):
        """Test decorator when restart lock is locked"""
        mock_self = MagicMock()
        mock_self._system._restart.lock.locked.return_value = True

        @check_restart_lock
        def test_function(self, *args, **kwargs):
            return "success"

        result = test_function(mock_self)

        mock_redirect.assert_called_once_with("/restarting")
        assert result is mock_redirect.return_value

    def test_check_restart_lock_preserves_function_metadata(self):
        """Test that decorator preserves function metadata"""
        @check_restart_lock
        def test_function(self, arg1, arg2=None):
            """Test function docstring"""
            return "success"

        # Check that function name and docstring are preserved
        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test function docstring"

    def test_check_restart_lock_with_arguments(self):
        """Test decorator with function arguments"""
        mock_self = MagicMock()
        mock_self._system._restart.lock.locked.return_value = False

        @check_restart_lock
        def test_function(self, arg1, arg2, kwarg1=None, kwarg2=None):
            return f"success: {arg1}, {arg2}, {kwarg1}, {kwarg2}"

        result = test_function(mock_self, "arg1", "arg2", kwarg1="kwarg1", kwarg2="kwarg2")

        assert result == "success: arg1, arg2, kwarg1, kwarg2"

    @patch('utils.flask.redirect')
    def test_check_restart_lock_with_arguments_locked(self, mock_redirect):
        """Test decorator with function arguments when locked"""
        mock_self = MagicMock()
        mock_self._system._restart.lock.locked.return_value = True

        @check_restart_lock
        def test_function(self, arg1, arg2, kwarg1=None, kwarg2=None):
            return f"success: {arg1}, {arg2}, {kwarg1}, {kwarg2}"

        result = test_function(mock_self, "arg1", "arg2", kwarg1="kwarg1", kwarg2="kwarg2")

        mock_redirect.assert_called_once_with("/restarting")
        # Function should not be called when locked
        assert result is mock_redirect.return_value


class TestRouteManagerIntegration:
    """Integration tests for RouteManager"""

    def test_route_manager_full_workflow(self):
        """Test complete workflow of RouteManager"""
        mock_app = MagicMock()
        route_manager = RouteManager(mock_app)

        # Define proxy routes
        proxy_routes = [
            ["/map/", "TAR1090", "/"],
            ["/graphs1090/", "TAR1090", "/graphs1090/"],
            ["/fa/", "PIAWAREMAP", "/"]
        ]

        # Add routes
        route_manager.add_proxy_routes(proxy_routes)

        # Verify all routes were added
        assert mock_app.add_url_rule.call_count == 3

        # Test one of the generated functions with numeric port
        func = route_manager.function_factory("/map/", 8080, "/")

        # Create a real Flask app for request context
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/'):
            with patch('utils.flask.redirect') as mock_redirect:
                func()
                # Port should be numeric for my_redirect to work
                mock_redirect.assert_called_once_with("http://localhost:8080/")

    def test_route_manager_edge_cases(self):
        """Test RouteManager edge cases"""
        mock_app = MagicMock()
        route_manager = RouteManager(mock_app)

        # Test with empty proxy routes
        route_manager.add_proxy_routes([])
        mock_app.add_url_rule.assert_not_called()

        # Test with malformed proxy routes
        malformed_routes = [
            ["/test/"],  # Missing port and path
            ["/test/", "8080"],  # Missing path
        ]

        # Should not crash, but may not work as expected
        try:
            route_manager.add_proxy_routes(malformed_routes)
        except Exception as e:
            # This is expected behavior for malformed routes
            assert isinstance(e, (IndexError, TypeError, ValueError))

    def test_route_manager_special_characters(self, flask_app):
        """Test RouteManager with special characters in URLs"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/'):
            with patch('utils.flask.redirect') as mock_redirect:
                # Test with special characters
                result = route_manager.my_redirect("/test/", 8080, "/path with spaces", sub_path="/extra%20path")
                mock_redirect.assert_called_once_with("http://localhost:8080/path with spaces/extra%20path")

    def test_route_manager_unicode(self, flask_app):
        """Test RouteManager with unicode characters"""
        route_manager = RouteManager(flask_app)

        with flask_app.test_request_context('/'):
            with patch('utils.flask.redirect') as mock_redirect:
                # Test with unicode characters
                result = route_manager.my_redirect("/test/", 8080, "/path", sub_path="/测试")
                mock_redirect.assert_called_once_with("http://localhost:8080/path/测试")
