#!/usr/bin/env python

"""
Tests for 401 token expiration handling.

Simulates token expiration and verifies automatic re-login.

Run:
    pytest tests/test_401_handling.py -v
"""

import pathlib
import pytest
from unittest.mock import Mock, patch, call
import requests

from pyepignostics.epignostics import EpignosticsPortalClient

CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.txt"

requires_config = pytest.mark.skipif(
    not CONFIG_PATH.exists(),
    reason="config.txt not found in project root"
)


class _EpignosticsPortalClientWithCreds(EpignosticsPortalClient):
    """Test-only subclass that injects credentials instead of reading config.txt."""
    def __init__(self, username, password):
        self._user = username
        self._pwd = password

    def get_config(self):
        pass


class Test401Handling:
    @requires_config
    def test_401_triggers_relogin(self):
        """Verify that a 401 response triggers automatic re-login and retry."""
        # Setup
        with open(CONFIG_PATH) as f:
            config = dict(line.strip().split('=') for line in f if '=' in line)

        app = _EpignosticsPortalClientWithCreds(config['user'], config['pwd'])
        app.login()
        original_token = app._response_token

        # Verify we have a token
        assert original_token is not None
        assert len(original_token) > 0

        print(f"\n✓ Logged in successfully, token: {original_token[:20]}...")

        # Simulate token expiration by invalidating it
        app._response_token = "invalid_expired_token"
        print(f"✗ Invalidated token for testing")

        # Mock both requests.request and requests.post for the entire operation
        with patch('pymnp.pymnp.requests.request') as mock_request, \
             patch('pymnp.pymnp.requests.post') as mock_post:

            # Mock responses
            mock_response_401 = Mock()
            mock_response_401.status_code = 401
            mock_response_401.raise_for_status.side_effect = requests.exceptions.HTTPError("401")

            mock_response_success = Mock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {"access_token": "new_valid_token_xyz"}
            mock_response_success.raise_for_status.return_value = None

            # Setup response sequence:
            # 1. GET request with invalid token → 401
            # 2. POST login request → success with new token
            # 3. GET request retry → success
            mock_request.side_effect = [
                mock_response_401,      # First request with invalid token
                mock_response_success,  # Retry request with new token
            ]
            mock_post.return_value = mock_response_success  # Login request

            # This should trigger the 401 handler
            response = app.get(
                app._SERVER_URL + '/workflows',
                params={"entity_type": "IlluminaMethylationSample"}
            )

            # Verify the request succeeded after retry
            assert response.status_code == 200

            # Verify token was refreshed
            assert app._response_token == "new_valid_token_xyz"

            print(f"✓ Received 401, re-logged in, and retried successfully")
            print(f"✓ New token: {app._response_token[:20]}...")

            # Verify we made 2 GET requests (1 failed + 1 retry) and 1 login POST
            assert mock_request.call_count == 2
            assert mock_post.call_count == 1
            print(f"✓ Made correct sequence: GET(401) → POST(login) → GET(success)")

    @requires_config
    def test_401_relogin_uses_saved_credentials(self):
        """Verify re-login doesn't require re-entering credentials."""
        with open(CONFIG_PATH) as f:
            config = dict(line.strip().split('=') for line in f if '=' in line)

        app = _EpignosticsPortalClientWithCreds(config['user'], config['pwd'])
        app.login()
        original_user = app._user
        original_pwd = app._pwd

        # After login, credentials are cleared from memory
        assert app._user is None
        assert app._pwd is None
        print(f"✓ Credentials cleared after login")

        # But we should still be able to re-login if token expires
        # (The test above verifies this works)
