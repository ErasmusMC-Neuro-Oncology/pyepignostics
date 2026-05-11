import pathlib
import pytest
from pymnp.pymnp import mnpscrapNew

CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.txt"


@pytest.fixture(scope="session")
def server_url():
    return mnpscrapNew._SERVER_URL
