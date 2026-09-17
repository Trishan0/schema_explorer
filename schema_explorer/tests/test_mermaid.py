# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.exporters.mermaid import to_mermaid


def _node(model, table, fields):
    return {
        'id': model, 'kind': 'owned', 'table': table, 'label': table,
        'module': 'demo', 'mixins': [], 'inherits': {}, 'fields': fields,
    }


def _field(name, ftype, **overrides):
    base = {'name': name, 'type': ftype, 'label': name, 'target': None,
            'store': True, 'required': False, 'index': False, 'origin': 'own'}
    base.update(overrides)
    return base


@tagged('schema_explorer', 'post_install', '-at_install')
class TestMermaid(TransactionCase):
    """Pure-data test: builds a small hand-crafted graph dict rather than a
    real one, so it exercises only the exporter (PLAN.md, section 11)."""

    def _sample_graph(self):
        parent = _node('demo.parent', 'demo_parent', [
            _field('id', 'integer'),
            _field('name', 'char'),
        ])
        child = _node('demo.child', 'demo_child', [
            _field('id', 'integer'),
            _field('parent_id', 'many2one', target='demo.parent'),
            _field('inherited_field', 'char', origin='inherits'),
        ])
        edges = [
            {'id': 'e1', 'kind': 'many2one', 'from': 'demo.child', 'to': 'demo.parent',
             'field': 'parent_id', 'required': True},
        ]
        return {
            'nodes': [parent, child],
            'edges': edges,
        }

    def test_entities_are_rendered_with_sanitized_ids(self):
        mmd = to_mermaid(self._sample_graph())
        self.assertIn('erDiagram', mmd)
        self.assertIn('demo_parent {', mmd)
        self.assertIn('demo_child {', mmd)
        self.assertIn('string _model "demo.parent"', mmd)

    def test_many2one_attribute_row_has_no_duplicate_fk_marker(self):
        mmd = to_mermaid(self._sample_graph())
        self.assertIn('FK parent_id', mmd)
        self.assertNotIn('FK parent_id FK', mmd)

    def test_inherited_field_excluded_from_attribute_block(self):
        mmd = to_mermaid(self._sample_graph())
        self.assertNotIn('inherited_field', mmd)

    def test_many2one_relationship_line_uses_exactly_one_when_required(self):
        mmd = to_mermaid(self._sample_graph())
        self.assertIn('demo_parent ||--o{ demo_child : "parent_id"', mmd)

    def test_many2one_relationship_line_uses_zero_or_one_when_optional(self):
        graph = self._sample_graph()
        graph['edges'][0]['required'] = False
        mmd = to_mermaid(graph)
        self.assertIn('demo_parent o|--o{ demo_child : "parent_id"', mmd)

    def test_one2many_skipped_when_mirrored_by_many2one(self):
        graph = self._sample_graph()
        graph['edges'].append({
            'id': 'e2', 'kind': 'one2many', 'from': 'demo.parent', 'to': 'demo.child',
            'field': 'child_ids', 'inverse': 'parent_id', 'physical': False,
        })
        mmd = to_mermaid(graph)
        self.assertNotIn('child_ids', mmd)

    def test_inherits_edge_renders_as_one_to_one(self):
        graph = self._sample_graph()
        graph['edges'] = [{
            'id': 'e1', 'kind': 'inherits', 'from': 'demo.child', 'to': 'demo.parent',
            'field': 'parent_id',
        }]
        mmd = to_mermaid(graph)
        self.assertIn('demo_parent ||--|| demo_child : "_inherits (parent_id)"', mmd)
