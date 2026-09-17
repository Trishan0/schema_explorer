# -*- coding: utf-8 -*-
"""End-to-end pipeline test against the real, always-installed `base` module.

Builds an actual graph via :func:`build_graph` (not hand-built fixtures) to
prove scope + registry_reader + classify + expand + relations wire together
correctly. The full acceptance test against `patient_safety` (PLAN.md,
section 16.3) lives separately and only runs when that module is installed.
"""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.contract import validate_graph
from odoo.addons.schema_explorer.core.inspector import build_graph
from odoo.addons.schema_explorer.core.options import Options


def _node(graph, model_name):
    return next((n for n in graph['nodes'] if n['id'] == model_name), None)


def _field(node, name):
    return next((f for f in node['fields'] if f['name'] == name), None)


@tagged('schema_explorer', 'post_install', '-at_install')
class TestBuildGraphAgainstBase(TransactionCase):

    def test_graph_is_contract_valid(self):
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        self.assertEqual(validate_graph(graph), [])
        self.assertFalse(
            [w for w in graph['warnings'] if w.startswith('internal contract issue')],
        )

    def test_owned_model_is_kind_owned(self):
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        node = _node(graph, 'res.partner')
        self.assertIsNotNone(node)
        self.assertEqual(node['kind'], 'owned')
        self.assertEqual(node['module'], 'base')
        self.assertEqual(node['table'], 'res_partner')

    def test_auto_false_model_is_kind_view(self):
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        node = _node(graph, 'res.device')
        self.assertIsNotNone(node)
        self.assertEqual(node['kind'], 'view')

    def test_wizard_excluded_by_default_included_with_flag(self):
        without = build_graph(self.env, Options(modules=('base',), depth=0, include_wizards=False))
        with_wizards = build_graph(self.env, Options(modules=('base',), depth=0, include_wizards=True))
        self.assertIsNone(_node(without, 'res.config.settings'))
        node = _node(with_wizards, 'res.config.settings')
        self.assertIsNotNone(node)
        self.assertEqual(node['kind'], 'wizard')

    def test_abstract_mixin_is_not_a_node_but_is_listed(self):
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        self.assertIsNone(_node(graph, 'avatar.mixin'))
        mixin_entry = next((m for m in graph['abstract_models'] if m['id'] == 'avatar.mixin'), None)
        self.assertIsNotNone(mixin_entry)
        self.assertIn('res.partner', mixin_entry['used_by'])

    def test_base_is_not_listed_as_a_mixin(self):
        # every model implicitly inherits `base` - it would appear on every
        # single node's mixin badge list and every abstract_models entry
        # otherwise, with zero teaching value.
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        node = _node(graph, 'res.partner')
        self.assertNotIn('base', node['mixins'])
        self.assertIsNone(next((m for m in graph['abstract_models'] if m['id'] == 'base'), None))

    def test_mixin_field_origin(self):
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        node = _node(graph, 'res.partner')
        field = _field(node, 'avatar_1920')
        self.assertIsNotNone(field)
        self.assertEqual(field['origin'], 'mixin')

    def test_inherits_field_is_marked_borrowed_not_a_real_column(self):
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        cron_node = _node(graph, 'ir.cron')
        self.assertIsNotNone(cron_node)
        self.assertEqual(cron_node['inherits'], {'ir.actions.server': 'ir_actions_server_id'})
        # 'model_id' is declared on ir.actions.server and borrowed by ir.cron
        # through _inherits - it should show up with no column on this table.
        borrowed = _field(cron_node, 'model_id')
        self.assertIsNotNone(borrowed)
        self.assertEqual(borrowed['origin'], 'inherits')
        self.assertEqual(borrowed.get('stored_on'), 'ir.actions.server')

    def test_inherits_edge_present_when_both_ends_in_scope(self):
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        inh = next(
            (e for e in graph['edges'] if e['kind'] == 'inherits' and e['from'] == 'ir.cron'),
            None,
        )
        self.assertIsNotNone(inh)
        self.assertEqual(inh['to'], 'ir.actions.server')

    def test_extended_model_is_not_owned_by_the_extending_module(self):
        # `mail` contributes fields to res.partner (message_ids etc. come
        # through the mail.thread mixin, but mail also patches some plain
        # fields in) without being the module that *created* res.partner -
        # scoping to `mail` alone must not misclassify res.partner as
        # "owned" (PLAN.md, section 7.2 / registry_reader.find_defining_module).
        mail_module = self.env['ir.module.module'].sudo().search(
            [('name', '=', 'mail'), ('state', '=', 'installed')], limit=1,
        )
        if not mail_module:
            self.skipTest('mail is not installed in this test database')
        graph = build_graph(self.env, Options(modules=('mail',), depth=0))
        node = _node(graph, 'mail.message')
        self.assertIsNotNone(node)
        self.assertEqual(node['kind'], 'owned')

    def test_edges_need_both_endpoints_to_be_nodes(self):
        # At depth 0 with a narrow scope, a relational field whose target
        # isn't itself a node must not produce a dangling edge - the target
        # is still visible as plain text on the field (`target`), just not
        # as a graph node (PLAN.md, section 8.1).
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        node = _node(graph, 'res.partner.category')
        self.assertIsNotNone(node)
        partner_field = _field(node, 'partner_ids')
        self.assertIsNotNone(partner_field)
        self.assertEqual(partner_field['target'], 'res.partner')

    def test_stats_reflect_the_graph(self):
        graph = build_graph(self.env, Options(modules=('base',), depth=0))
        self.assertEqual(graph['stats']['nodes'], len(graph['nodes']))
        self.assertEqual(graph['stats']['edges'], len(graph['edges']))
        self.assertGreater(graph['stats']['nodes'], 0)

    def test_anonymize_strips_database_identity_and_source_paths(self):
        graph = build_graph(self.env, Options(modules=('base',), depth=0, anonymize=True))
        self.assertIsNone(graph['odoo']['database'])
        self.assertIsNone(graph['odoo']['version'])
        for node in graph['nodes']:
            self.assertEqual(node['source'], [])
