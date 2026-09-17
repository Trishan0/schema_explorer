# -*- coding: utf-8 -*-
"""File-download exports (PLAN.md, section 12: ``controllers/main.py``,
"/schema_explorer/export/<fmt> (file download), auth='user'"``).

This is the one place in the module that touches ``odoo.http`` - the
portable core (``core/``) and the RPC service (``models/
schema_explorer_service.py``) stay free of it, per decision D1. All this
controller does is: parse the posted options, delegate the access check
and graph build to ``schema.explorer.service.get_graph`` (so a user
without the group, or without the physical group, gets exactly the same
behaviour here as in the in-app canvas), then hand the graph to the
matching exporter and stream the result back as a file.
"""
from __future__ import annotations

import json

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.modules.module import get_module_path

from ..core.exporters.dbml import to_dbml
from ..core.exporters.html_standalone import render_standalone_html
from ..core.exporters.json_export import to_json
from ..core.exporters.markdown import to_markdown
from ..core.exporters.mermaid import to_mermaid

_EXPORTERS = {
    'json': ('application/json', 'schema_explorer.json', lambda graph, **kw: to_json(graph)),
    'mermaid': ('text/plain', 'schema_explorer.mmd', lambda graph, **kw: to_mermaid(graph)),
    'dbml': ('text/plain', 'schema_explorer.dbml', lambda graph, **kw: to_dbml(graph)),
    'markdown': ('text/markdown', 'schema_explorer.md', lambda graph, **kw: to_markdown(graph)),
    'html': ('text/html', 'schema_explorer.html', lambda graph, **kw: render_standalone_html(graph, **kw)),
}


class SchemaExplorerController(http.Controller):

    @http.route('/schema_explorer/export/<string:fmt>', type='http', auth='user',
                methods=['POST'], csrf=True)
    def export(self, fmt, options='{}', stories='[]', **kwargs):
        if fmt not in _EXPORTERS:
            return request.not_found()

        try:
            payload = json.loads(options or '{}')
        except ValueError:
            return request.make_response('Invalid options payload.', status=400)

        # A standalone file is meant to be handed to someone outside the
        # database - anonymize by default here even if the in-app canvas
        # this export was triggered from currently isn't (PLAN.md, section
        # 11.1: "anonymize... on by default for HTML").
        if fmt == 'html' and 'anonymize' not in payload:
            payload = dict(payload, anonymize=True)

        try:
            # Reuses the service's own group check and physical-group
            # downgrade (PLAN.md, section 14) - this controller never
            # calls the core pipeline directly, so an export can't see
            # anything the in-app canvas couldn't.
            graph = request.env['schema.explorer.service'].get_graph(payload)
        except AccessError as exc:
            return request.make_response(str(exc), status=403)
        except UserError as exc:
            return request.make_response(str(exc), status=400)

        content_type, filename, build = _EXPORTERS[fmt]
        extra = {}
        if fmt == 'html':
            try:
                stories_payload = json.loads(stories or '[]')
            except ValueError:
                stories_payload = []
            extra['module_path'] = get_module_path('schema_explorer')
            extra['stories'] = stories_payload

        content = build(graph, **extra)
        headers = [
            ('Content-Type', f'{content_type}; charset=utf-8'),
            ('Content-Disposition', f'attachment; filename="{filename}"'),
        ]
        return request.make_response(content, headers=headers)
