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

    def test_all_delegated_incident_types_listed_in_company_inherits(self):
        # PLAN.md, section 16.3: "all 9 delegated incident types listed in
        # company.inherits_company".
        inherits_company = {e['model']: e['via'] for e in self.graph['company']['inherits_company']}
        incident_types = [
            n['id'] for n in self.graph['nodes']
            if n.get('inherits', {}).get('patient.safety.incident')
        ]
        self.assertEqual(len(incident_types), EXPECTED_INHERITS_CHILD_COUNT)
        for model in incident_types:
            self.assertEqual(inherits_company.get(model), 'patient.safety.incident')

    def test_incident_itself_is_company_scoped(self):
        company_models = {m['model']: m for m in self.graph['company']['company_models']}
        self.assertIn('patient.safety.incident', company_models)
        self.assertEqual(company_models['patient.safety.incident']['company_field'], 'company_id')

    def test_drift_against_real_database_is_the_one_known_finding(self):
        # PLAN.md, section 17, phase 2 exit criteria: every drift item is
        # either real or a fixed false positive. As of 19.0.3.2.0 against
        # odoo_hsapp4, the only genuine finding is res.users.action_id
        # (a many2one with no database-level foreign key - a deliberate
        # Odoo core choice, backed by an @api.constrains instead).
        graph = build_graph(self.env, Options(modules=('patient_safety',), depth=0, physical=True))
        self.assertEqual(len(graph['drift']), 1, graph['drift'])
        self.assertEqual(graph['drift'][0]['check'], 'D5')
        self.assertEqual(graph['drift'][0]['model'], 'res.users')

    def test_hooks_detection_finds_the_company_backfill(self):
        hooks = self.graph['company']['hooks']
        hooks_file = next((h for h in hooks if h['file'] == 'hooks.py'), None)
        self.assertIsNotNone(hooks_file)
        self.assertIn('_backfill_incident_company', hooks_file['functions'])

    def test_acl_matrix_matches_ir_model_access_directly(self):
        # PLAN.md, section 17, phase 3 exit criteria: "ACL matrix for
        # patient_safety matches security/ir.model.access.csv" - checked
        # against the database those rows were loaded into, model by model,
        # rather than re-parsing the CSV file (which the graph never reads
        # either).
        owned_models = [n['id'] for n in self.graph['nodes'] if n['kind'] == 'owned']
        for model_name in owned_models:
            rows = self.graph['security']['access'].get(model_name, [])
            expected = self.env['ir.model.access'].search_count([('model_id.model', '=', model_name)])
            self.assertEqual(len(rows), expected, model_name)

    def test_incident_access_matrix(self):
        rows = {r['group_label']: r for r in self.graph['security']['access']['patient.safety.incident']}
        self.assertIn('Incidents: Own incidents', rows)
        self.assertIn('Incidents: All incidents', rows)
        self.assertFalse(rows['Incidents: Own incidents']['unlink'])

    def test_all_rules_have_english_or_a_safe_fallback(self):
        # PLAN.md, section 17, phase 3 exit criteria: "all 48 rules listed
        # with English or a raw fallback. Zero crashes on any domain."
        all_rules = [r for rules in self.graph['security']['rules'].values() for r in rules]
        self.assertGreater(len(all_rules), 0)
        for rule in all_rules:
            self.assertTrue(rule['english'] or rule['domain'])

    def test_lifecycle_finds_the_incident_state_machine(self):
        incident_entry = next(
            (m for m in self.graph['lifecycle']['models'] if m['model'] == 'patient.safety.incident'), None,
        )
        self.assertIsNotNone(incident_entry)
        state_field = next(f for f in incident_entry['fields'] if f['field'] == 'state')
        self.assertGreater(len(state_field['values']), 3)
        self.assertGreater(len(state_field['transitions_guess']), 3)

    def test_lifecycle_transitions_found_for_delegated_incident_types(self):
        # PLAN.md section 8.4: a delegated incident type's `state` field has
        # no code of its own - the transitions live in the parent
        # (patient.safety.incident)'s source, found and fixed while
        # building this phase.
        entry = next(
            (m for m in self.graph['lifecycle']['models']
             if m['model'] == 'patient.safety.adverse.drug.reaction'), None,
        )
        self.assertIsNotNone(entry)
        state_field = next(f for f in entry['fields'] if f['field'] == 'state')
        self.assertGreater(len(state_field['transitions_guess']), 0)
