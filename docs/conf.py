import os
import sys

sys.path.insert(0, os.path.abspath(".."))

# SQLAlchemy declarative classes can't survive a second module exec in the
# same process (Table/mapper registry is a process-global singleton).
# Sphinx autodoc's importer re-imports modules across multiple automodule
# directives over the course of a full-package build; pre-importing here
# ensures the module is cached in sys.modules before any directive can
# trigger a re-exec (which otherwise fails with a confusing
# AttributeError/InvalidRequestError deep in SQLAlchemy's declarative base).
import cbpos.core.models  # noqa: F401

project = "CB POS"
copyright = "2025, Ceylon Byte"
author = "Akash Hasendra"
release = "1.3.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "myst_parser",
]

# Auto-generate GitHub-style heading anchors so PROJECT_OVERVIEW.md's own
# markdown table-of-contents links (#1-architecture etc.) resolve.
myst_heading_anchors = 3

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "alabaster"

# Several models (Sale, Purchase, Document, ...) each have their own `type`
# column; Sphinx's Python-domain autodoc tries to cross-reference the shared
# attribute name and can't disambiguate. Not a content problem -- suppress
# just this warning category rather than renaming a well-established column
# across 8 SQLAlchemy models to appease a docs tool.
suppress_warnings = ["ref.python"]


_FOREIGN_INSTANCE_ATTR_TYPES = {
    ("PyQt6.QtCore", "pyqtSignal"),
    ("sqlalchemy.sql.schema", "MetaData"),
}


def _skip_foreign_instance_docstrings(app, what, name, obj, options, lines):
    """Some class attributes (PyQt signals, SQLAlchemy's Base.metadata) are
    instances of external library classes and have no docstring of their own,
    so autodoc falls back to rendering the *library's* class docstring --
    e.g. PyQt6's pyqtSignal(*types, ...) constructor text (breaks RST on the
    unmatched `*`) or SQLAlchemy's MetaData docstring (references internal
    :ref: targets we have no intersphinx mapping for). Neither is useful
    documentation for these attributes anyway, so drop it.
    """
    if (type(obj).__module__, type(obj).__name__) in _FOREIGN_INSTANCE_ATTR_TYPES:
        del lines[:]


def setup(app):
    """Register the foreign-instance-docstring filter (Sphinx extension entry point)."""
    app.connect("autodoc-process-docstring", _skip_foreign_instance_docstrings)
