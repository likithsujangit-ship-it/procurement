import pytest
from pathlib import Path
from config import Config

@pytest.fixture(autouse=True, scope="session")
def override_config_dirs(tmp_path_factory):
    # Override config directories to use temporary pytest-managed folders during tests
    temp_download = tmp_path_factory.mktemp("files")
    temp_outputs = tmp_path_factory.mktemp("outputs")
    
    Config.DOWNLOAD_DIR = temp_download
    Config.OUTPUTS_DIR = temp_outputs
    
    yield
