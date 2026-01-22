#!/usr/bin/env python3
"""
Resume Template Renderer

Renders the Jinja2 LaTeX template (resume.tex.j2) using data from JSON config files.
This creates a single source of truth for portfolio and resume content.

Usage:
    python scripts/render_resume.py
    python scripts/render_resume.py --template templates/resume.tex.j2 --output resume.tex
"""

import json
import re
import sys
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, TemplateError
except ImportError:
    print("Error: Jinja2 is required. Install it with: pip install jinja2")
    sys.exit(1)


# Paths relative to script location (assuming scripts/render_resume.py)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATE_DIR = PROJECT_ROOT / "templates"
TEMPLATE_FILE = "resume.tex.j2"
OUTPUT_FILE = "resume.tex" # Output to root of the project


def latex_escape(text: str) -> str:
    """
    Escape special LaTeX characters in text.
    
    Args:
        text: Raw text that may contain LaTeX special characters
        
    Returns:
        Text with special characters properly escaped
    """
    if not text:
        return ""
    
    # Order matters: escape backslash first, then others
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
        ("<", r"\textless{}"),
        (">", r"\textgreater{}"),
    ]
    
    result = text
    for char, escaped in replacements:
        result = result.replace(char, escaped)
    
    return result


def github_username(url: str) -> str:
    """Extract GitHub username from URL."""
    if not url:
        return ""
    match = re.search(r"github\.com/([^/]+)", url)
    return match.group(1) if match else url


def linkedin_username(url: str) -> str:
    """Extract LinkedIn username from URL."""
    if not url:
        return ""
    match = re.search(r"linkedin\.com/in/([^/]+)", url)
    return match.group(1) if match else url


def join_tech(technologies: list) -> str:
    """Join technology list into comma-separated string."""
    if not technologies:
        return ""
    # Handle both {"name": "Tech"} objects and plain strings
    names = []
    for tech in technologies:
        if isinstance(tech, dict):
            names.append(tech.get("name", ""))
        else:
            names.append(str(tech))
    return ", ".join(filter(None, names))


def format_duration(start_date: str, end_date: str | None = None) -> str:
    """
    Format duration string from startDate and endDate.
    e.g., "Jan 2025 – Present" or "May 2022 – Aug 2024"
    """
    months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]
    
    def format_date(date_str: str) -> str:
        parts = date_str.split("-")
        year = int(parts[0])
        month = int(parts[1])
        return f"{months[month - 1]} {year}"
    
    start = format_date(start_date)
    end = format_date(end_date) if end_date else "Present"
    
    return f"{start} -- {end}"


def load_json_file(filepath: Path) -> dict:
    """Load and parse a JSON file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Config file not found: {filepath}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {filepath}: {e}")
        sys.exit(1)


def load_all_configs(data_dir: Path) -> dict:
    """
    Load all JSON config files and merge into a single context.
    
    Returns:
        Dictionary with all config data merged for template rendering
    """
    context = {}
    
    # Load individual config files
    config_files = {
        "profile": "profile.json",
        "experience_data": "experience.json",
        "projects_data": "projects.json",
        "skills_data": "skills.json",
        "education_data": "education.json",
        "contact": "contact.json",
        "seo": "seo.json",
    }
    
    for key, filename in config_files.items():
        filepath = data_dir / filename
        if filepath.exists():
            context[key] = load_json_file(filepath)
    
    # Flatten nested structures for easier template access
    # Experience: experience_data.experience -> experience
    if "experience_data" in context and "experience" in context["experience_data"]:
        context["experience"] = context["experience_data"]["experience"]
    
    # Projects: projects_data.projects -> projects
    if "projects_data" in context and "projects" in context["projects_data"]:
        context["projects"] = context["projects_data"]["projects"]
    
    # Skills: skills_data.categories -> skills
    if "skills_data" in context and "categories" in context["skills_data"]:
        context["skills"] = context["skills_data"]["categories"]
    
    # Education: education_data.education -> education
    if "education_data" in context and "education" in context["education_data"]:
        context["education"] = context["education_data"]["education"]
    
    return context


def create_jinja_env(template_dir: Path) -> Environment:
    """
    Create a Jinja2 environment with LaTeX-safe delimiters.
    
    Uses (( )) for blocks and ((= =)) for variables to avoid
    conflicts with LaTeX's { } syntax.
    """
    env = Environment(
        loader=FileSystemLoader(template_dir),
        block_start_string="((",
        block_end_string="))",
        variable_start_string="((=",
        variable_end_string="=))",
        comment_start_string="((#",
        comment_end_string="#))",
        trim_blocks=True,
        lstrip_blocks=True,
    )
    
    # Register custom filters
    env.filters["latex_escape"] = latex_escape
    env.filters["github_username"] = github_username
    env.filters["linkedin_username"] = linkedin_username
    env.filters["join_tech"] = join_tech
    env.filters["format_duration"] = format_duration
    
    return env


def render_resume(
    template_dir: Path = TEMPLATE_DIR,
    template_file: str = TEMPLATE_FILE,
    output_file: str = OUTPUT_FILE,
    data_dir: Path = DATA_DIR,
) -> bool:
    """
    Render the resume template with config data.
    
    Args:
        template_dir: Directory containing the template file
        template_file: Name of the Jinja2 template file
        output_file: Name of the output .tex file
        data_dir: Directory containing JSON config files
        
    Returns:
        True if rendering succeeded, False otherwise
    """
    print(f"Loading config files from: {data_dir}")
    context = load_all_configs(data_dir)
    
    # Validate required data
    required_keys = ["profile", "experience", "education"]
    missing = [k for k in required_keys if k not in context or not context[k]]
    if missing:
        print(f"Error: Missing required config data: {', '.join(missing)}")
        return False
    
    print(f"Loaded configs: {list(context.keys())}")
    
    # Create Jinja environment and load template
    print(f"Loading template: {template_dir / template_file}")
    env = create_jinja_env(template_dir)
    
    try:
        template = env.get_template(template_file)
    except TemplateError as e:
        print(f"Error loading template: {e}")
        return False
    
    # Render template
    try:
        rendered = template.render(**context)
    except TemplateError as e:
        print(f"Error rendering template: {e}")
        return False
    
    # Write output
    output_path = PROJECT_ROOT / output_file
    print(f"Writing output to: {output_path}")
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(rendered)
    except IOError as e:
        print(f"Error writing output file: {e}")
        return False
    
    print("Resume template rendered successfully!")
    return True


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Render LaTeX resume from Jinja2 template and JSON configs"
    )
    parser.add_argument(
        "--template",
        default=str(TEMPLATE_DIR / TEMPLATE_FILE),
        help="Path to Jinja2 template file",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / OUTPUT_FILE),
        help="Path to output .tex file",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DATA_DIR),
        help="Directory containing JSON config files",
    )
    
    args = parser.parse_args()
    
    # Convert paths
    template_path = Path(args.template)
    output_path = Path(args.output)
    data_dir = Path(args.data_dir)
    
    success = render_resume(
        template_dir=template_path.parent,
        template_file=template_path.name,
        output_file=output_path.name,
        data_dir=data_dir,
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
