"""
metrics.py — Core evaluation metrics for the resume-builder tailoring pipeline.

These metrics are intentionally dependency-free (stdlib only) so they can run
in any environment without pip installs. They implement the ResumeFlow methodology
of measuring keyword overlap and content preservation as proxy signals for
tailoring quality.

Why these metrics matter
------------------------
LLM tailoring is a black box. Without systematic measurement you cannot tell
whether a prompt change improved or degraded output quality. These metrics give
you a quantitative signal across three orthogonal dimensions:

  1. Job alignment   — does the tailored resume use the right vocabulary?
  2. Preservation    — did the LLM keep the candidate's real accomplishments?
  3. Integrity       — did the LLM invent facts (hallucination) or corrupt
                       immutable fields (company names, dates, URLs)?

Run them on every tailored output before you trust it in production.
"""

from __future__ import annotations

import re
import json
from collections import Counter
from typing import Any


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    """
    Convert *text* to a normalised list of lowercase word tokens.

    Strips punctuation, lowercases everything, and discards single-character
    tokens.  Simple but sufficient for overlap-based similarity metrics.

    Args:
        text: Raw string (multi-sentence, multi-paragraph).

    Returns:
        List of lowercase word tokens with length >= 2.

    Example:
        >>> tokenize("Led migration to microservices (Docker, Kubernetes).")
        ['led', 'migration', 'to', 'microservices', 'docker', 'kubernetes']
    """
    text = text.lower()
    tokens = re.findall(r"[a-z0-9][a-z0-9'/.-]*[a-z0-9]|[a-z0-9]", text)
    return [t for t in tokens if len(t) >= 2]


# ---------------------------------------------------------------------------
# Job Alignment Score
# ---------------------------------------------------------------------------

def job_alignment_score(tailored_text: str, jd_text: str) -> float:
    """
    Compute the token-overlap coefficient between the tailored resume and the JD.

    This is the primary signal for whether the AI successfully incorporated
    relevant JD vocabulary into the resume.  Implemented as:

        score = |tokens(tailored) ∩ tokens(jd)| / |tokens(jd)|

    A score of 0.0 means zero shared vocabulary; 1.0 means the resume contains
    every word from the JD (ceiling not meaningful — the floor matters more).

    ResumeFlow benchmarks suggest well-tailored resumes reach 0.15–0.35 on this
    metric for typical senior-engineer JDs.

    Args:
        tailored_text: Flat text representation of the tailored resume.
        jd_text:       The full job description text.

    Returns:
        Float in [0, 1].
    """
    tailored_tokens = set(tokenize(tailored_text))
    jd_tokens = set(tokenize(jd_text))

    if not jd_tokens:
        return 0.0

    overlap = tailored_tokens & jd_tokens
    return len(overlap) / len(jd_tokens)


# ---------------------------------------------------------------------------
# Content Preservation Score
# ---------------------------------------------------------------------------

def content_preservation_score(original_text: str, tailored_text: str) -> float:
    """
    Measure how much of the *original* resume content survived tailoring.

    Computed as the Jaccard similarity between token *bags* (not sets), which
    accounts for token frequency:

        score = sum(min(c_orig, c_tailored)) / sum(max(c_orig, c_tailored))

    A score of 1.0 means no content was removed or added (identical).
    Below 0.40 indicates heavy rewriting — likely hallucination risk territory.
    A healthy range is 0.55–0.80: the AI rewrote the framing but kept the facts.

    Args:
        original_text: Flat text of the original (un-tailored) resume.
        tailored_text: Flat text of the tailored resume.

    Returns:
        Float in [0, 1].
    """
    orig_counts = Counter(tokenize(original_text))
    tail_counts = Counter(tokenize(tailored_text))

    all_tokens = set(orig_counts) | set(tail_counts)
    if not all_tokens:
        return 1.0

    intersection = sum(min(orig_counts[t], tail_counts[t]) for t in all_tokens)
    union = sum(max(orig_counts[t], tail_counts[t]) for t in all_tokens)

    return intersection / union if union > 0 else 1.0


# ---------------------------------------------------------------------------
# Keyword Injection Report
# ---------------------------------------------------------------------------

def keyword_injection_report(
    original_text: str,
    tailored_text: str,
    jd_text: str,
) -> dict[str, Any]:
    """
    Produce a detailed report on how JD keywords were handled during tailoring.

    Classifies each unique JD keyword into one of three buckets:
      - added:      present in tailored but NOT in original (newly injected)
      - maintained: present in both original and tailored
      - lost:       present in original but NOT in tailored

    This is your primary diagnostic tool when alignment score drops: you can
    see exactly which keywords were removed or missed.

    Args:
        original_text: Flat text of the original resume.
        tailored_text: Flat text of the tailored resume.
        jd_text:       Full JD text.

    Returns:
        Dict with keys: ``added``, ``maintained``, ``lost``, ``injection_rate``
        (fraction of JD keywords that were added or maintained in tailored).
    """
    jd_keywords = set(tokenize(jd_text))
    orig_tokens = set(tokenize(original_text))
    tail_tokens = set(tokenize(tailored_text))

    added = sorted(jd_keywords & tail_tokens - orig_tokens)
    maintained = sorted(jd_keywords & orig_tokens & tail_tokens)
    lost = sorted(jd_keywords & orig_tokens - tail_tokens)

    total_jd = len(jd_keywords)
    covered = len(added) + len(maintained)
    injection_rate = covered / total_jd if total_jd > 0 else 0.0

    return {
        "added": added,
        "maintained": maintained,
        "lost": lost,
        "jd_keyword_count": total_jd,
        "covered_count": covered,
        "injection_rate": round(injection_rate, 4),
    }


# ---------------------------------------------------------------------------
# Hallucination Check
# ---------------------------------------------------------------------------

# Pattern matches standalone numbers, percentages, multipliers, and dollar
# amounts that are commonly hallucinated (e.g. "reduced latency by 70%").
_NUMBER_PATTERN = re.compile(
    r"""
    (?<!\w)
    (?:
        \$[\d,]+(?:\.\d+)?[kmb]?   |   # dollar amounts: $1.2M, $500k
        \d+(?:\.\d+)?[x%]          |   # ratios/percentages: 35%, 10x
        \d{1,3}(?:,\d{3})+         |   # large numbers with commas: 10,000
        \d+(?:\.\d+)?(?!\s*[-:/])      # bare numbers (excluding dates)
    )
    (?!\w)
    """,
    re.VERBOSE | re.IGNORECASE,
)


def hallucination_check(original_text: str, tailored_text: str) -> list[str]:
    """
    Detect numeric metrics or quantified claims present in *tailored* but
    absent from the *original* resume — a strong hallucination signal.

    The LLM is instructed not to invent facts, but it sometimes does anyway.
    This function extracts all numeric tokens from both texts and flags any
    that appear in the tailored output but not the original.

    False-positive note: reformatting an existing number (e.g. "500,000" →
    "500k") will flag it.  Review flagged items manually.

    Args:
        original_text: Flat text of the original resume.
        tailored_text: Flat text of the tailored resume.

    Returns:
        List of numeric strings found in tailored but not in original.
        Empty list = no hallucinated numbers detected.
    """
    original_numbers = set(_NUMBER_PATTERN.findall(original_text.lower()))
    tailored_numbers = set(_NUMBER_PATTERN.findall(tailored_text.lower()))
    return sorted(tailored_numbers - original_numbers)


# ---------------------------------------------------------------------------
# Immutable Field Violations
# ---------------------------------------------------------------------------

def immutable_field_violations(
    original_data: dict[str, Any],
    tailored_data: dict[str, Any],
) -> list[str]:
    """
    Verify that structurally immutable fields were not altered by the LLM.

    The tailoring prompt instructs the LLM to never change: company names,
    start/end dates, locations, project titles, and project URLs.  These fields
    are ground truth about the candidate's career and must not be fabricated.

    This function compares the original and tailored data structures field by
    field and returns a human-readable description of every violation found.

    Args:
        original_data: The original resume data dict (experience + projects).
        tailored_data: The tailored API response dict.

    Returns:
        List of violation strings.  Empty list = no violations.
    """
    violations: list[str] = []

    # --- Experience immutable fields ---
    orig_exp = original_data.get("experience", {}).get("experience", [])
    tail_exp = tailored_data.get("experience", {}).get("experience", [])

    for i, (orig, tail) in enumerate(zip(orig_exp, tail_exp)):
        for field in ("company", "startDate", "endDate", "location"):
            ov = orig.get(field)
            tv = tail.get(field)
            if ov != tv:
                violations.append(
                    f"experience[{i}].{field}: expected {ov!r}, got {tv!r}"
                )

    # --- Project immutable fields ---
    orig_proj = original_data.get("projects", {}).get("projects", [])
    tail_proj = tailored_data.get("projects", {}).get("projects", [])

    for i, (orig, tail) in enumerate(zip(orig_proj, tail_proj)):
        for field in ("title", "liveUrl"):
            ov = orig.get(field)
            tv = tail.get(field)
            if ov != tv:
                violations.append(
                    f"projects[{i}].{field}: expected {ov!r}, got {tv!r}"
                )

    # --- Profile immutable fields ---
    orig_profile = original_data.get("profile", {})
    tail_profile = tailored_data.get("profile", {})
    for field in ("name",):
        ov = orig_profile.get(field)
        tv = tail_profile.get(field)
        if ov != tv:
            violations.append(f"profile.{field}: expected {ov!r}, got {tv!r}")

    return violations


# ---------------------------------------------------------------------------
# Bullet Count Check
# ---------------------------------------------------------------------------

def bullet_count_check(
    original_data: dict[str, Any],
    tailored_data: dict[str, Any],
) -> list[str]:
    """
    Verify that the tailored resume has the same number of experience entries
    and that each entry preserves its original bullet count.

    The LLM is instructed to rewrite bullets but not add or remove them.
    Structural changes (dropping an entire job, adding phantom bullets) are
    hard bugs that this check catches immediately.

    Args:
        original_data: Original resume data dict.
        tailored_data: Tailored API response dict.

    Returns:
        List of violation strings.  Empty list = counts match.
    """
    issues: list[str] = []

    orig_exp = original_data.get("experience", {}).get("experience", [])
    tail_exp = tailored_data.get("experience", {}).get("experience", [])

    if len(orig_exp) != len(tail_exp):
        issues.append(
            f"Experience entry count mismatch: expected {len(orig_exp)}, got {len(tail_exp)}"
        )
        # Can't compare per-entry if counts differ
        return issues

    for i, (orig, tail) in enumerate(zip(orig_exp, tail_exp)):
        orig_bullets = len(orig.get("details", []))
        tail_bullets = len(tail.get("details", []))
        if orig_bullets != tail_bullets:
            company = orig.get("company", f"entry[{i}]")
            issues.append(
                f"{company}: bullet count changed from {orig_bullets} to {tail_bullets}"
            )

    return issues


# ---------------------------------------------------------------------------
# Flatten Resume to Text
# ---------------------------------------------------------------------------

def flatten_resume_to_text(data: dict[str, Any]) -> str:
    """
    Convert the nested resume JSON structure into a single flat string.

    This helper feeds data from the structured JSON into the text-based
    similarity and keyword functions.  It concatenates all human-readable
    string fields: bio, role, bullets, project descriptions, and technologies.

    Fields that are URLs, dates, or phone numbers are excluded so they don't
    pollute keyword overlap calculations.

    Args:
        data: Resume dict — either original (full) or tailored API response.

    Returns:
        Single whitespace-separated string of all text content.
    """
    parts: list[str] = []

    # Profile
    profile = data.get("profile", {})
    for field in ("name", "title", "bio"):
        if v := profile.get(field):
            parts.append(str(v))

    # Experience
    for entry in data.get("experience", {}).get("experience", []):
        for field in ("company", "role", "location"):
            if v := entry.get(field):
                parts.append(str(v))
        for detail in entry.get("details", []):
            parts.append(str(detail))

    # Projects
    for project in data.get("projects", {}).get("projects", []):
        for field in ("title", "description"):
            if v := project.get(field):
                parts.append(str(v))
        for tech in project.get("technologies", []):
            parts.append(str(tech))

    # Education (usually not tailored, but include for completeness)
    for edu in data.get("education", {}).get("education", []):
        for field in ("institution", "degree"):
            if v := edu.get(field):
                parts.append(str(v))

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Run All Metrics
# ---------------------------------------------------------------------------

def run_all_metrics(
    original_data: dict[str, Any],
    tailored_data: dict[str, Any],
    jd_text: str,
) -> dict[str, Any]:
    """
    Run the full evaluation suite and return a comprehensive report dict.

    This is the single entry point for running all metrics in one shot.
    Suitable for CI scripts, the promptfoo assertions.py, and ad-hoc debugging.

    The returned report includes:
      - ``job_alignment_score``   — float [0, 1]
      - ``content_preservation``  — float [0, 1]
      - ``keyword_report``        — injected/maintained/lost breakdown
      - ``hallucinated_numbers``  — list of suspicious numeric tokens
      - ``immutable_violations``  — list of immutable field change descriptions
      - ``bullet_count_issues``   — list of count mismatch descriptions
      - ``overall_pass``          — bool, True if all integrity checks pass and
                                    alignment + preservation meet thresholds
      - ``relevance``             — int from the API response (0 if absent)

    Args:
        original_data: The original (full) resume data dict.
        tailored_data: The tailored API response dict.
        jd_text:       The full job description text.

    Returns:
        Dict with all metric results.
    """
    orig_text = flatten_resume_to_text(original_data)
    tail_text = flatten_resume_to_text(tailored_data)

    alignment = job_alignment_score(tail_text, jd_text)
    preservation = content_preservation_score(orig_text, tail_text)
    kw_report = keyword_injection_report(orig_text, tail_text, jd_text)
    hallucinations = hallucination_check(orig_text, tail_text)
    imm_violations = immutable_field_violations(original_data, tailored_data)
    bullet_issues = bullet_count_check(original_data, tailored_data)
    relevance = tailored_data.get("relevance", 0)

    overall_pass = (
        alignment >= 0.08
        and preservation >= 0.55
        and len(hallucinations) == 0
        and len(imm_violations) == 0
        and len(bullet_issues) == 0
    )

    return {
        "job_alignment_score": round(alignment, 4),
        "content_preservation": round(preservation, 4),
        "keyword_report": kw_report,
        "hallucinated_numbers": hallucinations,
        "immutable_violations": imm_violations,
        "bullet_count_issues": bullet_issues,
        "relevance": relevance,
        "overall_pass": overall_pass,
    }
