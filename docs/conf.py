import os
import sys


sys.path.insert(0, os.path.abspath(".."))

project = "Email Assistant"
author = "Email Assistant contributors"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

html_theme = "alabaster"
exclude_patterns = ["_build"]
autodoc_member_order = "bysource"
