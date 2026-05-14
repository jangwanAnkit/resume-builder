"""
test_metrics.py — Level 2: Quality metrics tests.

LEVEL: 2 — Quality metrics (fast, zero LLM cost)
RUNS WITHOUT: any API key or network access
SPEED: < 1 second

What this file tests
---------------------
These tests use the pre-computed mock_tailored_backend fixture to validate
that the tailored output is *qualitatively* better than the original for the
backend engineer JD.  They answer the question:

    "Is the tailored output actually better aligned to the job description,
     and did the LLM preserve the candidate's real experience?"

This is the second layer of the eval loop.  Level 1 checks structure;
Level 2 checks quality.

Thresholds
----------
The thresholds here are intentionally conservative (not too strict) to allow
for variation across model providers.  Tighten them as you accumulate more
golden data and calibrate your expectations per model.
"""

from __future__ import annotations

from typing import Any

import pytest

from metrics import (
    job_alignment_score,
    content_preservation_score,
    keyword_injection_report,
    hallucination_check,
    immutable_field_violations,
    bullet_count_check,
    flatten_resume_to_text,
    run_all_metrics,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJobAlignment:
    """Tests that tailoring measurably improved keyword overlap with the JD."""

    def test_job_alignment_increases(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
        backend_jd: str,
    ) -> None:
        """
        WHY: The whole point of tailoring is to make the resume more aligned
        to the job description.  If the alignment score of the tailored output
        is NOT higher than the original, the tailoring is actively harmful —
        it may have removed relevant keywords while the LLM rewrote things.

        This test ensures the core value proposition holds: tailoring increases
        JD keyword coverage.
        """
        orig_text = flatten_resume_to_text(sample_resume)
        tail_text = flatten_resume_to_text(mock_tailored_backend)

        orig_alignment = job_alignment_score(orig_text, backend_jd)
        tail_alignment = job_alignment_score(tail_text, backend_jd)

        assert tail_alignment > orig_alignment, (
            f"Tailored alignment ({tail_alignment:.4f}) is not higher than "
            f"original ({orig_alignment:.4f}). Tailoring is not adding value."
        )

    def test_job_alignment_above_minimum(
        self,
        mock_tailored_backend: dict[str, Any],
        backend_jd: str,
    ) -> None:
        """
        WHY: Even with a conservative threshold of 0.10 (10% JD keyword overlap),
        a well-tailored backend resume should comfortably exceed this.
        If it doesn't, the prompt is probably not injecting keywords effectively.
        """
        tail_text = flatten_resume_to_text(mock_tailored_backend)
        alignment = job_alignment_score(tail_text, backend_jd)
        assert alignment >= 0.10, (
            f"Job alignment {alignment:.4f} is below minimum threshold of 0.10."
        )


class TestContentPreservation:
    """Tests that the LLM preserved a meaningful portion of the original content."""

    def test_content_preservation_above_threshold(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
    ) -> None:
        """
        WHY: Content preservation measures how much of the original text survived
        the rewrite.  A score below 0.55 suggests the LLM invented large portions
        of the resume rather than rewording existing content.  This is the single
        best proxy for hallucination risk at the paragraph level.

        The threshold of 0.55 is calibrated to allow substantial rewording while
        catching cases where the model invents entire job histories.
        """
        orig_text = flatten_resume_to_text(sample_resume)
        tail_text = flatten_resume_to_text(mock_tailored_backend)
        preservation = content_preservation_score(orig_text, tail_text)

        assert preservation >= 0.55, (
            f"Content preservation {preservation:.4f} is below threshold 0.55. "
            "The LLM may have replaced too much original content with new text."
        )

    def test_content_not_identical(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
    ) -> None:
        """
        WHY: A preservation score of 1.0 means nothing changed — the tailoring
        was a no-op.  This test ensures the LLM actually modified the resume.
        A completely unchanged resume would get the same relevance score as
        submitting the generic resume.
        """
        orig_text = flatten_resume_to_text(sample_resume)
        tail_text = flatten_resume_to_text(mock_tailored_backend)
        preservation = content_preservation_score(orig_text, tail_text)

        assert preservation < 0.98, (
            f"Content preservation {preservation:.4f} is almost 1.0 — the tailoring "
            "produced no meaningful changes."
        )


class TestHallucination:
    """Tests that the LLM did not invent new numbers or metrics."""

    def test_no_hallucinated_numbers(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
    ) -> None:
        """
        WHY: The most damaging form of hallucination in resume tailoring is
        inventing new quantified claims: "improved performance by 70%" when the
        original said 50%, or "managed a team of 10" when the original said 5.

        A recruiter who spots an inconsistency between the resume and what the
        candidate says in an interview will immediately distrust the entire resume.

        This test checks that no new numeric tokens appeared in the tailored
        output that weren't in the original.
        """
        orig_text = flatten_resume_to_text(sample_resume)
        tail_text = flatten_resume_to_text(mock_tailored_backend)
        new_numbers = hallucination_check(orig_text, tail_text)

        assert len(new_numbers) == 0, (
            f"Hallucinated numbers detected (present in tailored but not original):\n"
            + "\n".join(f"  - {n}" for n in new_numbers)
            + "\n\nReview the tailored output for fabricated metrics."
        )


class TestKeywordInjection:
    """Tests that JD keywords were successfully woven into the tailored resume."""

    def test_keyword_injection_happens(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
        backend_jd: str,
    ) -> None:
        """
        WHY: A tailored resume should explicitly incorporate keywords from the JD.
        ATS (Applicant Tracking System) parsing relies on exact keyword matches.
        If the injection count is zero, the tailoring only rewrote framing but
        didn't add any new relevant terms — ATS scores won't improve.
        """
        orig_text = flatten_resume_to_text(sample_resume)
        tail_text = flatten_resume_to_text(mock_tailored_backend)
        report = keyword_injection_report(orig_text, tail_text, backend_jd)

        added = report["added"]
        assert len(added) > 0, (
            "No new JD keywords were injected into the tailored resume. "
            f"Injection report: maintained={len(report['maintained'])}, "
            f"lost={len(report['lost'])}, jd_keywords={report['jd_keyword_count']}"
        )

    def test_critical_keywords_present(
        self,
        mock_tailored_backend: dict[str, Any],
        backend_jd: str,
    ) -> None:
        """
        WHY: The backend JD explicitly requires microservices, Docker, Kafka,
        PostgreSQL, Redis, Python, and CI/CD.  A well-tailored output for a
        highly-matching resume (the sample resume mentions all of these) must
        retain ALL of these keywords in the tailored text.
        """
        tail_text = flatten_resume_to_text(mock_tailored_backend).lower()
        critical_keywords = ["microservices", "docker", "kafka", "postgresql", "redis", "python"]

        missing = [kw for kw in critical_keywords if kw not in tail_text]
        assert not missing, (
            f"Critical backend JD keywords missing from tailored resume:\n"
            + "\n".join(f"  - {kw}" for kw in missing)
        )

    def test_injection_rate_positive(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
        backend_jd: str,
    ) -> None:
        """
        WHY: The injection_rate measures what fraction of JD keywords appear in the
        tailored resume (via addition or maintenance).  Even a low injection rate
        (>0.30) indicates meaningful coverage.
        """
        orig_text = flatten_resume_to_text(sample_resume)
        tail_text = flatten_resume_to_text(mock_tailored_backend)
        report = keyword_injection_report(orig_text, tail_text, backend_jd)

        assert report["injection_rate"] > 0.30, (
            f"Keyword injection rate {report['injection_rate']:.4f} is below 0.30. "
            "Too few JD keywords are covered by the tailored resume."
        )


class TestImmutableFieldMetrics:
    """Tests the immutable field and bullet-count metrics functions directly."""

    def test_no_immutable_violations(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
    ) -> None:
        """
        WHY: This validates the metrics.immutable_field_violations() function
        itself — making sure it correctly identifies zero violations for a
        well-formed tailored output.  If this fails, either the mock fixture
        has a bug or the function has a regression.
        """
        violations = immutable_field_violations(sample_resume, mock_tailored_backend)
        assert violations == [], (
            f"Unexpected immutable field violations:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_bullet_count_issues(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
    ) -> None:
        """
        WHY: Validates the bullet_count_check() function against a correct
        fixture.  Also acts as a regression test for the mock fixture itself.
        """
        issues = bullet_count_check(sample_resume, mock_tailored_backend)
        assert issues == [], (
            f"Unexpected bullet count issues:\n"
            + "\n".join(f"  - {i}" for i in issues)
        )


class TestComprehensiveReport:
    """Tests the all-in-one run_all_metrics() orchestrator."""

    def test_overall_quality_report(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
        backend_jd: str,
    ) -> None:
        """
        WHY: run_all_metrics() is used by the promptfoo assertions.py and any
        CI script that wants a single-call quality gate.  This test ensures it
        runs without error and returns a report with all expected keys.
        """
        report = run_all_metrics(sample_resume, mock_tailored_backend, backend_jd)

        # All expected keys present
        expected_keys = {
            "job_alignment_score",
            "content_preservation",
            "keyword_report",
            "hallucinated_numbers",
            "immutable_violations",
            "bullet_count_issues",
            "relevance",
            "overall_pass",
        }
        assert expected_keys.issubset(set(report.keys())), (
            f"run_all_metrics() report missing keys: {expected_keys - set(report.keys())}"
        )

    def test_overall_pass_is_true_for_good_output(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
        backend_jd: str,
    ) -> None:
        """
        WHY: The mock tailored output was designed to be a high-quality, correct
        tailoring.  overall_pass=True is the expected result.  If this fails,
        the mock fixture has a problem or a metric threshold is miscalibrated.
        """
        report = run_all_metrics(sample_resume, mock_tailored_backend, backend_jd)
        assert report["overall_pass"] is True, (
            f"overall_pass=False for mock output that should be high quality.\n"
            f"alignment={report['job_alignment_score']}, "
            f"preservation={report['content_preservation']}, "
            f"hallucinations={report['hallucinated_numbers']}, "
            f"violations={report['immutable_violations']}"
        )

    def test_report_scores_in_valid_ranges(
        self,
        sample_resume: dict[str, Any],
        mock_tailored_backend: dict[str, Any],
        backend_jd: str,
    ) -> None:
        """
        WHY: Sanity-check that the numeric metrics stay within mathematically
        valid bounds.  Out-of-range scores indicate a bug in the metric functions.
        """
        report = run_all_metrics(sample_resume, mock_tailored_backend, backend_jd)

        assert 0.0 <= report["job_alignment_score"] <= 1.0, (
            f"job_alignment_score out of range: {report['job_alignment_score']}"
        )
        assert 0.0 <= report["content_preservation"] <= 1.0, (
            f"content_preservation out of range: {report['content_preservation']}"
        )
        assert 0.0 <= report["keyword_report"]["injection_rate"] <= 1.0, (
            f"injection_rate out of range: {report['keyword_report']['injection_rate']}"
        )
