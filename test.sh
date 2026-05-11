#!/bin/bash

# Run tests for the new Epignostix portal API integration

# Test update_samples (fetches and lists samples)
source .venv/bin/activate
pytest -s tests/test_login.py
#::TestLogin::test_update_samples

# Or run all login tests:
# pytest -s tests/test_login.py

# Or run a specific test:
# pytest -s tests/test_login.py::TestLogin::test_login_succeeds
