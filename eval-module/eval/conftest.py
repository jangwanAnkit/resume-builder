"""
conftest.py — Shared pytest fixtures for the resume-builder eval module.

This file is automatically discovered by pytest and serves two purposes:
  1. Adds the eval/ directory to sys.path so `from metrics import ...` and
     `from schemas import ...` work regardless of where pytest is invoked from.
  2. Provides shared fixtures used across all test modules.

All tests in this directory can use these fixtures without importing them.
Pytest discovers conftest.py automatically.

Fixture hierarchy
-----------------
  sample_resume           — The full original resume data (all sections).
  mock_tailored_backend   — Pre-computed tailored output for the backend JD.
                            Loaded from disk so metric tests run without any
                            LLM API call.
  backend_jd              — The backend engineer JD text string.
  golden_cases            — All golden test cases loaded from
                            fixtures/golden_cases/*.json.
  api_config              — LLM provider config read from environment variables.
                            Used only by test_golden.py (Level 3 tests).
"""

from __future__ import annotations

import json
import os
import sys
import glob as glob_module
from pathlib import Path
from typing import Any

import pytest

# Ensure eval/ is on sys.path regardless of where pytest is invoked from.
# This makes `from metrics import ...` and `from schemas import ...` work
# both when running `pytest eval/` from the project root AND `pytest .` from
# within the eval/ directory.
_EVAL_DIR = Path(__file__).parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

# Root of the eval directory — all fixture paths are relative to this.
EVAL_DIR = Path(__file__).parent
FIXTURES_DIR = EVAL_DIR / "fixtures"


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_resume() -> dict[str, Any]:
    """
    Load the full original resume data from fixtures/sample_resume.json.

    Scoped to ``session`` so the file is only read once per test run.
    This is the ground-truth data that all tailored outputs are compared against.
    """
    path = FIXTURES_DIR / "sample_resume.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def mock_tailored_backend() -> dict[str, Any]:
    """
    Load a pre-computed tailored output for the Backend Engineer JD.

    This fixture allows Level 1 and Level 2 tests to validate schema and
    metrics WITHOUT making any LLM API calls.  The fixture was manually
    crafted to represent a realistic, high-quality tailored output.
    """
    path = FIXTURES_DIR / "mock_tailored_backend.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def backend_jd() -> str:
    """
    The Backend Engineer - Distributed Systems job description text.

    Stored inline here (also present in the golden case fixture) so it can be
    used directly by metric fixtures without reading golden case JSON.
    """
    path = FIXTURES_DIR / "golden_cases" / "backend_engineer.json"
    with open(path) as f:
        data = json.load(f)
    return data["jd"]


@pytest.fixture(scope="session")
def golden_cases() -> list[dict[str, Any]]:
    """
    Load all golden test case files from fixtures/golden_cases/*.json.

    Returns a list of case dicts, each with ``name``, ``jd``, and ``expected``
    keys.  Parametrized tests in test_golden.py iterate over this list.
    """
    pattern = str(FIXTURES_DIR / "golden_cases" / "*.json")
    cases = []
    for filepath in sorted(glob_module.glob(pattern)):
        with open(filepath) as f:
            cases.append(json.load(f))
    return cases


# ---------------------------------------------------------------------------
# LLM config fixture (used only by Level 3 slow tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api_config() -> dict[str, Any]:
    """
    Build the LLM provider config from environment variables.

    Required env vars:
      - ``OPENAI_API_KEY``  (or ``LLM_API_KEY`` as a generic override)

    Optional env vars:
      - ``LLM_PROVIDER``   defaults to ``"openai"``
      - ``LLM_MODEL``      defaults to ``"gpt-4o-mini"``
      - ``LLM_BASE_URL``   defaults to ``""``

    If ``OPENAI_API_KEY`` (or ``LLM_API_KEY``) is not set, golden tests skip.
    """
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY", "")
    return {
        "provider": os.environ.get("LLM_PROVIDER", "openai"),
        "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        "base_url": os.environ.get("LLM_BASE_URL", ""),
        "api_key": api_key,
    }
