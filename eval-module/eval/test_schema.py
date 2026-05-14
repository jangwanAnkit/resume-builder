"""
Test Suite — Level 1: Schema Validation
=========================================
Validates that resume JSON (original and tailored) conforms to expected
Pydantic schemas.  These tests run WITHOUT an LLM — purely structural checks.

Run:  pytest eval/test_schema.py -v

Tests are grouped into four classes:
  TestExperienceIntegrity  — immutable fields, entry count, bullet integrity
  TestProfileIntegrity     — name, bio, title constraints
  TestProjectIntegrity     — project structure validation
  TestSchemaValidation     — full TailoredResponse + edge-case rejection
"""

import pytest
from pydantic import ValidationError

from schemas import (
    ExperienceEntry,
    ExperienceSchema,
    ProfileSchema,
    ProjectEntry,
    ProjectsSchema,
    EducationEntry,
    EducationSchema,
    TailoredResponse,
)


# ===================================================================
# Experience Integrity
# ===================================================================


class TestExperienceIntegrity:
    """Ensure experience data survives tailoring without structural damage."""

    def test_valid_experience(self, sample_resume):
        """Experience from sample resume should validate."""
        result = ExperienceSchema(**sample_resume["experience"])
        assert len(result.experience) == 3

    def test_preserves_entry_count(self, sample_resume, mock_tailored_backend):
        """Tailoring must not drop experience entries."""
        original = ExperienceSchema(**sample_resume["experience"])
        tailored = ExperienceSchema(**mock_tailored_backend["experience"])
        assert len(tailored.experience) == len(original.experience), (
            f"Experience count changed: {len(original.experience)} → {len(tailored.experience)}"
        )

    def test_immutable_fields_preserved(self, sample_resume, mock_tailored_backend):
        """Company names, dates, and locations must not change during tailoring."""
        orig = sample_resume["experience"]["experience"]
        tail = mock_tailored_backend["experience"]["experience"]

        for i, (o, t) in enumerate(zip(orig, tail)):
            assert o["company"] == t["company"], f"experience[{i}].company changed"
            assert o["startDate"] == t["startDate"], f"experience[{i}].startDate changed"
            assert o["endDate"] == t["endDate"], f"experience[{i}].endDate changed"
            assert o["location"] == t["location"], f"experience[{i}].location changed"

    def test_empty_details_rejected(self):
        """Experience entry with no bullet points must fail."""
        with pytest.raises(ValidationError):
            ExperienceEntry(
                company="Acme",
                role="Engineer",
                startDate="2021-06",
                endDate=None,
                location="NYC",
                details=[],
            )

    def test_blank_bullet_rejected(self):
        """Experience entry with a blank bullet point must fail."""
        with pytest.raises(ValidationError):
            ExperienceEntry(
                company="Acme",
                role="Engineer",
                startDate="2021-06",
                endDate=None,
                location="NYC",
                details=["Good work", "  ", "More work"],
            )

    def test_bad_date_format_rejected(self):
        """Dates not in YYYY-MM format must fail."""
        with pytest.raises(ValidationError):
            ExperienceEntry(
                company="Acme",
                role="Engineer",
                startDate="June 2021",
                endDate=None,
                location="NYC",
                details=["Did things"],
            )

    def test_empty_company_rejected(self):
        """Empty company name must fail."""
        with pytest.raises(ValidationError):
            ExperienceEntry(
                company="",
                role="Engineer",
                startDate="2021-06",
                endDate=None,
                location="NYC",
                details=["Did things"],
            )

    def test_tailored_experience_valid(self, mock_tailored_backend):
        """Tailored experience should pass schema validation."""
        result = ExperienceSchema(**mock_tailored_backend["experience"])
        assert len(result.experience) >= 1


# ===================================================================
# Profile Integrity
# ===================================================================


class TestProfileIntegrity:
    """Ensure profile data is valid and immutable fields are preserved."""

    def test_valid_profile(self, sample_resume):
        """Profile from sample resume should validate."""
        result = ProfileSchema(**sample_resume["profile"])
        assert result.name == "John Doe"
        assert len(result.bio) > 10

    def test_empty_name_rejected(self):
        """Profile with empty name must fail."""
        with pytest.raises(ValidationError):
            ProfileSchema(name="", title="Engineer", bio="A solid engineer with experience.")

    def test_empty_bio_rejected(self):
        """Profile with empty bio must fail."""
        with pytest.raises(ValidationError):
            ProfileSchema(name="John", title="Engineer", bio="")

    def test_tailored_profile_valid(self, mock_tailored_backend):
        """Tailored output profile should also validate."""
        result = ProfileSchema(**mock_tailored_backend["profile"])
        assert result.name == "John Doe"

    def test_name_unchanged_after_tailoring(self, sample_resume, mock_tailored_backend):
        """Profile name must never change during tailoring."""
        assert sample_resume["profile"]["name"] == mock_tailored_backend["profile"]["name"]


# ===================================================================
# Project Integrity
# ===================================================================


class TestProjectIntegrity:
    """Ensure project data structure is valid."""

    def test_valid_projects(self, sample_resume):
        result = ProjectsSchema(**sample_resume["projects"])
        assert len(result.projects) >= 1

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            ProjectEntry(title="", description="A project", technologies=["Python"])

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            ProjectEntry(title="My Project", description="", technologies=["Python"])

    def test_tailored_projects_valid(self, mock_tailored_backend):
        result = ProjectsSchema(**mock_tailored_backend["projects"])
        assert len(result.projects) >= 1


# ===================================================================
# Full Schema Validation
# ===================================================================


class TestSchemaValidation:
    """Test the complete TailoredResponse schema and edge cases."""

    def test_valid_tailored_output(self, mock_tailored_backend):
        """The full mock tailored output should validate."""
        result = TailoredResponse(**mock_tailored_backend)
        assert 1 <= result.relevance <= 10
        assert len(result.relevance_analysis) > 10

    def test_relevance_out_of_range_rejected(self, mock_tailored_backend):
        """Relevance outside 1-10 must fail."""
        bad = {**mock_tailored_backend, "relevance": 15}
        with pytest.raises(ValidationError):
            TailoredResponse(**bad)

    def test_zero_relevance_rejected(self, mock_tailored_backend):
        """Relevance of 0 must fail."""
        bad = {**mock_tailored_backend, "relevance": 0}
        with pytest.raises(ValidationError):
            TailoredResponse(**bad)

    def test_empty_analysis_rejected(self, mock_tailored_backend):
        """Empty relevance_analysis must fail."""
        bad = {**mock_tailored_backend, "relevance_analysis": ""}
        with pytest.raises(ValidationError):
            TailoredResponse(**bad)
