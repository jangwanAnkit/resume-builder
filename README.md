# Automated Resume Builder

Manage your professional profile via JSON and get a high-quality LaTeX resume PDF automatically. No local LaTeX installation or syntax knowledge required—GitHub Actions handles the heavy lifting.

[**📄 View Sample Resume**](https://github.com/jangwanAnkit/resume-builder/releases/download/latest/resume.pdf)

## Features

- **JSON-based Source of Truth**: Manage all your data (profile, experience, education, skills, projects) in structured JSON files.
- **LaTeX Professionalism**: Utilizes a professional LaTeX template with Jinja2 rendering for a premium look.
- **Automated Workflow**: GitHub Actions automatically compiles your LaTeX source into a PDF on every push to `main`.

## Setup

1.  **Use as Template / Fork**: Click the **"Use this template"** button at the top of the repository (or simply **Fork** it) to create your own copy.
2.  **Install Dependencies** (for local testing):
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### 1. Update Data
Edit the JSON files in the `data/` directory. The structure is intuitive and keeps your data clean:
- `profile.json`: Name, title, bio, and social links.
- `experience.json`: Professional work history.
- `education.json`: Academic background.
- `skills.json`: Categorized technical skills.
- `projects.json`: Highlighted projects.
- `contact.json`: Contact information and location.

### 2. Generate LaTeX (Local)
To preview the generated LaTeX code:
```bash
python scripts/render_resume.py
```

### 3. Compile to PDF
- **Automatic**: Simply push your changes to GitHub. The workflow will trigger automatically.
- **Local (Optional)**: If you have a LaTeX distribution (like TeX Live) installed:
  ```bash
  pdflatex resume.tex
  ```

## Accessing your PDF
Once you push your code to GitHub, the **CI/CD pipeline** kicks in. You can access your generated PDF by:
1.  Checking the [**Latest Release**](https://github.com/jangwanAnkit/resume-builder/releases/download/latest/resume.pdf) directly.
2.  Navigating to the **"Releases"** section on the right side of your GitHub repository.
3.  Downloading the `resume.pdf` asset from the **"Latest"** tag.
4. You can check the **"Actions"** tab to see the build progress and logs.
