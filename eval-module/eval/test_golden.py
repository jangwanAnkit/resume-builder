"""
test_golden.py — Level 3: Golden regression tests (requires LLM API call).

LEVEL: 3 — Golden regression (slow, requires API key)
RUNS WITHOUT: NOT runnable without OPENAI_API_KEY (or LLM_API_KEY)
SPEED: ~5–15 seconds per test case (one LLM round-trip each)
MARKER: @pytest.mark.slow — skipped by default in fast CI runs

What this file tests
---------------------
Golden regression tests call the actual tailoring function (or the HTTP API)
with a known JD and then validate that the response meets all quality and
structural criteria defined in the golden case fixture.

They answer the question:
    "When I actually call the LLM with this JD, does the output meet our
     quality bar for relevance, keyword coverage, and data integrity?"

Why golden tests matter
-----------------------
Unit tests (Levels 1 & 2) run against a pre-computed fixture.  They catch
regressions in the evaluation framework itself.  Golden tests catch model
regressions: when OpenAI rolls out a new model version or you switch to a
different provider, the tailoring quality may silently degrade.  Golden tests
give you an early warning signal.

How to run
----------
# Run only golden tests (requires API key):
    export OPENAI_API_KEY=sk-...
    pytest eval/test_golden.py -v

# Skip golden tests (run only Levels 1 & 2):
    pytest eval/ -v -m "not slow"

# Run all tests including golden:
    pytest eval/ -v

How to add a new golden case
-----------------------------
1. Create a new JSON file in eval/fixtures/golden_cases/<name>.json.
2. Set ``expected.min_relevance``, ``expected.max_relevance``, etc.
3. The parametrized test will pick it up automatically.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from metrics import (
    flatten_resume_to_text,
    job_alignment_score,
    content_preservation_score,
    immutable_field_violations,
    hallucination_check,
    bullet_count_check,
)
from schemas import TailoredResponse


# ---------------------------------------------------------------------------
# Tailor function — calls the local server API or the function directly
# ---------------------------------------------------------------------------

def _call_tailor_api(
    jd: str,
    resume_data: dict[str, Any],
    api_config: dict[str, Any],
    base_url: str = "http://localhost:3000",
) -> dict[str, Any]:
    """
    Call the /api/tailor endpoint and return the parsed JSON response.

    Tries to import the server's tailor function directly first (faster, no
    network overhead).  Falls back to HTTP if the module is not importable,
    which is the case when running the eval module standalone.

    Args:
        jd:          The job description text.
        resume_data: Full resume data dict (all sections).
        api_config:  LLM provider config dict from the api_config fixture.
        base_url:    Base URL of the running resume builder server.

    Returns:
        The parsed tailored API response dict.

    Raises:
        RuntimeError: If the API call fails or returns non-200.
    """
    payload = {
        "jd": jd,
        "config": api_config,
        "data": resume_data,
    }

    # Attempt direct function import first (when running inside the main project)
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from server import tailor_resume  # type: ignore[import]
        return tailor_resume(payload)
    except ImportError:
        pass

    # Fall back to HTTP call
    import urllib.request
    import urllib.error

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/tailor",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Tailor API returned HTTP {exc.code}: {body_text}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Failed to reach tailor API at {base_url}. "
            "Make sure the server is running: `npm run dev`\n"
            f"Original error: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Parametrized golden test
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.parametrize("case", ["backend_engineer", "frontend_react", "data_scientist"])
def test_golden_case(
    case: str,
    golden_cases: list[dict[str, Any]],
    sample_resume: dict[str, Any],
    api_config: dict[str, Any],
) -> None:
    """
    Run the full tailoring pipeline for a golden case and validate all criteria.

    Each golden case defines:
      - ``jd``                     — the job description
      - ``expected.min_relevance`` — minimum acceptable relevance score
      - ``expected.max_relevance`` — maximum acceptable relevance score
      - ``expected.must_include_keywords``  — keywords that MUST appear in output
      - ``expected.must_not_change``        — field paths that must be immutable
      - ``expected.min_content_preservation`` — minimum preservation score
      - ``expected.min_job_alignment``     — minimum alignment score
      - ``expected.experience_count``      — expected number of experience entries
      - ``expected.profile_name``          — expected profile name

    Validation steps (all must pass):
      1. Schema validation via Pydantic TailoredResponse
      2. Relevance score in expected range
      3. All must-include keywords present in tailored text
      4. No immutable field violations (company, dates, locations)
      5. No hallucinated numbers
      6. Content preservation above threshold
      7. Job alignment above threshold
      8. Bullet count preserved per entry
    """
    # Find the matching case by name
    case_data = next(
        (c for c in golden_cases if c["name"].lower().replace(" ", "_").replace("-", "_")
         in case.lower().replace(" ", "_").replace("-", "_")
         or case.lower().replace("_", " ") in c["name"].lower()),
        None,
    )
    if case_data is None:
        # Also try case-name-based file matching
        case_map = {c["name"]: c for c in golden_cases}
        # Map parametrize keys to case names
        key_to_name = {
            "backend_engineer": "Backend Engineer - Distributed Systems",
            "frontend_react": "Frontend React Developer",
            "data_scientist": "Data Scientist - ML",
        }
        case_data = case_map.get(key_to_name.get(case, ""))

    if case_data is None:
        pytest.fail(
            f"Golden case {case!r} not found in fixtures/golden_cases/. "
            f"Available cases: {[c['name'] for c in golden_cases]}"
        )

    # Skip if no API key is configured
    if not api_config.get("api_key"):
        pytest.skip(
            "No LLM API key configured. Set OPENAI_API_KEY or LLM_API_KEY "
            "environment variable to run golden tests."
        )

    jd = case_data["jd"]
    expected = case_data["expected"]

    # --- Step 0: Call the tailoring API ---
    tailored = _call_tailor_api(jd, sample_resume, api_config)

    # --- Step 1: Schema validation ---
    try:
        parsed = TailoredResponse(**tailored)
    except Exception as exc:
        pytest.fail(
            f"[{case}] Pydantic schema validation failed:\n{exc}\n\n"
            f"Raw response (truncated):\n{json.dumps(tailored, indent=2)[:2000]}"
        )

    # --- Step 2: Relevance score in expected range ---
    relevance = tailored.get("relevance", 0)
    assert expected["min_relevance"] <= relevance <= expected["max_relevance"], (
        f"[{case}] Relevance {relevance} outside expected range "
        f"[{expected['min_relevance']}, {expected['max_relevance']}]."
    )

    # --- Step 3: Must-include keywords present ---
    tail_text = flatten_resume_to_text(tailored).lower()
    missing_kws = [
        kw for kw in expected.get("must_include_keywords", [])
        if kw.lower() not in tail_text
    ]
    assert not missing_kws, (
        f"[{case}] Required keywords missing from tailored output:\n"
        + "\n".join(f"  - {kw}" for kw in missing_kws)
    )

    # --- Step 4: Immutable field violations ---
    violations = immutable_field_violations(sample_resume, tailored)
    assert not violations, (
        f"[{case}] Immutable field violations detected:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )

    # --- Step 5: No hallucinated numbers ---
    orig_text = flatten_resume_to_text(sample_resume)
    new_numbers = hallucination_check(orig_text, tail_text)
    assert not new_numbers, (
        f"[{case}] Hallucinated numeric values detected:\n"
        + "\n".join(f"  - {n}" for n in new_numbers)
    )

    # --- Step 6: Content preservation above threshold ---
    preservation = content_preservation_score(orig_text, tail_text)
    min_preservation = expected.get("min_content_preservation", 0.55)
    assert preservation >= min_preservation, (
        f"[{case}] Content preservation {preservation:.4f} is below "
        f"minimum {min_preservation:.4f}."
    )

    # --- Step 7: Job alignment above threshold ---
    alignment = job_alignment_score(tail_text, jd)
    min_alignment = expected.get("min_job_alignment", 0.08)
    assert alignment >= min_alignment, (
        f"[{case}] Job alignment {alignment:.4f} is below minimum {min_alignment:.4f}."
    )

    # --- Step 8: Bullet count preserved ---
    bullet_issues = bullet_count_check(sample_resume, tailored)
    assert not bullet_issues, (
        f"[{case}] Bullet count issues:\n"
        + "\n".join(f"  - {i}" for i in bullet_issues)
    )

    # --- Step 9: Experience count matches ---
    expected_exp_count = expected.get("experience_count", 3)
    actual_exp_count = len(tailored.get("experience", {}).get("experience", []))
    assert actual_exp_count == expected_exp_count, (
        f"[{case}] Experience count: expected {expected_exp_count}, got {actual_exp_count}."
    )

    # --- Step 10: Profile name unchanged ---
    expected_name = expected.get("profile_name")
    if expected_name:
        actual_name = tailored.get("profile", {}).get("name")
        assert actual_name == expected_name, (
            f"[{case}] Profile name changed: {expected_name!r} → {actual_name!r}"
        )


# ---------------------------------------------------------------------------
# Additional single-case slow tests for specific scenarios
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_low_match_jd_gets_low_relevance(
    golden_cases: list[dict[str, Any]],
    sample_resume: dict[str, Any],
    api_config: dict[str, Any],
) -> None:
    """
    WHY: The Data Scientist JD is a low-match for this full-stack resume.
    A well-calibrated LLM should reflect this with a low relevance score (1–4).
    If the model returns relevance=9 for a data science JD against a full-stack
    resume, its scoring is uncalibrated and the whole system's credibility
    suffers (users will distrust the score).

    This test is particularly valuable when switching models — some models
    are over-optimistic and inflate relevance scores regardless of fit.
    """
    if not api_config.get("api_key"):
        pytest.skip("No API key configured.")

    ds_case = next(
        (c for c in golden_cases if "data scientist" in c["name"].lower()),
        None,
    )
    if not ds_case:
        pytest.skip("Data scientist golden case not found.")

    tailored = _call_tailor_api(ds_case["jd"], sample_resume, api_config)
    relevance = tailored.get("relevance", 0)

    assert relevance <= 4, (
        f"Data Scientist JD got relevance={relevance} (expected ≤4). "
        "The model appears to be inflating relevance scores."
    )


@pytest.mark.slow
def test_high_match_jd_gets_high_relevance(
    golden_cases: list[dict[str, Any]],
    sample_resume: dict[str, Any],
    api_config: dict[str, Any],
) -> None:
    """
    WHY: The Backend Engineer JD is a strong match for this resume.
    The model should recognise this and return relevance ≥ 7.
    If it returns a low score, its semantic understanding of the JD-to-resume
    match is broken — likely a system prompt regression or wrong model.
    """
    if not api_config.get("api_key"):
        pytest.skip("No API key configured.")

    be_case = next(
        (c for c in golden_cases if "backend engineer" in c["name"].lower()),
        None,
    )
    if not be_case:
        pytest.skip("Backend engineer golden case not found.")

    tailored = _call_tailor_api(be_case["jd"], sample_resume, api_config)
    relevance = tailored.get("relevance", 0)

    assert relevance >= 7, (
        f"Backend Engineer JD got relevance={relevance} (expected ≥7). "
        "The model appears to be under-scoring a strong match."
    )
