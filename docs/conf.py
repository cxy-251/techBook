# Sphinx configuration for techBook

project = 'techBook'
copyright = '2026, cxy251'
author = 'cxy251'
release = '1.0.0'

extensions = [
    'myst_parser',
    'sphinx.ext.mathjax',
    'sphinx.ext.viewcode',
    'sphinx.ext.todo',
]

source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

myst_enable_extensions = [
    'dollarmath',
    'colon_fence',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
language = 'zh_CN'

html_theme = 'furo'
html_static_path = ['_static']
html_title = 'techBook'

todo_include_todos = True
