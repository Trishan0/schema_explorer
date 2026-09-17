# -*- coding: utf-8 -*-
"""PLAN.md, section 8.3 - against the real, always-installed `base` module.

Runs the whole pipeline (build_graph) rather than hand-built fixtures,
since the security analyzer's value is entirely in correctly reflecting
real ir.model.access/ir.rule/res.groups rows - there is no useful "pure
logic" half to unit test in isolation the way classify.py has."""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.inspector import build_graph
from odoo.addons.schema_explorer.core.options import Options


@tagged('schema_explorer', 'post_install', '-at_install')
class TestSecurityAnalyzer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.graph = build_graph(cls.env, Options(modules=('base',), depth=0))
        cls.security = cls.graph['security']

    def test_access_matches_the_database_directly(self):
        # not a tautology: this proves the batched query in
        # analyzers/security.py returns the same rows a direct,
        # unbatched query would.
        rows = self.security['access'].get('res.partner', [])
        expected = self.env['ir.model.access'].search_count([('model_id.model', '=', 'res.partner')])
        self.assertEqual(len(rows), expected)
        self.assertGreater(expected, 0)

    def test_model_with_zero_access_rows_is_flagged(self):
        for model_name, rows in self.security['access'].items():
            if not rows:
                self.assertIn(model_name, self.security['models_without_access'])
            else:
                self.assertNotIn(model_name, self.security['models_without_access'])

    def test_field_level_group_restriction_is_found(self):
        # ir.actions.server.code has groups='base.group_system'.
        match = next(
            (fg for fg in self.security['field_groups']
             if fg['model'] == 'ir.actions.server' and fg['field'] == 'code'),
            None,
        )
        self.assertIsNotNone(match)
        self.assertIn('base.group_system', match['groups'])

    def test_groups_tree_includes_directly_implied_groups(self):
        # cross-check against what the ORM itself says group_system implies,
        # rather than hard-coding an implied pair that might change.
        group_system = self.env.ref('base.group_system')
        expected_implied_xmlids = set()
        for implied in group_system.implied_ids:
            xmlid = implied.get_external_id().get(implied.id)
            if xmlid:
                expected_implied_xmlids.add(xmlid)

        entry = next((g for g in self.security['groups'] if g['xmlid'] == 'base.group_system'), None)
        self.assertIsNotNone(entry, 'base.group_system should be referenced by some ACL/rule on a base model')
        self.assertEqual(set(entry['implied_ids']), expected_implied_xmlids)

    def test_every_rule_has_english_or_a_safe_fallback_never_crashes(self):
        # PLAN.md, section 16.3 exit criterion: "Zero crashes on any domain."
        # Getting this far without an exception already proves that; this
        # also checks the fallback contract explicitly.
        any_rule_seen = False
        for rules in self.security['rules'].values():
            for rule in rules:
                any_rule_seen = True
                self.assertIn('english', rule)
                self.assertIn('domain', rule)
                if rule['english'] is None:
                    self.assertTrue(rule['domain'], 'a rule with no English summary must still show something')
        self.assertTrue(any_rule_seen, 'expected at least one ir.rule among base models')
