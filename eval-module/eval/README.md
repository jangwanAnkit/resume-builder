# Resume Builder — Evaluation Module

This directory contains the complete evaluation and testing framework for the JSON-to-LaTeX resume builder's AI tailoring capability.

---

## Why This Module Exists

The tailoring endpoint is a black box: it accepts a job description and a resume, sends both to an LLM, and returns a rewritten resume. Without systematic evaluation, you cannot answer:

- Did the LLM actually improve keyword alignment with the JD?
- Did it hallucinate new numbers ("improved performance by 90%" when the original said 35%)?
- Did it corrupt immutable fields like company names or dates?
- If you switch from `gpt-4o-mini` to a cheaper model, is the quality still acceptable?

**The eval loop is what drives accuracy.** Every time you change the prompt, switch a model, or update the output schema, run the eval suite to catch regressions before they reach users.

---

## Architecture — Three Levels of Testing

```
eval/
├── Level 1 — test_schema.py     → Structure & integrity (< 1 sec, no API key)
├── Level 2 — test_metrics.py    → Quality metrics      (< 1 sec, no API key)
├── Level 3 — test_golden.py     → Live LLM regression  (5–15 sec, requires API key)
│
├── metrics.py                   → Core metrics (stdlib only, no dependencies)
├── schemas.py                   → Pydantic models (contract enforcement)
├── conftest.py                  → Shared pytest fixtures
│
├── fixtures/
│   ├── sample_resume.json       → Full original resume (all sections)
│   ├── mock_tailored_backend.json  → Pre-computed tailored output (no LLM needed)
│   └── golden_cases/
│       ├── backend_engineer.json   → High-match JD expectations
│       ├── frontend_react.json     → Moderate-match JD expectations
│       └── data_scientist.json     → Low-match JD expectations
│
└── promptfoo/
    ├── promptfooconfig.yaml     → Multi-provider prompt regression config
    ├── tailoring_prompt.txt     → The prompt template under test
    └── assertions.py            → Custom Python assertions for promptfoo
```

### Level 1 — Schema Validation (`test_schema.py`)

**What:** Validates that the tailored output has the correct JSON structure and that immutable fields were not changed.

**Why:** The LaTeX renderer will crash with unhelpful errors if the JSON structure is wrong. Catching this at the schema layer (Pydantic) is faster and more informative than debugging a LaTeX compilation failure.

**Key checks:**
- Experience entry count unchanged
- Company names, start/end dates, and locations not modified
- No empty bullet points
- Project titles and URLs unchanged
- Dates in `YYYY-MM` format
- Full Pydantic schema validation passes
- Relevance score in 1–10 range

**Runs without:** Any API key or network access. < 1 second.

### Level 2 — Quality Metrics (`test_metrics.py`)

**What:** Validates that the tailored output is qualitatively better than the original for the target JD.

**Why:** Structure tests only catch hard bugs. Quality tests catch soft failures: the output passes schema validation but is still a bad tailoring (e.g. the LLM rewrote everything to be generic, or preserved no JD keywords).

**Key checks:**
- Tailored alignment score > original alignment score
- Alignment score ≥ 0.10 (10% JD keyword overlap)
- Content preservation ≥ 0.55 (LLM didn't invent the whole resume)
- No hallucinated numeric values
- At least some JD keywords were injected
- Critical backend keywords present (microservices, docker, kafka, etc.)
- `run_all_metrics()` report structure is valid

**Runs without:** Any API key or network access. < 1 second.

### Level 3 — Golden Regression (`test_golden.py`)

**What:** Makes actual LLM API calls for each golden case and validates that the live output meets all expected criteria.

**Why:** Levels 1 & 2 test against a pre-computed fixture. They catch framework regressions but not model regressions. If OpenAI releases a new model version or you switch providers, these tests tell you whether quality degraded.

**Key checks (per golden case):**
- Relevance score within expected range (high/moderate/low match cases)
- All must-include keywords present in tailored output
- No immutable field violations
- No hallucinated numbers
- Content preservation above per-case threshold
- Job alignment above per-case threshold
- Bullet count unchanged

**Requires:** `OPENAI_API_KEY` (or `LLM_API_KEY`) environment variable. 5–15 sec per test.

---

## How to Run

### Prerequisites

```bash
pip install pytest pydantic
```

### Run Level 1 + 2 only (fast, no API key)

```bash
cd /path/to/project
pytest eval/ -v -m "not slow"
```

Expected output:
```
eval/test_schema.py::TestExperienceIntegrity::test_experience_preserves_entry_count PASSED
eval/test_schema.py::TestExperienceIntegrity::test_immutable_fields_unchanged PASSED
eval/test_schema.py::TestExperienceIntegrity::test_no_empty_bullets PASSED
...
eval/test_metrics.py::TestJobAlignment::test_job_alignment_increases PASSED
eval/test_metrics.py::TestContentPreservation::test_content_preservation_above_threshold PASSED
...
```

### Run all tests including Level 3 (requires API key)

```bash
export OPENAI_API_KEY=sk-...
# Optional: point at a different provider or model
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o-mini
export LLM_BASE_URL=          # leave blank for default OpenAI

pytest eval/ -v
```

### Run only golden tests

```bash
export OPENAI_API_KEY=sk-...
pytest eval/test_golden.py -v -m slow
```

### Run with coverage

```bash
pytest eval/ -v -m "not slow" --cov=eval --cov-report=term-missing
```

---

## Eval Platform Recommendations

This project uses two complementary eval platforms. They serve different purposes and work best together.

### promptfoo — For Prompt Engineering Iteration

**Best for:** Comparing different prompts and models side-by-side. Use when asking: *"Did my prompt change break anything? Which model gives better output?"*

**Why it fits this project:**
- You already work with YAML and JSON — promptfoo's test format is immediately familiar
- Built-in `is-json` assertion validates JSON output before any custom logic runs
- Web UI (`npx promptfoo view`) lets you visually compare GPT-4o-mini vs Gemini vs Cerebras outputs in a table — invaluable when evaluating cost/quality tradeoffs across providers
- Zero Python dependency — works as a standalone `npx` tool with no pip installs
- Free and open source
- CI integration: exits non-zero on failures, works with GitHub Actions out of the box

**When to run:**
- Every time you modify `tailoring_prompt.txt`
- When testing a new model provider
- When doing A/B tests on prompt variants

```bash
cd eval/promptfoo
npx promptfoo eval            # run all test cases
npx promptfoo view            # open web UI at http://localhost:15500
npx promptfoo eval --watch    # re-run on file changes
```

### deepeval — For Advanced Custom Metrics

**Best for:** Custom evaluation metrics in Python with pytest integration. Use when asking: *"How good is my tailoring quality across a large dataset? What's the G-Eval score?"*

**Advantages deepeval adds over promptfoo:**
- Native pytest integration — `from deepeval import assert_test`
- `BaseMetric` classes let you define arbitrarily complex scoring logic
- Built-in metrics: G-Eval, RAGAS, hallucination detection, contextual precision
- Dataset management and CI tracking out of the box
- Scored metrics with LLM-judge explanations

**When to use (later phase):**
- You have 50+ golden cases and need statistical analysis
- You want LLM-as-judge scoring (e.g. "rate the tailoring quality 1–10")
- You want to track metric trends across model versions over time

**Recommendation:** Start with **promptfoo**. The fast iteration cycle (change prompt → run `npx promptfoo eval` → see side-by-side comparison) is the highest-value workflow for this project right now. The custom metrics in `metrics.py` already cover the most important signals (alignment, preservation, hallucination, immutability). Add deepeval when you need LLM-judge scoring or large-scale dataset analysis.

---

## Adding a New Golden Case

1. Create `eval/fixtures/golden_cases/<descriptive_name>.json`:

```json
{
    "name": "DevOps Engineer",
    "jd": "We are looking for a DevOps Engineer...",
    "expected": {
        "min_relevance": 6,
        "max_relevance": 9,
        "must_include_keywords": ["kubernetes", "terraform", "ci/cd"],
        "must_not_change": {
            "experience[0].company": "Tech Innovations Global"
        },
        "min_content_preservation": 0.55,
        "min_job_alignment": 0.10,
        "experience_count": 3,
        "profile_name": "John Doe"
    }
}
```

2. The parametrized test in `test_golden.py` will pick it up automatically on the next run.

3. Optionally add a corresponding test case in `promptfoo/promptfooconfig.yaml` under `tests:`.

---

## Adding a New Metric

1. Add a function to `metrics.py` (no external dependencies).
2. Add corresponding tests to `test_metrics.py`.
3. If the metric is binary (pass/fail), update `run_all_metrics()` to include it in the `overall_pass` calculation.
4. Optionally update `promptfoo/assertions.py` to include the new metric in the promptfoo score.

---

## File Structure in the Main Project

```
project-root/
├── server.py (or server.js)      ← tailoring endpoint
├── data/
│   ├── profile.json
│   ├── experience.json
│   ├── projects.json
│   ├── education.json
│   └── contact.json
├── eval/                         ← this directory
│   ├── README.md
│   ├── metrics.py
│   ├── schemas.py
│   ├── conftest.py
│   ├── test_schema.py
│   ├── test_metrics.py
│   ├── test_golden.py
│   ├── fixtures/
│   └── promptfoo/
└── pytest.ini (or pyproject.toml)
```

### Recommended `pytest.ini`

```ini
[pytest]
testpaths = eval
markers =
    slow: marks tests as slow (requiring LLM API calls) — deselect with -m "not slow"
```

### Recommended CI workflow (`.github/workflows/eval.yml`)

```yaml
name: Eval — Fast Tests

on: [push, pull_request]

jobs:
  eval-fast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pytest pydantic
      - run: pytest eval/ -v -m "not slow" --tb=short

  eval-golden:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    needs: eval-fast
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pytest pydantic
      - run: pytest eval/test_golden.py -v -m slow
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

This configuration runs Level 1 + 2 tests on every push (fast, free), and Level 3 golden tests only on `main` branch merges.

---

## Interpreting Metric Scores

| Metric | Green | Yellow | Red |
|---|---|---|---|
| `job_alignment_score` | ≥ 0.15 | 0.08–0.15 | < 0.08 |
| `content_preservation` | ≥ 0.70 | 0.55–0.70 | < 0.55 |
| `hallucinated_numbers` | 0 items | — | ≥ 1 item |
| `immutable_violations` | 0 items | — | ≥ 1 item |
| `relevance` (high-match JD) | 7–10 | 5–7 | < 5 |
| `relevance` (low-match JD) | 1–4 | 4–5 | > 5 |

A `content_preservation` below 0.55 is a strong signal that the LLM is hallucinating large portions of the resume rather than rewording existing content. Investigate immediately.

A `job_alignment_score` below 0.08 means the tailored resume shares fewer than 8% of tokens with the JD — the tailoring added minimal relevant vocabulary. This usually means the prompt is not doing keyword injection effectively.
