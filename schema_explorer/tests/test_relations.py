# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.analyzers.relations import build_edges
from odoo.addons.schema_explorer.core.options import Options


def _find(edges, **attrs):
    for e in edges:
        if all(e.get(k) == v for k, v in attrs.items()):
            return e
    return None


@tagged('schema_explorer', 'post_install', '-at_install')
class TestBuildEdges(TransactionCase):
    """PLAN.md, section 8.1, against res.partner.category (self-referencing
    m2o/o2m pair) and its many2many to res.partner."""

    def test_edges_only_drawn_between_nodes_in_scope(self):
        options = Options(modules=('base',), depth=0)
        edges = build_edges(self.env, frozenset({'res.partner.category'}), options)
        # partner_ids targets res.partner, which is NOT in node_ids here -
        # no edge should be created for it (PLAN.md, section 8.1: "an edge
        # is only emitted when both endpoints are already nodes").
        self.assertIsNone(_find(edges, kind='many2many', field='partner_ids'))

    def test_many2one_self_reference(self):
        options = Options(modules=('base',), depth=1)
        node_ids = frozenset({'res.partner.category', 'res.partner'})
        edges = build_edges(self.env, node_ids, options)
        m2o = _find(edges, **{'kind': 'many2one', 'from': 'res.partner.category', 'field': 'parent_id'})
        self.assertIsNotNone(m2o)
        self.assertEqual(m2o['to'], 'res.partner.category')

    def test_one2many_is_marked_non_physical(self):
        options = Options(modules=('base',), depth=1)
        node_ids = frozenset({'res.partner.category', 'res.partner'})
        edges = build_edges(self.env, node_ids, options)
        o2m = _find(edges, **{'kind': 'one2many', 'from': 'res.partner.category', 'field': 'child_ids'})
        self.assertIsNotNone(o2m)
        self.assertFalse(o2m['physical'])
        self.assertEqual(o2m['inverse'], 'parent_id')

    def test_many2many_carries_the_real_junction_table(self):
        options = Options(modules=('base',), depth=1)
        node_ids = frozenset({'res.partner.category', 'res.partner'})
        edges = build_edges(self.env, node_ids, options)
        m2m = _find(edges, **{'kind': 'many2many', 'from': 'res.partner.category', 'field': 'partner_ids'})
        self.assertIsNotNone(m2m)
        expected_table = self.env['res.partner.category']._fields['partner_ids'].relation
        self.assertEqual(m2m['junction'], expected_table)
        self.assertEqual(m2m['column1'], 'category_id')
        self.assertEqual(m2m['column2'], 'partner_id')

    def test_inherits_edge(self):
        # ir.cron _inherits ir.actions.server via ir_actions_server_id.
        options = Options(modules=('base',), depth=1)
        node_ids = frozenset({'ir.cron', 'ir.actions.server'})
        edges = build_edges(self.env, node_ids, options)
        inh = _find(edges, **{'kind': 'inherits', 'from': 'ir.cron', 'to': 'ir.actions.server'})
        self.assertIsNotNone(inh)
        self.assertEqual(inh['field'], 'ir_actions_server_id')

    def test_inherited_field_does_not_duplicate_as_its_own_edge(self):
        # ir.actions.server.model_id is a many2one to ir.model; ir.cron
        # *inherits* that field through _inherits (delegation), it does not
        # have its own column for it. With all three models in scope, there
        # must be exactly one edge for this relationship - the many2one from
        # ir.actions.server - and none from ir.cron directly to ir.model.
        options = Options(modules=('base',), depth=1)
        node_ids = frozenset({'ir.cron', 'ir.actions.server', 'ir.model'})
        edges = build_edges(self.env, node_ids, options)
        self.assertIsNone(_find(edges, **{'from': 'ir.cron', 'to': 'ir.model'}))
        self.assertIsNotNone(_find(edges, **{'from': 'ir.actions.server', 'to': 'ir.model', 'field': 'model_id'}))

    def test_edge_ids_are_sequential_and_unique(self):
        options = Options(modules=('base',), depth=1)
        node_ids = frozenset({'res.partner.category', 'res.partner'})
        edges = build_edges(self.env, node_ids, options)
        ids = [e['id'] for e in edges]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids, key=lambda i: int(i[1:])))

    def test_magic_fields_excluded_from_edges_by_default(self):
        options = Options(modules=('base',), depth=1, include_technical_fields=False)
        node_ids = frozenset({'ir.cron', 'res.users'})
        edges = build_edges(self.env, node_ids, options)
        self.assertIsNone(_find(edges, **{'field': 'create_uid'}))
        self.assertIsNone(_find(edges, **{'field': 'write_uid'}))
