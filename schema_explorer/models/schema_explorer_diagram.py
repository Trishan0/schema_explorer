# -*- coding: utf-8 -*-
"""Saved diagrams (PLAN.md, section 13).

No stored copy of the schema itself lives here - the graph is always
computed live (or served from the service's in-process cache; PLAN.md,
section 15) from ``options``/``module_ids``. What *is* stored is exactly
the state a person spent time setting up: which modules, which view, the
manual node layout, and any presentation stories built on top of it.
"""
from __future__ import annotations

from odoo import fields, models, _


class SchemaExplorerDiagram(models.Model):
    _name = 'schema.explorer.diagram'
    _description = 'Schema Explorer: saved diagram'
    _order = 'write_date desc'

    name = fields.Char(required=True)
    module_ids = fields.Many2many(
        'ir.module.module', string='Modules', required=True,
        help='The module scope this diagram was built from (PLAN.md, section 7.1).',
    )
    options = fields.Json(
        string='Options', default=dict,
        help='Serialized schema_explorer.core.options.Options (depth, toggles, ...).',
    )
    view = fields.Selection(
        [('erd', 'ERD'), ('company', 'Company'), ('security', 'Security'),
         ('lifecycle', 'Lifecycle'), ('physical', 'Physical')],
        default='erd', required=True,
    )
    layout = fields.Json(
        string='Layout', default=dict,
        help='{"positions": {node_id: {x, y}}, "hidden": [node_id, ...], "camera": {...}}',
    )
    story_ids = fields.One2many('schema.explorer.story', 'diagram_id', string='Stories')
    user_id = fields.Many2one('res.users', string='Owner', default=lambda self: self.env.user, required=True)
    shared = fields.Boolean(string='Shared', help='Visible to every Schema Explorer user, not just the owner.')
    graph_snapshot = fields.Json(
        string='Graph snapshot',
        help='Optional frozen graph for "as of" comparisons (PLAN.md, section 20, future work). '
             'Left empty by normal save/load - nothing writes it yet.',
    )

    def action_open(self):
        """Open Schema Explorer pre-loaded with this diagram's scope,
        options, view and layout (PLAN.md, section 9.1: "A saved diagram
        record opens the explorer with stored options, layout and story.")."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'schema_explorer.action',
            'name': _('Schema Explorer: %s', self.name),
            'params': {'diagram_id': self.id},
        }
