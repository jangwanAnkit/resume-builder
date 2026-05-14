"""
assertions.py — Custom Python assertion functions for promptfoo.

promptfoo calls this file's ``get_assert`` function for any assertion of type
``python`` in promptfooconfig.yaml.  The function receives the raw LLM output
string and the test context, and must return either:
  - A boolean (True = pass, False = fail)
  - A dict with keys: ``pass`` (bool), ``score`` (float), ``reason`` (str)

The dict format is preferred — it provides richer information in the promptfoo
web UI and is required for scored (non-binary) assertions.

How this integrates
-------------------
promptfoo passes the raw LLM ``output`` string and a ``context`` dict containing:
  - ``context["vars"]``    — the test variables (``jd``, ``resume_json``)
  - ``context["prompt"]``  — the rendered prompt string
  - ``context["test"]``    — the full test case dict from the YAML

This module imports from metrics.py (in the parent directory) and runs the
full metric suite against the parsed JSON output.

Usage in promptfooconfig.yaml:
    assert:
      - type: python
        value: file://assertions.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

# Allow imports from the parent eval/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics import (
    run_all_metrics,
    flatten_resume_to_text,
    job_alignment_score,
    content_preservation_score,
)
from schemas import TailoredResponse


def _parse_output(output: str) -> dict[str, Any] | None:
    """
    Parse the LLM output string as JSON, stripping any markdown fences first.

    Returns None if parsing fails.
    """
    text = output.strip()
    # Strip markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def get_assert(output: str, context: dict[str, Any]) -> dict[str, Any]:
    """
    Main entry point called by promptfoo for ``type: python`` assertions.

    Runs a battery of checks against the LLM output:
      1. JSON parseability
      2. Pydantic schema validation
      3. Immutable field integrity
      4. Bullet count preservation
      5. Hallucination check (new numbers)
      6. Job alignment score
      7. Content preservation score

    Each component contributes to a weighted overall score (0–1).

    Args:
        output:  Raw string output from the LLM.
        context: Test context dict from promptfoo.

    Returns:
        Dict with ``pass`` (bool), ``score`` (float 0–1), ``reason`` (str).
    """
    failures: list[str] = []
    component_scores: list[float] = []

    # ---- 1. JSON parseable? -----------------------------------------------
    data = _parse_output(output)
    if data is None:
        return {
            "pass": False,
            "score": 0.0,
            "reason": (
                "Output is not valid JSON. The LLM returned non-parseable text. "
                f"First 200 chars: {output[:200]!r}"
            ),
        }
    component_scores.append(1.0)  # JSON parse passed

    # ---- 2. Pydantic schema validation ------------------------------------
    try:
        TailoredResponse(**data)
        component_scores.append(1.0)
    except Exception as exc:
        failures.append(f"Schema validation: {exc}")
        component_scores.append(0.0)

    # ---- 3–7. Metric-based checks -----------------------------------------
    # Reconstruct original resume from context vars
    vars_ = context.get("vars", {})
    resume_json_str = vars_.get("resume_json", "{}")
    jd_text = vars_.get("jd", "")

    try:
        original_data = json.loads(resume_json_str)
    except json.JSONDecodeError:
        original_data = {}

    if original_data and jd_text:
        report = run_all_metrics(original_data, data, jd_text)

        # Immutable field violations
        if report["immutable_violations"]:
            failures.append(
                "Immutable fields changed: " + "; ".join(report["immutable_violations"])
            )
            component_scores.append(0.0)
        else:
            component_scores.append(1.0)

        # Bullet count issues
        if report["bullet_count_issues"]:
            failures.append(
                "Bullet count issues: " + "; ".join(report["bullet_count_issues"])
            )
            component_scores.append(0.0)
        else:
            component_scores.append(1.0)

        # Hallucination check
        if report["hallucinated_numbers"]:
            failures.append(
                "Hallucinated numbers: " + ", ".join(report["hallucinated_numbers"])
            )
            component_scores.append(0.0)
        else:
            component_scores.append(1.0)

        # Job alignment (scored — partial credit)
        alignment = report["job_alignment_score"]
        if alignment >= 0.15:
            component_scores.append(1.0)
        elif alignment >= 0.08:
            component_scores.append(0.6)
        else:
            failures.append(f"Job alignment too low: {alignment:.4f} (need ≥0.08)")
            component_scores.append(0.0)

        # Content preservation (scored — partial credit)
        preservation = report["content_preservation"]
        if preservation >= 0.70:
            component_scores.append(1.0)
        elif preservation >= 0.55:
            component_scores.append(0.7)
        else:
            failures.append(
                f"Content preservation too low: {preservation:.4f} (need ≥0.55)"
            )
            component_scores.append(0.0)

    # ---- Compute overall score --------------------------------------------
    overall_score = sum(component_scores) / len(component_scores) if component_scores else 0.0
    passed = len(failures) == 0 and overall_score >= 0.70

    # ---- Build reason string ----------------------------------------------
    if passed:
        align = report.get("job_alignment_score", 0) if original_data else "N/A"
        pres = report.get("content_preservation", 0) if original_data else "N/A"
        relevance = data.get("relevance", "N/A")
        reason = (
            f"All checks passed. "
            f"Relevance={relevance}/10, "
            f"alignment={align:.4f}, "
            f"preservation={pres:.4f}."
        )
    else:
        reason = "FAILURES:\n" + "\n".join(f"  - {f}" for f in failures)
        if overall_score < 0.70 and not failures:
            reason = f"Overall score {overall_score:.2f} below threshold 0.70."

    return {
        "pass": passed,
        "score": round(overall_score, 4),
        "reason": reason,
    }
