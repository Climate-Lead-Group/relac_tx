# Configuration file for the Sphinx documentation builder (RELAC TX).
# Source language is English; Spanish lives in locale/es/LC_MESSAGES/*.po.

project = "RELAC TX"
copyright = "2025-2026, Climate Lead Group"
author = "Climate Lead Group"
release = "1.0"

extensions = ["myst_parser"]
myst_enable_extensions = ["colon_fence", "deflist", "tasklist", "attrs_inline"]
myst_heading_anchors = 3
source_suffix = {".md": "markdown"}

# NOTE: no templates_path on purpose -- the repo .gitignore ignores any path
# containing "temp", so docs/_templates would silently never be committed.
exclude_patterns = [
    "_build", "dev", "superpowers", "locale", "requirements.txt",
    "Thumbs.db", ".DS_Store",
]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_theme_options = {"navigation_depth": 3, "collapse_navigation": False}

# Internationalisation (sphinx-intl / gettext)
language = "en"
locale_dirs = ["locale/"]
gettext_compact = False
gettext_uuid = False
