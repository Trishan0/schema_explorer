# -*- coding: utf-8 -*-
"""Presentation stories (PLAN.md, sections 9.7 and 13).

A story is an ordered walkthrough over a saved diagram: each step records
enough of the canvas state (view, which nodes/edges to highlight, camera)
to replay it later, either in-app (presentation mode) or from the
standalone HTML export - see
:mod:`schema_explorer.core.exporters.html_standalone`, which consumes
:meth:`SchemaExplorerStory.to_export_dict`.
"""
from __future__ import annotations

from odoo import fields, models


class SchemaExplorerStory(models.Model):
    _name = 'schema.explorer.story'
    _description = 'Schema Explorer: presentation story'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    diagram_id = fields.Many2one('schema.explorer.diagram', required=True, ondelete='cascade')
    step_ids = fields.One2many('schema.explorer.story.step', 'story_id', string='Steps')

    def to_export_dict(self) -> dict:
        """The shape :func:`html_standalone.render_standalone_html` expects
        (PLAN.md, section 13: "included in HTML export")."""
        self.ensure_one()
        return {
            'name': self.name,
            'steps': [step.to_export_dict() for step in self.step_ids],
        }


class SchemaExplorerStoryStep(models.Model):
    _name = 'schema.explorer.story.step'
    _description = 'Schema Explorer: presentation story step'
    _order = 'sequence, id'

    story_id = fields.Many2one('schema.explorer.story', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    title = fields.Char(required=True)
    narration = fields.Text(help='1-3 lines of narration read aloud while this step is showing.')
    view = fields.Selection(
        [('erd', 'ERD'), ('company', 'Company'), ('security', 'Security'),
         ('lifecycle', 'Lifecycle'), ('physical', 'Physical')],
        default='erd', required=True,
    )
    focus_nodes = fields.Json(default=list, help='Node ids to highlight; everything else dims.')
    highlight_edges = fields.Json(default=list, help='Edge ids to highlight alongside focus_nodes.')
    camera = fields.Json(default=dict, help='{"zoom": float, "pan": {"x": float, "y": float}}')
    inspector_section = fields.Char(help='Inspector section to auto-open for this step, if any.')

    def to_export_dict(self) -> dict:
        self.ensure_one()
        return {
            'title': self.title,
            'narration': self.narration or '',
            'view': self.view,
            'focus_nodes': self.focus_nodes or [],
            'highlight_edges': self.highlight_edges or [],
            'camera': self.camera or {},
            'inspector_section': self.inspector_section or None,
        }
