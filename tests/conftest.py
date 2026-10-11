import os
from pathlib import Path

import pytest

# Ensure testing settings
os.environ["PLAN_MODE"] = "fixture"
os.environ["ALLOWED_TARGET_HOSTS"] = "localhost,127.0.0.1,demo-api,demo-web"
os.environ["TEST_USER_EMAIL"] = "tester@example.test"
os.environ["TEST_USER_PASSWORD"] = "SecretPassword123!"
os.environ["OUTPUT_DIR"] = "output"


@pytest.fixture
def sample_inputs_dir():
    return Path(__file__).parent.parent / "inputs"
