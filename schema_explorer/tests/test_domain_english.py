# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.analyzers.domain_english import domain_to_english


@tagged('schema_explorer', 'post_install', '-at_install')
class TestDomainEnglish(TransactionCase):
    """Table-driven cases (PLAN.md, section 16.1) - real domain_force text
    taken from patient_safety's own security rules, plus edge cases.
    Malformed input must never raise; it falls back to None (caller shows
    the raw text instead)."""

    def test_simple_company_domain(self):
        self.assertEqual(
            domain_to_english("[('company_id', 'in', company_ids)]"),
            'company_id is one of the companies selected in the company switcher',
        )

    def test_implicit_and_of_two_leaves(self):
        result = domain_to_english(
            "['&', ('reporter_id', '=', user.id), ('company_id', 'in', company_ids)]"
        )
        self.assertEqual(
            result,
            '(reporter_id is the current user) AND '
            '(company_id is one of the companies selected in the company switcher)',
        )

    def test_nested_or_inside_and(self):
        result = domain_to_english(
            "['&', ('company_id', 'in', company_ids), '|', "
            "('department_id', '=', False), ('department_id', 'in', user.allowed_unit_ids.ids)]"
        )
        self.assertIn('company_id is one of the companies selected', result)
        self.assertIn(') OR (', result)
        self.assertIn('department_id is not set', result)

    def test_always_true_constant_domain(self):
        self.assertEqual(domain_to_english("[(1, '=', 1)]"), 'always true')

    def test_always_false_constant_domain(self):
        self.assertEqual(domain_to_english("[(1, '=', 0)]"), 'always false')

    def test_not_operator(self):
        result = domain_to_english("['!', ('active', '=', False)]")
        self.assertTrue(result.startswith('NOT ('))
        self.assertIn('active is not set', result)

    def test_false_literal_reads_as_not_set(self):
        self.assertEqual(domain_to_english("[('parent_id', '=', False)]"), 'parent_id is not set')

    def test_empty_domain_returns_none(self):
        self.assertIsNone(domain_to_english('[]'))

    def test_blank_string_returns_none(self):
        self.assertIsNone(domain_to_english(''))
        self.assertIsNone(domain_to_english(None))

    def test_garbage_text_returns_none_not_raise(self):
        self.assertIsNone(domain_to_english('this is not python at all !!'))

    def test_unrecognised_value_falls_back_to_source_text(self):
        # `some_weird_function()` isn't in the known-phrase table - the
        # condition should still render, using the raw call as text,
        # rather than failing the whole domain.
        result = domain_to_english("[('date', '<=', some_weird_function())]")
        self.assertIn('some_weird_function()', result)

    def test_never_evaluates_anything(self):
        # a domain that would raise/exit/do damage if it were ever eval'd -
        # parsing it must still succeed harmlessly (nothing here should
        # execute Python, only read its syntax tree).
        result = domain_to_english("[('x', '=', __import__('os').system('true'))]")
        self.assertIsNotNone(result)
        self.assertIn('os', result)
