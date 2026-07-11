from __future__ import annotations

project = "techBook"
author = "cxy-251"
language = "zh_CN"

extensions = [
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

root_doc = "index"
exclude_patterns = ["_build"]
nitpicky = True
show_authors = False
html_theme = "alabaster"
html_title = "techBook"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}
