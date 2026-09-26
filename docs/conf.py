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

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "alabaster"
