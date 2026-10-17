# Modernize Sphinx Documentation with Shibuya Theme and Extensions Design

**Issue**: #708  
**Date**: 2026-10-18  
**Status**: Proposed  

---

## 1. Intent and Why
The current CB-POS documentation relies on Sphinx's default `alabaster` theme, which lacks modern navigation, mobile responsiveness, seamless light/dark mode toggling, social/repository links, and visual hierarchy. As CB-POS expands its retail POS platform and trilingual capabilities, the technical documentation, API references, and architecture guides must provide a first-class reading experience for developers, contributors, and operators.

This project upgrades the documentation system to the modern **Shibuya** theme, enables essential built-in Sphinx extensions (including `intersphinx`, `todo`, `duration`, and `githubpages`), and integrates plugins for project contributors and version warning banners.

---

## 2. User Decisions
1. **Scope**: Full modernization per Issue #708.
2. **Theme**: Shibuya (`shibuya>=2026.7.12`) with automatic system-based dark/light mode switching (`color_mode = "auto"`), responsive sidebar navigation, and repository integration.
3. **Repository Links**: Direct navigation to `https://github.com/HMAHD/CB-POS`.
4. **Plugins**:
   - `sphinx_contributors`: Dynamic project contributor attribution via GitHub API with graceful local/offline fallback.
   - `versionwarning.extension`: Top-of-page warning banner notifying readers if browsing older releases or development branches.
   - `sphinx.ext.intersphinx`: Cross-referencing Python standard library, SQLAlchemy, and PyQt6 documentation.
   - `sphinx.ext.todo`, `sphinx.ext.duration`, `sphinx.ext.githubpages`.
5. **Warning Suppression & Clean Build**: Add internal workspace/planning directories (`docs/superpowers/**`, `docs/agents/**`, `docs/archive/**`, `docs/adr/**`) to Sphinx's `exclude_patterns` so the build is clean and warning-free.

---

## 3. Goals, Non-Goals, and Anti-Goals

### Goals
- Add `shibuya`, `sphinx-version-warning`, and `sphinx-contributors` to `[dependency-groups] dev` in `pyproject.toml`.
- Configure `html_theme = "shibuya"` and `html_theme_options` in `docs/conf.py`:
  - `color_mode = "auto"` (supports light, dark, and system preference).
  - `github_url = "https://github.com/HMAHD/CB-POS"`.
  - Curated top `nav_links` (Onboarding, Architecture Overview, API Reference, Roadmap).
- Enable and configure built-in Sphinx extensions in `docs/conf.py`:
  - `sphinx.ext.autodoc` (already active).
  - `sphinx.ext.viewcode` (already active).
  - `sphinx.ext.napoleon` (already active).
  - `sphinx.ext.intersphinx` with mappings for `python` (docs.python.org/3).
  - `sphinx.ext.todo` with `todo_include_todos = True`.
  - `sphinx.ext.duration` to benchmark build performance.
  - `sphinx.ext.githubpages` to create `.nojekyll` for GitHub Pages hosting.
- Configure external extensions:
  - `versionwarning.extension` configured with banner at `"top"` and clear warning text.
  - `sphinx_contributors` registered in `extensions`.
- Add a dedicated contributors page `docs/contributors.rst` and include it in `docs/index.rst`.
- Clean up `exclude_patterns` in `docs/conf.py` to prevent orphaned toctree warnings for internal agent/superpowers notes.
- Audit and enrich existing API docstrings across core modules, services, and models to ensure complete and readable Sphinx API reference pages.
- Ensure `uv run sphinx-build -b html docs docs/_build/html` builds cleanly with 0 errors.

### Non-Goals
- Replacing MyST Markdown parser (MyST parser stays enabled for markdown docs).
- Altering application runtime dependencies (docs dependencies belong strictly in `[dependency-groups] dev`).

### Anti-Goals
- Do NOT break existing Sphinx autodoc filters in `docs/conf.py` (specifically `_skip_foreign_instance_docstrings` for PyQt signals and SQLAlchemy MetaData).
- Do NOT let GitHub API rate limiting break local offline builds (provide an offline-friendly pattern or graceful fallback for `contributors`).
- Do NOT install or hardcode private tokens into configuration files.

---

## 4. Proposed Technical Architecture & Changes

### A. Dependency Configuration (`pyproject.toml`)
Add to `[dependency-groups] dev`:
```toml
[dependency-groups]
dev = [
    ...
    "shibuya>=2026.7.12",
    "sphinx-version-warning>=1.1.2",
    "sphinx-contributors>=0.3.0",
]
```

### B. Sphinx Configuration (`docs/conf.py`)
1. **Extensions list update**:
```python
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.duration",
    "sphinx.ext.githubpages",
    "myst_parser",
    "versionwarning.extension",
    "sphinx_contributors",
]
```

2. **Intersphinx Mapping**:
```python
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}
```

3. **Todo Configuration**:
```python
todo_include_todos = True
```

4. **Version Warning Configuration**:
```python
versionwarning_banner_position = "top"
versionwarning_body_text = (
    "You are viewing documentation for a previous or development version ({version}). "
    "Check the latest release for up-to-date guidance."
)
```

5. **Exclude Patterns**:
```python
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "superpowers/**",
    "agents/**",
    "archive/**",
    "adr/**",
]
```

6. **Shibuya Theme & Options**:
```python
html_theme = "shibuya"

html_theme_options = {
    "color_mode": "auto",
    "github_url": "https://github.com/HMAHD/CB-POS",
    "nav_links": [
        {"title": "Onboarding", "url": "onboarding"},
        {"title": "Architecture", "url": "PROJECT_OVERVIEW"},
        {"title": "Roadmap", "url": "Roadmap"},
        {"title": "API Reference", "url": "api/modules"},
    ],
}
```

### C. Documentation Content
1. **`docs/contributors.rst`**:
   New page containing project contributor acknowledgments:
   ```rst
   Contributors
   ============

   We thank all individuals who have contributed to the development and maintenance of CB-POS.

   .. contributors:: HMAHD/CB-POS
      :avatars:
      :contributions:
      :names:
      :order: ASC
   ```
2. **`docs/index.rst`**:
   Add `contributors` to the root `toctree`.

---

## 5. Verification & Acceptance Criteria
1. **Clean Sphinx Build**:
   `uv run sphinx-build -b html docs docs/_build/html` completes with exit code 0 and no fatal errors.
2. **Theme Rendering**:
   Verify generated HTML in `docs/_build/html/index.html`:
   - Shibuya theme structure, responsive navigation bar, and dark/light color scheme toggle.
   - GitHub link points to `https://github.com/HMAHD/CB-POS`.
3. **Contributors Page**:
   `docs/_build/html/contributors.html` renders properly with contributors list.
4. **Version Warning**:
   Banner script and container are injected into the build output for versioned documentation.
5. **No Regressions**:
   Existing API reference pages (`docs/_build/html/api/*.html`) continue to render cleanly with syntax-highlighted source code via `viewcode`.
