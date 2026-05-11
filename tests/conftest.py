import pathlib
import pytest
from pyepignostics.epignostics import EpignosticsPortalClient

CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.txt"


@pytest.fixture(scope="session")
def server_url():
    return EpignosticsPortalClient._SERVER_URL
