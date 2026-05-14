"""
schemas.py — Pydantic v2 models for validating resume-builder JSON structures.

These schemas serve as the contract between the LLM output and the rest of the
system.  Any tailored response that fails Pydantic validation is rejected before
it reaches the LaTeX renderer — preventing corrupt PDF generation.

Why schema validation matters
------------------------------
LLMs occasionally return structurally malformed JSON: missing required fields,
wrong types, swapped field names.  Catching this at the schema layer (fast,
zero-LLM-cost) saves you from debugging LaTeX compilation errors later.

The ``field_validator`` decorators enforce business-logic constraints that go
beyond type checking (e.g. date format, URL non-mutation).
"""

from __future__ import annotations

import re
from typing import Optional, List, Literal

from pydantic import BaseModel, HttpUrl, field_validator, model_validator


# ---------------------------------------------------------------------------
# Date format helper
# ---------------------------------------------------------------------------

_YYYY_MM_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def _validate_date_format(v: Optional[str]) -> Optional[str]:
    """Assert value is None or matches YYYY-MM."""
    if v is not None and not _YYYY_MM_PATTERN.match(v):
        raise ValueError(f"Date must be in YYYY-MM format, got: {v!r}")
    return v


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class SocialsSchema(BaseModel):
    """Social links on the profile card."""

    github: Optional[str] = None
    linkedin: Optional[str] = None

    model_config = {"extra": "allow"}


class ResumeContactSchema(BaseModel):
    """Phone / website embedded in profile.resume."""

    phone: Optional[str] = None
    website: Optional[str] = None

    model_config = {"extra": "allow"}


class ProfileSchema(BaseModel):
    """
    Validates profile.json / the profile section of the tailored API response.

    Immutable constraints enforced by the application layer (not Pydantic):
      - ``name`` must never change between original and tailored.

    The ``bio`` and ``title`` fields are intentionally mutable — the LLM may
    rewrite them to better match the JD.
    """

    name: str
    title: str
    bio: str
    avatar: Optional[str] = None
    socials: Optional[SocialsSchema] = None
    resume: Optional[ResumeContactSchema] = None

    model_config = {"extra": "allow"}

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Profile name must not be empty.")
        return v

    @field_validator("bio")
    @classmethod
    def bio_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Bio must not be empty.")
        return v


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------

class ExperienceEntry(BaseModel):
    """
    A single job entry in experience.json.

    Immutable fields (validated against the original at runtime in test_schema.py):
      - ``company``
      - ``startDate``
      - ``endDate``
      - ``location``

    Mutable fields (the LLM may rewrite these):
      - ``role``      — may be adjusted to better reflect JD language
      - ``details``   — bullets are rewritten; count must stay the same
    """

    company: str
    role: str
    startDate: str
    endDate: Optional[str] = None
    location: str
    logo: Optional[str] = None
    details: List[str]

    @field_validator("startDate")
    @classmethod
    def validate_start_date(cls, v: str) -> str:
        return _validate_date_format(v)  # type: ignore[return-value]

    @field_validator("endDate", mode="before")
    @classmethod
    def validate_end_date(cls, v: Optional[str]) -> Optional[str]:
        return _validate_date_format(v)

    @field_validator("details")
    @classmethod
    def details_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("An experience entry must have at least one bullet point.")
        for i, bullet in enumerate(v):
            if not bullet.strip():
                raise ValueError(f"Bullet {i} is an empty string.")
        return v

    @field_validator("company")
    @classmethod
    def company_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Company name must not be empty.")
        return v


class ExperienceSchema(BaseModel):
    """Wrapper matching the experience.json top-level structure."""

    experience: List[ExperienceEntry]

    @field_validator("experience")
    @classmethod
    def at_least_one_entry(cls, v: List[ExperienceEntry]) -> List[ExperienceEntry]:
        if not v:
            raise ValueError("Experience list must not be empty.")
        return v


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectEntry(BaseModel):
    """
    A single project entry.

    Immutable fields:
      - ``title``   — identifies the project; must not change
      - ``liveUrl`` — external URL; must not change

    Mutable fields:
      - ``description``    — may be rewritten to highlight relevant aspects
      - ``technologies``   — order may be reordered; no new techs invented
    """

    title: str
    description: str
    technologies: List[str]
    liveUrl: Optional[str] = None
    status: Optional[Literal["ongoing", "completed", "archived"]] = None

    model_config = {"extra": "allow"}

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Project title must not be empty.")
        return v

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Project description must not be empty.")
        return v

    @field_validator("technologies")
    @classmethod
    def at_least_one_technology(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("Project must list at least one technology.")
        return v


class ProjectsSchema(BaseModel):
    """Wrapper matching the projects.json top-level structure."""

    projects: List[ProjectEntry]


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------

class EducationEntry(BaseModel):
    """Single education entry — treated as fully immutable."""

    institution: str
    location: Optional[str] = None
    degree: str
    duration: Optional[str] = None

    model_config = {"extra": "allow"}


class EducationSchema(BaseModel):
    """Wrapper matching the education.json top-level structure."""

    education: List[EducationEntry]


# ---------------------------------------------------------------------------
# Full Tailored API Response
# ---------------------------------------------------------------------------

class TailoredResponse(BaseModel):
    """
    Validates the complete response from the ``/api/tailor`` endpoint.

    The endpoint returns:
    ```json
    {
        "profile":            { ... },
        "experience":         { "experience": [ ... ] },
        "projects":           { "projects": [ ... ] },
        "relevance":          8,
        "relevance_analysis": "..."
    }
    ```

    ``education`` and ``contact`` are not returned by the tailoring endpoint
    (they are considered fully immutable and passed through unchanged).

    Raises ``pydantic.ValidationError`` if the structure is malformed.
    """

    profile: ProfileSchema
    experience: ExperienceSchema
    projects: ProjectsSchema
    relevance: int
    relevance_analysis: str

    @field_validator("relevance")
    @classmethod
    def relevance_in_range(cls, v: int) -> int:
        if not (1 <= v <= 10):
            raise ValueError(f"Relevance must be between 1 and 10, got {v}.")
        return v

    @field_validator("relevance_analysis")
    @classmethod
    def analysis_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("relevance_analysis must not be empty.")
        return v

    @model_validator(mode="after")
    def experience_entry_count_sane(self) -> "TailoredResponse":
        """Sanity check: at least one experience entry must be present."""
        if not self.experience.experience:
            raise ValueError("Tailored experience must contain at least one entry.")
        return self
