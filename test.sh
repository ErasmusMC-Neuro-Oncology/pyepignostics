#!/bin/bash

# Run tests for the new Epignostix portal API integration

source .venv/bin/activate

# Test 401 token expiration handling (fast, mocked)
echo "=== Testing 401 re-login handling ==="
pytest -s tests/test_401_handling.py

# Test update_samples (fetches and lists samples)
echo -e "\n=== Testing login and sample operations ==="
pytest -s tests/test_login.py
#::TestLogin::test_update_samples

# Or run all login tests:
# pytest -s tests/test_login.py

# Or run a specific test:
# pytest -s tests/test_login.py::TestLogin::test_login_succeeds


pytest -s tests/test_workflows.py
