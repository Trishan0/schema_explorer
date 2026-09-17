# -*- coding: utf-8 -*-
"""PLAN.md, section 8.4. The regex-scanning half is tested against a small
fixture file (tests/fixtures/lifecycle_sample.py) rather than a real
module's source, so it's independent of patient_safety (PLAN.md, section
16.2) and of any particular business module's code changing under it."""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.analyzers.lifecycle import _is_lifecycle_field, analyze_lifecycle


def _selection_field(name, values, **overrides):
    base = {
        'name': name, 'type': 'selection', 'origin': 'own',
        'selection': [(v, v.capitalize()) for v in values],
    }
    base.update(overrides)
    return base


def _node(model, fields, source=None):
    return {'id': model, 'fields': fields, 'source': source or []}


_FIXTURE_SOURCE = [{'module': 'schema_explorer', 'file': 'tests/fixtures/lifecycle_sample.py', 'class': 'Sample'}]


@tagged('schema_explorer', 'post_install', '-at_install')
class TestIsLifecycleField(TransactionCase):

    def test_matches_plain_state_stage_status(self):
        for name in ('state', 'stage', 'status'):
            self.assertTrue(_is_lifecycle_field({'name': name, 'type': 'selection'}))

    def test_matches_suffixed_names(self):
        for name in ('approval_state', 'kanban_state', 'review_status'):
            self.assertTrue(_is_lifecycle_field({'name': name, 'type': 'selection'}))

    def test_rejects_non_selection_type(self):
        self.assertFalse(_is_lifecycle_field({'name': 'state', 'type': 'char'}))

    def test_rejects_unrelated_names(self):
        for name in ('name', 'partner_id', 'statement_line_id'):
            self.assertFalse(_is_lifecycle_field({'name': name, 'type': 'selection'}))


@tagged('schema_explorer', 'post_install', '-at_install')
class TestAnalyzeLifecycle(TransactionCase):

    def test_model_with_no_lifecycle_field_is_absent(self):
        nodes = [_node('demo.a', [{'name': 'name', 'type': 'char', 'origin': 'own'}])]
        result = analyze_lifecycle(nodes)
        self.assertEqual(result['models'], [])

    def test_values_come_from_the_fields_own_selection(self):
        nodes = [_node('demo.a', [_selection_field('state', ['draft', 'done'])])]
        result = analyze_lifecycle(nodes)
        self.assertEqual(len(result['models']), 1)
        field_entry = result['models'][0]['fields'][0]
        self.assertEqual(field_entry['values'], [('draft', 'Draft'), ('done', 'Done')])

    def test_no_source_means_no_transitions_but_no_crash(self):
        nodes = [_node('demo.a', [_selection_field('state', ['draft', 'done'])], source=[])]
        result = analyze_lifecycle(nodes)
        self.assertEqual(result['models'][0]['fields'][0]['transitions_guess'], [])

    def test_finds_transitions_in_write_and_attribute_assignment(self):
        nodes = [_node(
            'demo.a',
            [_selection_field('state', ['draft', 'confirmed', 'cancelled'])],
            source=_FIXTURE_SOURCE,
        )]
        result = analyze_lifecycle(nodes)
        guessed = result['models'][0]['fields'][0]['transitions_guess']
        self.assertEqual(guessed, ['cancelled', 'confirmed', 'draft'])

    def test_ignores_matches_not_in_the_declared_values(self):
        # the fixture file also sets 'active' to False in the same write()
        # call - that must never be reported as a state transition target.
        nodes = [_node(
            'demo.a',
            [_selection_field('state', ['confirmed'])],  # deliberately narrow
            source=_FIXTURE_SOURCE,
        )]
        result = analyze_lifecycle(nodes)
        guessed = result['models'][0]['fields'][0]['transitions_guess']
        self.assertEqual(guessed, ['confirmed'])
        self.assertNotIn('active', guessed)
        self.assertNotIn('False', guessed)

    def test_inherited_field_scans_the_delegate_parents_source_too(self):
        parent = _node('demo.parent', [_selection_field('state', ['draft', 'confirmed'])], source=_FIXTURE_SOURCE)
        child = _node('demo.child', [
            _selection_field('state', ['draft', 'confirmed'], origin='inherits', stored_on='demo.parent'),
        ], source=[])
        result = analyze_lifecycle([parent, child])
        child_entry = next(m for m in result['models'] if m['model'] == 'demo.child')
        # both 'confirmed' (from write({'state': 'confirmed'})) and 'draft'
        # (from self.state = "draft") are genuinely in the fixture and in
        # this field's declared values.
        self.assertEqual(child_entry['fields'][0]['transitions_guess'], ['confirmed', 'draft'])
