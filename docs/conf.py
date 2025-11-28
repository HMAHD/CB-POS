import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "CB POS"
copyright = "2025, Ceylon Byte"
author = "Akash Hasendra"
release = "1.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "alabaster"
html_static_path = ["_static"]
