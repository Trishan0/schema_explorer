# -*- coding: utf-8 -*-
"""Standalone HTML export (PLAN.md, sections 5.2 and 11.1).

Produces one self-contained ``.html`` file that opens with **no server and
no network**: the vendored Cytoscape/dagre libraries, the portable vanilla
renderer (``static/src/renderer/*.js``), a small vanilla sidebar/inspector/
story player, the graph JSON and any stories are all inlined into it.

The renderer files are written as ES modules (``import``/``export``) for
the in-app OWL client action, but a single downloadable file has nowhere to
serve a second file from - so rather than loading them as real ES modules,
this textually strips their ``import``/``export`` keywords and concatenates
them into one classic ``<script>`` tag, where plain top-level ``function``/
``const`` declarations end up sharing one scope. This is exactly what
PLAN.md, section 11.1 describes: "The standalone template inlines
renderer/* plus a minimal vanilla sidebar and inspector."

Uses Jinja2 rather than QWeb (PLAN.md, section 19, Q3's default: "portable,
already a dependency") - this module still takes ``module_path`` as an
argument rather than resolving it itself, so it stays import-safe from
anywhere ``jinja2`` is installed, with no Odoo environment required.
"""
from __future__ import annotations

import html
import json
import os
import re

import jinja2

from .json_export import to_json

_IMPORT_LINE_RE = re.compile(r'^[ \t]*import\s+.*?;[ \t]*$\n?', re.MULTILINE)
_EXPORT_BLOCK_RE = re.compile(r'^[ \t]*export\s*\{[^}]*\}\s*;[ \t]*$\n?', re.MULTILINE)
_EXPORT_PREFIX_RE = re.compile(r'^([ \t]*)export\s+(function|const|class|let|var)\b', re.MULTILINE)
_ODOO_MODULE_COMMENT_RE = re.compile(r'/\*\*\s*@odoo-module\s*\*\*/')

_TEMPLATE_NAME = 'standalone.html.j2'
# Concatenation order matters only in that a file must not *read* a name at
# module-execution time before it exists; every one of these only declares
# functions/consts, which plain top-level `function`s hoist regardless of
# order, so this order (dependency-ish, for readability) is not load-bearing.
_RENDERER_FILES = ('styles.js', 'legend.js', 'graph_to_elements.js', 'renderer.js')
_LIB_FILES = (
    ('cytoscape', '3.34.3', 'cytoscape.min.js'),
    ('cytoscape-dagre', '4.0.1', 'cytoscape-dagre.js'),
)


def _read(path: str) -> str:
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _inline_js_module(source: str) -> str:
    """Strip ES module ``import``/``export`` syntax so several files can be
    concatenated into one plain ``<script>`` and share a single top-level
    scope - see the module docstring."""
    source = _ODOO_MODULE_COMMENT_RE.sub('', source)
    source = _IMPORT_LINE_RE.sub('', source)
    source = _EXPORT_BLOCK_RE.sub('', source)
    source = _EXPORT_PREFIX_RE.sub(r'\1\2', source)
    return source


def _build_renderer_bundle(module_path: str) -> str:
    renderer_dir = os.path.join(module_path, 'static', 'src', 'renderer')
    parts = []
    for fname in _RENDERER_FILES:
        parts.append(f'// -- {fname} --')
        parts.append(_inline_js_module(_read(os.path.join(renderer_dir, fname))))
    return '\n'.join(parts)


def _build_vendor_bundle(module_path: str) -> str:
    parts = []
    for lib_name, version, fname in _LIB_FILES:
        path = os.path.join(module_path, 'static', 'lib', lib_name, version, fname)
        parts.append(f'// -- {lib_name} {version} --')
        parts.append(_read(path))
    return '\n'.join(parts)


_INLINE_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; font: 13px/1.4 -apple-system, "Segoe UI", Roboto, sans-serif; color: #1a202c; background: #fff; }
#se-app { display: flex; flex-direction: column; height: 100%; }
#se-topbar { display: flex; align-items: center; gap: 12px; padding: 8px 12px; background: #1a202c; color: #fff; flex: none; }
#se-topbar strong { font-size: 14px; }
#se-status { color: #a0aec0; font-size: 12px; flex: 1; }
#se-topbar button { background: #2d3748; color: #fff; border: 1px solid #4a5568; border-radius: 4px; padding: 4px 10px; cursor: pointer; }
#se-body { flex: 1; display: flex; min-height: 0; }
#se-sidebar { width: 220px; overflow: auto; border-right: 1px solid #e2e8f0; padding: 8px; flex: none; }
#se-sidebar .se-group-title { font-weight: 600; text-transform: uppercase; font-size: 10px; color: #718096; margin: 10px 0 4px; }
#se-sidebar .se-item { padding: 3px 6px; cursor: pointer; border-radius: 3px; }
#se-sidebar .se-item:hover { background: #edf2f7; }
#se-canvas-wrap { flex: 1; position: relative; min-width: 0; }
#se-canvas { position: absolute; inset: 0; }
#se-inspector { width: 300px; overflow: auto; border-left: 1px solid #e2e8f0; padding: 10px; flex: none; }
#se-inspector table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 6px; }
#se-inspector th, #se-inspector td { text-align: left; border-bottom: 1px solid #edf2f7; padding: 2px 4px; }
#se-legend { position: absolute; right: 12px; bottom: 12px; background: #fff; border: 1px solid #cbd5e0; border-radius: 6px; padding: 10px; max-width: 320px; box-shadow: 0 2px 8px rgba(0,0,0,.15); font-size: 11px; }
.se-legend-item { margin-bottom: 4px; }
#se-story-panel { border-top: 1px solid #e2e8f0; padding: 10px 16px; background: #f7fafc; flex: none; }
#se-story-title { font-weight: 600; }
#se-story-narration { margin: 4px 0; white-space: pre-line; }
.se-story-controls button { padding: 4px 12px; margin-right: 8px; cursor: pointer; }
@media (prefers-color-scheme: dark) {
  html, body { background: #171923; color: #e2e8f0; }
  #se-sidebar, #se-inspector { border-color: #2d3748; }
  #se-sidebar .se-item:hover { background: #2d3748; }
  #se-inspector th, #se-inspector td { border-color: #2d3748; }
  #se-legend { background: #1a202c; border-color: #4a5568; color: #e2e8f0; }
  #se-story-panel { background: #1a202c; border-color: #2d3748; }
}
""".strip()


_APP_JS_TEMPLATE = r"""
document.addEventListener('DOMContentLoaded', function () {
    var graph = SE_GRAPH;
    var stories = SE_STORIES || [];
    var container = document.getElementById('se-canvas');
    var renderer = createRenderer(container, {
        onSelectNode: function (id) { showInspector(id); },
        onDeselect: function () { showInspector(null); },
    });
    renderer.mount(graph, {});
    renderer.fit();
    buildSidebar(graph, renderer);
    buildLegend();

    document.getElementById('se-legend-toggle').addEventListener('click', function () {
        var el = document.getElementById('se-legend');
        el.hidden = !el.hidden;
    });

    function buildSidebar(g, r) {
        var el = document.getElementById('se-sidebar');
        var groups = {};
        g.nodes.forEach(function (n) { (groups[n.kind] = groups[n.kind] || []).push(n); });
        Object.keys(groups).sort().forEach(function (kind) {
            var title = document.createElement('div');
            title.className = 'se-group-title';
            title.textContent = kind + ' (' + groups[kind].length + ')';
            el.appendChild(title);
            groups[kind].sort(function (a, b) { return a.id.localeCompare(b.id); }).forEach(function (n) {
                var item = document.createElement('div');
                item.className = 'se-item';
                item.textContent = n.label;
                item.addEventListener('click', function () { r.focus(n.id); });
                el.appendChild(item);
            });
        });
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function showInspector(nodeId) {
        var el = document.getElementById('se-inspector');
        if (!nodeId) {
            el.textContent = 'Select a node to inspect it.';
            return;
        }
        var node = graph.nodes.find(function (n) { return n.id === nodeId; });
        if (!node) { return; }
        var out = '<h3>' + escapeHtml(node.label) + '</h3>';
        out += '<div>' + escapeHtml(node.id) + '</div>';
        out += '<div><em>' + escapeHtml(node.kind) + (node.module ? ' · ' + escapeHtml(node.module) : '') + '</em></div>';
        out += '<table><thead><tr><th>Field</th><th>Type</th><th>Origin</th></tr></thead><tbody>';
        node.fields.forEach(function (f) {
            out += '<tr><td>' + escapeHtml(f.name) + '</td><td>' + escapeHtml(f.type) + '</td><td>' + escapeHtml(f.origin) + '</td></tr>';
        });
        out += '</tbody></table>';
        el.innerHTML = out;
    }

    function buildLegend() {
        var el = document.getElementById('se-legend');
        var out = '<strong>Table styles</strong>';
        LEGEND_NODE_KINDS.forEach(function (item) {
            out += '<div class="se-legend-item"><strong>' + escapeHtml(item.title) + '</strong> — ' + escapeHtml(item.description) + '</div>';
        });
        out += '<strong>Line styles</strong>';
        LEGEND_EDGE_KINDS.forEach(function (item) {
            out += '<div class="se-legend-item"><strong>' + escapeHtml(item.title) + '</strong> — ' + escapeHtml(item.description) + '</div>';
        });
        el.innerHTML = out;
    }

    if (stories.length) {
        initStoryPlayer(stories[0], renderer, graph);
    }

    function initStoryPlayer(story, r, g) {
        var steps = story.steps || [];
        if (!steps.length) { return; }
        var index = 0;
        document.getElementById('se-story-panel').style.display = '';

        function applyStep(i) {
            var step = steps[i];
            r.applyViewMode(step.view || 'erd', g);
            r.setHighlight(step.focus_nodes || [], step.highlight_edges || []);
            var focusIds = step.focus_nodes || [];
            if (step.camera && step.camera.pan && typeof step.camera.zoom === 'number') {
                r.setViewport(step.camera, { animate: true });
            } else if (focusIds.length) {
                var eles = r.cy.collection();
                focusIds.forEach(function (id) { eles = eles.union(r.cy.getElementById(id)); });
                if (eles.length) { r.cy.animate({ fit: { eles: eles, padding: 60 } }, { duration: 400 }); }
            }
            document.getElementById('se-story-title').textContent = step.title || '';
            document.getElementById('se-story-narration').textContent = step.narration || '';
            document.getElementById('se-story-progress').textContent = (i + 1) + ' / ' + steps.length;
        }

        document.getElementById('se-story-prev').addEventListener('click', function () {
            index = Math.max(0, index - 1);
            applyStep(index);
        });
        document.getElementById('se-story-next').addEventListener('click', function () {
            index = Math.min(steps.length - 1, index + 1);
            applyStep(index);
        });
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'ArrowRight') { document.getElementById('se-story-next').click(); }
            if (ev.key === 'ArrowLeft') { document.getElementById('se-story-prev').click(); }
        });
        applyStep(0);
    }
});
""".strip()


def render_standalone_html(graph: dict, *, module_path: str, title: str | None = None,
                            stories: list[dict] | None = None) -> str:
    """Render one self-contained ``.html`` file for ``graph``.

    ``module_path`` is the filesystem root of the installed
    ``schema_explorer`` addon (e.g.
    ``odoo.modules.module.get_module_path('schema_explorer')``, resolved by
    the caller so this function itself never needs an Odoo environment).

    ``stories``, if given, is a list of ``{"name": ..., "steps": [...]}``
    dicts - the same shape :mod:`schema_explorer.models.schema_explorer_story`
    serializes to (PLAN.md, section 13: "included in HTML export, so an
    offline demo keeps its script").
    """
    modules = ', '.join(m['name'] for m in graph.get('modules', []))
    page_title = html.escape(title or (f'Schema Explorer: {modules}' if modules else 'Schema Explorer'))

    stats = graph.get('stats', {})
    status_text = f"{stats.get('nodes', 0)} models shown"
    if stats.get('db_tables_total'):
        status_text += f" of {stats['db_tables_total']} tables in the database"
    status_text += f" · {stats.get('edges', 0)} relations · schema v{graph.get('schema_version')}"
    status_text = html.escape(status_text)

    template_path = os.path.join(os.path.dirname(__file__), '..', '..', 'templates', _TEMPLATE_NAME)
    template = jinja2.Environment(autoescape=False).from_string(_read(os.path.normpath(template_path)))

    app_js = 'var SE_GRAPH = ' + to_json(graph, indent=None) + ';\n'
    app_js += 'var SE_STORIES = ' + json.dumps(stories or [], ensure_ascii=False) + ';\n'
    app_js += _build_renderer_bundle(module_path) + '\n'
    app_js += _APP_JS_TEMPLATE

    return template.render(
        title=page_title,
        status_text=status_text,
        inline_css=_INLINE_CSS,
        vendor_js=_build_vendor_bundle(module_path),
        app_js=app_js,
    )
