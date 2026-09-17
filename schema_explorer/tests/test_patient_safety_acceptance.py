# -*- coding: utf-8 -*-
"""Acceptance test against the reference module (PLAN.md, sections 4 and
16.3). Skips itself gracefully when `patient_safety` isn't installed in the
target test database, or is at a different version than these numbers were
measured against - it never fails the suite just because a developer's
local database doesn't happen to have it.
"""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.inspector import build_graph
from odoo.addons.schema_explorer.core.options import Options
from odoo.addons.schema_explorer.core.scope import resolve_scope

#: PLAN.md, section 4 - measured 2026-09-17 against odoo_hsapp4.
#: Note: ir.model.data lists 54 models patient_safety *touches* (its own
#: models + res.company/res.users/res.groups/res.partner, which it only
#: extends). "Owned" here means genuinely defined by patient_safety, which
#: excludes those 4 - see registry_reader.find_defining_module.
EXPECTED_VERSION = '19.0.3.2.0'
EXPECTED_OWNED_MODEL_COUNT = 45
EXPECTED_JUNCTION_TABLE_COUNT = 13
EXPECTED_INHERITS_CHILD_COUNT = 9
EXPECTED_EXTENDED_CORE_MODELS = ('res.company', 'res.users', 'res.groups', 'res.partner')
EXPECTED_WIZARD_IDS = (
    'patient.safety.no.action.plan.wizard',
    'patient.safety.initial.review.wizard',
    'patient.safety.selection.wizard',
)


def _node(graph, model_name):
    return next((n for n in graph['nodes'] if n['id'] == model_name), None)


@tagged('schema_explorer_reference', 'post_install', '-at_install')
class TestPatientSafetyAcceptance(TransactionCase):

    def setUp(self):
        super().setUp()
        module = self.env['ir.module.module'].sudo().search(
            [('name', '=', 'patient_safety')], limit=1,
        )
        if not module or module.state != 'installed':
            self.skipTest('patient_safety is not installed in this test database')
        if module.latest_version != EXPECTED_VERSION:
            self.skipTest(
                f'patient_safety is at version {module.latest_version!r}, these '
                f'assertions are pinned to {EXPECTED_VERSION!r} (PLAN.md, section 4)'
            )
        self.options = Options(modules=('patient_safety',), depth=0, include_wizards=True)
        self.graph = build_graph(self.env, self.options)

    def test_owned_model_count(self):
        owned = [n for n in self.graph['nodes'] if n['kind'] == 'owned']
        self.assertEqual(len(owned), EXPECTED_OWNED_MODEL_COUNT)

    def test_junction_table_count(self):
        scope = resolve_scope(self.env, Options(modules=('patient_safety',)))
        self.assertEqual(len(scope.owned_relations), EXPECTED_JUNCTION_TABLE_COUNT)

    def test_inherits_edges_to_incident(self):
        inh = [
            e for e in self.graph['edges']
            if e['kind'] == 'inherits' and e['to'] == 'patient.safety.incident'
        ]
        self.assertEqual(len(inh), EXPECTED_INHERITS_CHILD_COUNT)

    def test_workflow_mixin_not_a_node_but_used_by_incident_types(self):
        self.assertIsNone(_node(self.graph, 'patient.safety.workflow.mixin'))
        entry = next(
            (m for m in self.graph['abstract_models'] if m['id'] == 'patient.safety.workflow.mixin'),
            None,
        )
        self.assertIsNotNone(entry)
        self.assertEqual(len(entry['used_by']), EXPECTED_INHERITS_CHILD_COUNT)

    def test_scan_provider_is_not_a_node(self):
        self.assertIsNone(_node(self.graph, 'patient.scan.provider'))

    def test_core_models_are_extended_not_owned(self):
        for model in EXPECTED_EXTENDED_CORE_MODELS:
            node = _node(self.graph, model)
            self.assertIsNotNone(node, f'{model} should appear as a node (extended)')
            self.assertEqual(node['kind'], 'extended')

    def test_incident_is_a_single_merged_owned_node(self):
        # patient_safety_incident_inherit.py re-opens the model in a second
        # file; it must not create a second/duplicate node.
        matches = [n for n in self.graph['nodes'] if n['id'] == 'patient.safety.incident']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['kind'], 'owned')

    def test_wizard_nodes_present_when_included(self):
        wizard_ids = {n['id'] for n in self.graph['nodes'] if n['kind'] == 'wizard'}
        self.assertTrue(set(EXPECTED_WIZARD_IDS).issubset(wizard_ids))

    def test_wizards_hidden_by_default(self):
        graph = build_graph(self.env, Options(modules=('patient_safety',), depth=0, include_wizards=False))
        wizard_ids = {n['id'] for n in graph['nodes'] if n['kind'] == 'wizard'}
        self.assertFalse(wizard_ids)
