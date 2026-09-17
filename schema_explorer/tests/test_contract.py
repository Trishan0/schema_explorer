# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.contract import (
    SCHEMA_VERSION,
    new_graph_skeleton,
    validate_graph,
)


@tagged('schema_explorer', 'post_install', '-at_install')
class TestContract(TransactionCase):
    """Pure shape checks - no Odoo environment is actually needed here, but
    every test in this suite runs as a TransactionCase for consistency."""

    def test_skeleton_is_valid(self):
        graph = new_graph_skeleton()
        graph['generated_at'] = '2026-09-17T00:00:00+00:00'
        graph['odoo'] = {'version': '19.0', 'database': 'test'}
        self.assertEqual(validate_graph(graph), [])

    def test_missing_top_level_key_is_reported(self):
        graph = new_graph_skeleton()
        del graph['nodes']
        problems = validate_graph(graph)
        self.assertTrue(any('nodes' in p for p in problems))

    def test_wrong_schema_version_is_reported(self):
        graph = new_graph_skeleton()
        graph['schema_version'] = SCHEMA_VERSION + 1
        problems = validate_graph(graph)
        self.assertTrue(any('schema_version' in p for p in problems))

    def test_invalid_node_kind_is_reported(self):
        graph = new_graph_skeleton()
        graph['nodes'] = [{
            'id': 'res.partner', 'kind': 'not-a-real-kind', 'table': 'res_partner',
            'label': 'Contact', 'module': 'base', 'mixins': [], 'inherits': {}, 'fields': [],
        }]
        problems = validate_graph(graph)
        self.assertTrue(any('invalid kind' in p for p in problems))

    def test_duplicate_node_id_is_reported(self):
        graph = new_graph_skeleton()
        node = {
            'id': 'res.partner', 'kind': 'boundary', 'table': 'res_partner',
            'label': 'Contact', 'module': 'base', 'mixins': [], 'inherits': {}, 'fields': [],
        }
        graph['nodes'] = [node, dict(node)]
        problems = validate_graph(graph)
        self.assertTrue(any('duplicate node id' in p for p in problems))

    def test_edge_to_unknown_node_is_reported(self):
        graph = new_graph_skeleton()
        graph['nodes'] = [{
            'id': 'res.partner', 'kind': 'boundary', 'table': 'res_partner',
            'label': 'Contact', 'module': 'base', 'mixins': [], 'inherits': {}, 'fields': [],
        }]
        graph['edges'] = [{
            'id': 'e1', 'kind': 'many2one', 'from': 'res.partner', 'to': 'does.not.exist',
        }]
        problems = validate_graph(graph)
        self.assertTrue(any('unknown node' in p for p in problems))

    def test_invalid_field_origin_is_reported(self):
        graph = new_graph_skeleton()
        graph['nodes'] = [{
            'id': 'res.partner', 'kind': 'boundary', 'table': 'res_partner',
            'label': 'Contact', 'module': 'base', 'mixins': [], 'inherits': {},
            'fields': [{
                'name': 'name', 'type': 'char', 'label': 'Name',
                'store': True, 'required': False, 'index': False, 'origin': 'nonsense',
            }],
        }]
        problems = validate_graph(graph)
        self.assertTrue(any('invalid origin' in p for p in problems))
