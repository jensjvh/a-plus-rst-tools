"""
Editor directive: embeds a Pyodide-based Python editor into a Sphinx page.

Usage::

    .. python-editor:: Exercise 1

        print("hello world")

The directive renders a CodeMirror editor pre-filled with the directive
content, a Run button and an output area. The Python code is executed in
the browser using Pyodide (WebAssembly build of CPython). Pyodide is
loaded lazily from a CDN the first time the user clicks Run, so pages
without any interaction do not pay the loading cost.

The markup, styles and client side logic of the editor live in the
``static`` folder next to this module:

    static/html/pyodide_editor.html  - markup template for the editor
    static/css/pyodide_editor.css    - styles for the editor
    static/js/pyodide_editor.js      - client side logic (Pyodide + CodeMirror)
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from html import escape

from docutils import nodes
from docutils.parsers.rst import directives

from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective
from sphinx.util.fileutil import copy_asset
from sphinx.util import logging

PYODIDE_VERSION = 'v314.0.7'
PYODIDE_CDN = f'https://cdn.jsdelivr.net/pyodide/{PYODIDE_VERSION}/full/'
CODEMIRROR_VERSION = '6.0.2'
CODEMIRROR_CDN = f'https://cdn.jsdelivr.net/npm/codemirror@{CODEMIRROR_VERSION}'

# Assets shipped with the extension. The css and js files are copied into the
# _static folder of the built documentation and the html file is used as a
# template when the directive is rendered.
ASSETS_PATH = 'static'
CSS_FILE = 'css/pyodide_editor.css'
JS_FILE = 'js/pyodide_editor.js'
HTML_TEMPLATE_FILE = 'html/pyodide_editor.html'

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _html_template() -> str:
    """Read the HTML template of the editor from the static folder."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        ASSETS_PATH, HTML_TEMPLATE_FILE)
    with open(path, encoding='utf-8') as template_file:
        return template_file.read()


class PyodideEditorNode(nodes.General, nodes.Element):
    """A node which renders a Pyodide Python editor as HTML."""

    def __init__(self, rawsource='', uid='', title='', code='', **attributes):
        super().__init__(rawsource, **attributes)
        self['uid'] = uid
        self['title'] = title
        self['code'] = code

    def html(self):
        title = escape(self['title'])
        code = self['code']
        code_escaped = escape(code, quote=True)
        height_style = ''
        if self.get('height'):
            height_style = f' style="min-height: {escape(str(self["height"]), quote=True)}"'
        return _html_template().format(
            uid=self['uid'],
            title=title,
            initial=code_escaped,
            code=escape(code),
            height=height_style,
        )


def visit_pyodide_editor_html(self, node):
    self.body.append(node.html())
    raise nodes.SkipNode


def visit_pyodide_editor_text(self, node):
    # Render the code as a plain code block in non-HTML output
    self.body.append('\n\n.. code-block:: python\n\n')
    self.body.append('\n'.join('    ' + line for line in node['code'].splitlines()))
    self.body.append('\n\n')
    raise nodes.SkipNode


class EditorDirective(SphinxDirective):
    """A directive for embedding a Pyodide Python editor in course material"""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = True
    option_spec = {
        'height': directives.unchanged,
    }

    def run(self) -> list[nodes.Node]:
        title = self.arguments[0] if self.arguments else 'Python editor'
        code = '\n'.join(self.content)
        uid = 'pyodide-editor-{}'.format(
            self.env.new_serialno('pyodide_editor'))
        node = PyodideEditorNode(uid=uid, title=title, code=code)
        if 'height' in self.options:
            node['height'] = self.options['height']
        return [node]


def add_assets(app: Sphinx, exception=None):
    pyodide_version = app.config.pyodide_version or PYODIDE_VERSION
    cdn = f'https://cdn.jsdelivr.net/pyodide/{pyodide_version}/full/'
    # Configuration for the static editor script (which cannot know the
    # configured Pyodide version at build time).
    config = {'pyodideUrl': cdn + 'pyodide.js', 'indexUrl': cdn}
    opts = {'data-aplus': 'yes'}
    # CodeMirror editor library
    app.add_js_file(f'{CODEMIRROR_CDN}/lib/codemirror.min.js', **opts)
    app.add_css_file(f'{CODEMIRROR_CDN}/lib/codemirror.css', **opts)
    app.add_css_file(f'{CODEMIRROR_CDN}/theme/eclipse.css', **opts)
    app.add_js_file(f'{CODEMIRROR_CDN}/mode/python/python.js', **opts)
    # Pyodide runtime configuration (Pyodide itself is loaded lazily)
    app.add_js_file(None, body='window.pyodideEditorConfig = {};'.format(
        json.dumps(config)), **opts)
    # Editor styles and client side logic
    app.add_css_file(CSS_FILE, **opts)
    app.add_js_file(JS_FILE, **opts)


def copy_asset_files(app: Sphinx, exception=None):
    """Copy the css and js files of the directive into the _static folder."""
    if exception:
        return
    logger.info('Copying assets from the python-editor directive to the '
                '_static folder... ')
    for asset in (CSS_FILE, JS_FILE):
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  ASSETS_PATH, asset)
        copy_asset(local_path, os.path.join(app.outdir, '_static',
                                            os.path.dirname(asset)))
    logger.info('done')


def setup(app: Sphinx):
    app.add_config_value('pyodide_version', PYODIDE_VERSION, 'html')
    app.connect('builder-inited', add_assets)
    app.connect('build-finished', copy_asset_files)
    app.add_node(
        PyodideEditorNode,
        html=(visit_pyodide_editor_html, None),
        latex=(visit_pyodide_editor_text, None),
        text=(visit_pyodide_editor_text, None),
        man=(visit_pyodide_editor_text, None),
        texinfo=(visit_pyodide_editor_text, None),
        override=True,
    )
    app.add_directive('python-editor', EditorDirective)

    return {
        'version': '0.1',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
