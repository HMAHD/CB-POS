# Modernize Sphinx Documentation with Shibuya Theme and Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize CB-POS technical documentation by transitioning from Alabaster to the Shibuya theme, integrating essential Sphinx extensions (intersphinx, version-warning, contributors), enriching API docstrings, and achieving a clean zero-error Sphinx build.

**Architecture:** Update `pyproject.toml` with doc dependencies (`shibuya`, `sphinx-version-warning`, `sphinx-contributors`). Configure Shibuya theme options, intersphinx mappings, and extension settings in `docs/conf.py`. Add a dedicated contributors page, audit and enrich docstrings across core services and models, and verify HTML output across light and dark modes.

**Tech Stack:** Python 3.12, Sphinx, Shibuya Theme, MyST-Parser, sphinx-version-warning, sphinx-contributors, intersphinx, napoleon, autodoc, uv.

**Spec:** `docs/superpowers/specs/2026-10-18-modernize-sphinx-docs-shibuya-design.md`

## Global Constraints
- Target Python version >= 3.12.
- Documentation dependencies must be added strictly to `[dependency-groups] dev` in `pyproject.toml`.
- All core test suites must remain green; no regressions to codebase models or runtime behavior.
- Existing custom autodoc filters (`_skip_foreign_instance_docstrings` in `docs/conf.py`) must be preserved.
- Offline builds and environments without `GITHUB_TOKEN` must complete cleanly without breaking.

## Review Focus
1. `contributors` directive without network / rate limited: ensure build completes gracefully even if GitHub API is unreachable.
2. Intersphinx mapping network failure: ensure offline builds do not crash the build runner.
3. Light and dark mode rendering: verify theme toggle operates smoothly without CSS clash or unreadable text.
4. Internal agent/superpowers documentation: verify `exclude_patterns` suppresses all orphan toctree warnings.
5. API docstrings: verify Sphinx Napoleon parses updated docstrings without formatting warnings.

---

### Task 1: Add Documentation Dependencies to `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: Installed packages `shibuya>=2026.7.12`, `sphinx-version-warning>=1.1.2`, `sphinx-contributors>=0.3.0` in the uv environment.

- [ ] **Step 1: Update `pyproject.toml`**
Add `shibuya>=2026.7.12`, `sphinx-version-warning>=1.1.2`, and `sphinx-contributors>=0.3.0` to `[dependency-groups] dev`.

- [ ] **Step 2: Sync dependencies using uv**
Run: `uv sync`
Expected: Resolves and installs packages successfully.

- [ ] **Step 3: Verify packages import cleanly in the environment**
Run: `uv run python -c "import shibuya, versionwarning, sphinx_contributors; print('imports ok')"`
Expected: Prints `imports ok` with exit code 0.

- [ ] **Step 4: Commit**
```bash
git add pyproject.toml uv.lock
git commit -m "build(deps): add shibuya, sphinx-version-warning, and sphinx-contributors to dev group"
```

---

### Task 2: Configure Shibuya Theme and Extensions in `docs/conf.py`

**Files:**
- Modify: `docs/conf.py`

**Interfaces:**
- Consumes: `shibuya`, `versionwarning.extension`, `sphinx_contributors`, built-in Sphinx extensions.
- Produces: Updated Sphinx configuration with Shibuya theme, light/dark mode, intersphinx, todo, duration, githubpages, version warning, and exclusion patterns.

- [ ] **Step 1: Update extensions, theme, and options in `docs/conf.py`**
In `docs/conf.py`:
- Add `"sphinx.ext.intersphinx"`, `"sphinx.ext.todo"`, `"sphinx.ext.duration"`, `"sphinx.ext.githubpages"`, `"versionwarning.extension"`, `"sphinx_contributors"` to `extensions`.
- Set `html_theme = "shibuya"`.
- Configure `html_theme_options`:
  ```python
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
- Configure `intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}`.
- Set `todo_include_todos = True`.
- Configure version warning:
  ```python
  versionwarning_banner_position = "top"
  versionwarning_body_text = (
      "You are viewing documentation for a previous or development version ({version}). "
      "Check the latest release for up-to-date guidance."
  )
  ```
- Add `"superpowers/**"`, `"agents/**"`, `"archive/**"`, `"adr/**"` to `exclude_patterns`.

- [ ] **Step 2: Run sphinx-build to verify theme and extension loading**
Run: `uv run sphinx-build -b html docs docs/_build/html`
Expected: Exits with code 0; `docs/_build/html` generated using Shibuya theme assets.

- [ ] **Step 3: Commit**
```bash
git add docs/conf.py
git commit -m "docs: configure shibuya theme, intersphinx, version warning, and extensions in conf.py"
```

---

### Task 3: Add Contributors Page and Integrate into Navigation

**Files:**
- Create: `docs/contributors.rst`
- Modify: `docs/index.rst`

**Interfaces:**
- Consumes: `sphinx_contributors` directive `.. contributors::`.
- Produces: Dedicated contributors documentation page linked in root toctree.

- [ ] **Step 1: Create `docs/contributors.rst`**
Create `docs/contributors.rst` with:
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

- [ ] **Step 2: Add `contributors` to `docs/index.rst`**
Add `contributors` to the `.. toctree::` directive in `docs/index.rst`.

- [ ] **Step 3: Verify documentation build includes contributors page**
Run: `uv run sphinx-build -b html docs docs/_build/html`
Expected: `docs/_build/html/contributors.html` is generated and linked from index page.

- [ ] **Step 4: Commit**
```bash
git add docs/contributors.rst docs/index.rst
git commit -m "docs: add contributors page and link to root toctree"
```

---

### Task 4: Audit & Enrich API Docstrings across Core Services & Models

**Files:**
- Modify: `cbpos/core/services/pricing_service.py`
- Modify: `cbpos/core/services/promotion_service.py`
- Modify: `cbpos/core/services/price_list_service.py`
- Modify: `cbpos/core/models/__init__.py`

**Interfaces:**
- Produces: Standardized Google/NumPy-style docstrings on core methods and models for autodoc rendering.

- [ ] **Step 1: Audit docstrings in `cbpos/core/services/pricing_service.py`**
Ensure `PricingService`, `calculate_price()`, and helper functions have comprehensive docstrings explaining arguments, return values, and behavior (including daily window and price-list stacking rules).

- [ ] **Step 2: Audit docstrings in `cbpos/core/services/promotion_service.py` and `price_list_service.py`**
Verify all public methods (`validate_promotion`, `create_promotion`, `find_overlapping`, `create_price_list`, `set_item_price`) have clear docstrings with type notes and behavior descriptions.

- [ ] **Step 3: Audit docstrings in `cbpos/core/models/__init__.py`**
Add/enrich module-level and class-level docstrings for primary models (`Promotion`, `PriceList`, `Product`, `Sale`, `AuditLog`).

- [ ] **Step 4: Run Sphinx build to verify clean API docs rendering**
Run: `uv run sphinx-build -b html docs docs/_build/html`
Expected: Clean build with 0 autodoc warnings for core services and models.

- [ ] **Step 5: Run tests to ensure no code regressions**
Run: `uv run pytest tests/unit/test_pricing* tests/unit/test_promotion* tests/unit/test_price*`
Expected: All tests pass.

- [ ] **Step 6: Commit**
```bash
git add cbpos/core/services/pricing_service.py cbpos/core/services/promotion_service.py cbpos/core/services/price_list_service.py cbpos/core/models/__init__.py
git commit -m "docs(api): enrich docstrings across core services and models for autodoc"
```

---

### Task 5: Complete Verification & Visual Build Inspection

**Files:**
- Verify: `docs/_build/html/index.html`
- Verify: `docs/_build/html/api/`
- Verify: `docs/_build/html/contributors.html`

**Interfaces:**
- Verifies: Full HTML output conforms to acceptance criteria.

- [ ] **Step 1: Perform full clean build**
Run: `rm -rf docs/_build && uv run sphinx-build -b html docs docs/_build/html`
Expected: Clean build, exit code 0.

- [ ] **Step 2: Verify HTML page generation and contents**
Inspect:
- `docs/_build/html/index.html`: Contains Shibuya theme classes, color mode toggle script, GitHub repo link, and navbar items.
- `docs/_build/html/contributors.html`: Contains contributors section.
- `docs/_build/html/api/cbpos.core.services.pricing_service.html`: Autodoc renders updated docstrings cleanly with source code links via viewcode.

- [ ] **Step 3: Run ruff lint and format check**
Run: `uv run ruff check cbpos/ docs/conf.py && uv run ruff format --check cbpos/ docs/conf.py`
Expected: All checks pass.

- [ ] **Step 4: Commit and finalize**
```bash
git status
```
