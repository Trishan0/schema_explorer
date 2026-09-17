# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.analyzers.company import analyze_company


def _node(model, table, fields, check_company_auto=False):
    return {
        'id': model, 'kind': 'owned', 'table': table, 'label': table,
        'module': 'demo', 'mixins': [], 'inherits': {}, 'fields': fields,
        'check_company_auto': check_company_auto,
    }


def _field(name, ftype, **overrides):
    base = {
        'name': name, 'type': ftype, 'label': name, 'target': None,
        'store': True, 'has_column': ftype not in ('one2many', 'many2many'),
        'required': False, 'index': False, 'origin': 'own',
    }
    base.update(overrides)
    return base


@tagged('schema_explorer', 'post_install', '-at_install')
class TestCompanyAnalyzer(TransactionCase):
    """PLAN.md, section 8.2. Uses hand-built graph fragments so the C1/C4
    classification logic is tested independently of any real module's
    ir.rule records (which the acceptance test against patient_safety
    covers instead, for C2/C3/rules_plain)."""

    def _run(self, nodes, edges):
        return analyze_company(self.env, nodes, edges, modules=[])

    def test_own_company_field_is_scoped(self):
        nodes = [_node('demo.scoped', 'demo_scoped', [_field('company_id', 'many2one', target='res.company')])]
        result = self._run(nodes, [])
        self.assertEqual(len(result['company_models']), 1)
        self.assertEqual(result['company_models'][0]['model'], 'demo.scoped')
        self.assertEqual(result['global_models'], [])

    def test_inherited_company_field_counts_as_scoped_not_global(self):
        nodes = [_node('demo.child', 'demo_child', [
            _field('company_id', 'many2one', target='res.company', origin='inherits', stored_on='demo.parent'),
        ])]
        result = self._run(nodes, [])
        self.assertEqual(len(result['inherits_company']), 1)
        self.assertEqual(result['inherits_company'][0]['via'], 'demo.parent')
        self.assertEqual(result['company_models'], [])
        self.assertEqual(result['global_models'], [])

    def test_model_with_no_company_field_is_global(self):
        nodes = [_node('demo.lookup', 'demo_lookup', [_field('name', 'char')])]
        result = self._run(nodes, [])
        self.assertEqual(result['global_models'], ['demo.lookup'])

    def test_c1_unguarded_link_between_scoped_models(self):
        nodes = [
            _node('demo.a', 'demo_a', [_field('company_id', 'many2one', target='res.company')]),
            _node('demo.b', 'demo_b', [_field('company_id', 'many2one', target='res.company')]),
        ]
        edges = [{
            'id': 'e1', 'kind': 'many2one', 'from': 'demo.a', 'to': 'demo.b',
            'field': 'partner_link_id', 'check_company': False, 'physical': True,
        }]
        result = self._run(nodes, edges)
        c1 = [leak for leak in result['leaks'] if leak['check'] == 'C1']
        self.assertEqual(len(c1), 1)
        self.assertEqual(c1[0]['from'], 'demo.a')

    def test_c1_suppressed_when_check_company_true(self):
        nodes = [
            _node('demo.a', 'demo_a', [_field('company_id', 'many2one', target='res.company')]),
            _node('demo.b', 'demo_b', [_field('company_id', 'many2one', target='res.company')]),
        ]
        edges = [{
            'id': 'e1', 'kind': 'many2one', 'from': 'demo.a', 'to': 'demo.b',
            'field': 'partner_link_id', 'check_company': True, 'physical': True,
        }]
        result = self._run(nodes, edges)
        self.assertFalse([leak for leak in result['leaks'] if leak['check'] == 'C1'])

    def test_c1_suppressed_when_check_company_auto_on_source(self):
        nodes = [
            _node('demo.a', 'demo_a', [_field('company_id', 'many2one', target='res.company')], check_company_auto=True),
            _node('demo.b', 'demo_b', [_field('company_id', 'many2one', target='res.company')]),
        ]
        edges = [{
            'id': 'e1', 'kind': 'many2one', 'from': 'demo.a', 'to': 'demo.b',
            'field': 'partner_link_id', 'check_company': False, 'physical': True,
        }]
        result = self._run(nodes, edges)
        self.assertFalse([leak for leak in result['leaks'] if leak['check'] == 'C1'])

    def test_c1_ignores_non_physical_many2one(self):
        # a computed/related many2one has no real column - not a real
        # cross-company link risk (found against mail.activity.mixin's
        # activity_user_id - see the comment in analyzers/company.py).
        nodes = [
            _node('demo.a', 'demo_a', [_field('company_id', 'many2one', target='res.company')]),
            _node('demo.b', 'demo_b', [_field('company_id', 'many2one', target='res.company')]),
        ]
        edges = [{
            'id': 'e1', 'kind': 'many2one', 'from': 'demo.a', 'to': 'demo.b',
            'field': 'computed_link_id', 'check_company': False, 'physical': False,
        }]
        result = self._run(nodes, edges)
        self.assertFalse([leak for leak in result['leaks'] if leak['check'] in ('C1', 'C4')])

    def test_c4_scoped_to_global_link_is_informational(self):
        nodes = [
            _node('demo.a', 'demo_a', [_field('company_id', 'many2one', target='res.company')]),
            _node('demo.lookup', 'demo_lookup', [_field('name', 'char')]),
        ]
        edges = [{
            'id': 'e1', 'kind': 'many2one', 'from': 'demo.a', 'to': 'demo.lookup',
            'field': 'category_id', 'check_company': False, 'physical': True,
        }]
        result = self._run(nodes, edges)
        c4 = [leak for leak in result['leaks'] if leak['check'] == 'C4']
        self.assertEqual(len(c4), 1)
        self.assertEqual(c4[0]['severity'], 'info')

    def test_c4_not_raised_for_the_models_own_company_field(self):
        # pointing at res.company via company_id/company_ids *is* what
        # "company-scoped" means - not a leak, even though res.company
        # itself has no company_id and so counts as "global".
        nodes = [
            _node('demo.a', 'demo_a', [_field('company_id', 'many2one', target='res.company')]),
            _node('res.company', 'res_company', [_field('name', 'char')]),
        ]
        edges = [{
            'id': 'e1', 'kind': 'many2one', 'from': 'demo.a', 'to': 'res.company',
            'field': 'company_id', 'check_company': False, 'physical': True,
        }]
        result = self._run(nodes, edges)
        self.assertFalse([leak for leak in result['leaks'] if leak['check'] in ('C1', 'C4')])

    def test_company_dependent_field_is_collected(self):
        nodes = [_node('demo.a', 'demo_a', [
            _field('company_id', 'many2one', target='res.company'),
            _field('extra_cost', 'monetary', company_dependent=True),
        ])]
        result = self._run(nodes, [])
        self.assertEqual(result['company_dependent_fields'], [
            {'model': 'demo.a', 'field': 'extra_cost', 'storage': 'jsonb'},
        ])

    def test_no_modules_means_no_hooks(self):
        result = self._run([], [])
        self.assertEqual(result['hooks'], [])
