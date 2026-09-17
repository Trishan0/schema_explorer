# -*- coding: utf-8 -*-
"""Tests for the RPC service layer (PLAN.md, sections 14 and 15) - the
access checks and caching that sit in front of the pure core pipeline."""
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.models.schema_explorer_service import (
    GROUP_PHYSICAL,
    GROUP_USER,
)


@tagged('schema_explorer', 'post_install', '-at_install')
class TestSchemaExplorerService(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env['schema.explorer.service']
        cls.plain_user = cls.env['res.users'].create({
            'name': 'Schema Explorer Plain User',
            'login': 'se_plain_user',
        })
        cls.se_user = cls.env['res.users'].create({
            'name': 'Schema Explorer User',
            'login': 'se_user',
            'group_ids': [(4, cls.env.ref(GROUP_USER).id)],
        })
        cls.se_physical_user = cls.env['res.users'].create({
            'name': 'Schema Explorer Physical User',
            'login': 'se_physical_user',
            # base.group_user too: get_sample_records never sudo()s, so
            # reading res.partner needs the same real access an ordinary
            # internal user would need - this is the point being tested.
            'group_ids': [(4, cls.env.ref(GROUP_PHYSICAL).id), (4, cls.env.ref('base.group_user').id)],
        })

    def test_get_graph_requires_group(self):
        with self.assertRaises(AccessError):
            self.service.with_user(self.plain_user).get_graph({'modules': ['base']})

    def test_get_graph_works_for_group_member(self):
        graph = self.service.with_user(self.se_user).get_graph({'modules': ['base'], 'depth': 0})
        self.assertGreater(len(graph['nodes']), 0)

    def test_get_graph_rejects_invalid_options(self):
        with self.assertRaises(Exception):
            self.service.with_user(self.se_user).get_graph({'modules': [], 'depth': 0})

    def test_physical_silently_downgraded_without_physical_group(self):
        # a user with only the base group asking for physical=True does not
        # get an error - they just don't get physical data (PLAN.md,
        # section 14).
        graph = self.service.with_user(self.se_user).get_graph({
            'modules': ['base'], 'depth': 0, 'physical': True,
        })
        self.assertNotIn('internal contract issue', ' '.join(graph['warnings']))

    def test_get_module_choices_requires_group(self):
        with self.assertRaises(AccessError):
            self.service.with_user(self.plain_user).get_module_choices('base')

    def test_get_module_choices_finds_base(self):
        results = self.service.with_user(self.se_user).get_module_choices('base', 10)
        self.assertTrue(any(r['name'] == 'base' for r in results))

    def test_graph_cache_returns_identical_object_on_repeat_call(self):
        options = {'modules': ['base'], 'depth': 0}
        first = self.service.with_user(self.se_user).get_graph(options)
        second = self.service.with_user(self.se_user).get_graph(options)
        # the cache returns the *same* dict instance when nothing changed -
        # a cheap, direct way to prove the cache hit without mocking time.
        self.assertIs(first, second)

    def test_physical_requests_are_never_cached(self):
        options = {'modules': ['base'], 'depth': 0, 'physical': True}
        first = self.service.with_user(self.se_physical_user).get_graph(options)
        second = self.service.with_user(self.se_physical_user).get_graph(options)
        self.assertIsNot(first, second)

    def test_sample_records_requires_the_physical_group(self):
        # PLAN.md, section 9.5 point 8: gated behind the stricter group,
        # not just the base one.
        with self.assertRaises(AccessError):
            self.service.with_user(self.se_user).get_sample_records('res.partner')

    def test_sample_records_requires_base_group_too(self):
        with self.assertRaises(AccessError):
            self.service.with_user(self.plain_user).get_sample_records('res.partner')

    def test_sample_records_never_sudos_past_real_acls(self):
        # a user with the physical group but no ordinary internal-user
        # access still can't read res.partner through this method - proves
        # get_sample_records genuinely never sudo()s (PLAN.md, section 14).
        no_base_access_user = self.env['res.users'].create({
            'name': 'Schema Explorer Physical User (no base access)',
            'login': 'se_physical_no_base_access',
            'group_ids': [(4, self.env.ref(GROUP_PHYSICAL).id)],
        })
        with self.assertRaises(AccessError):
            self.service.with_user(no_base_access_user).get_sample_records('res.partner')

    def test_sample_records_returns_real_rows_respecting_acls(self):
        result = self.service.with_user(self.se_physical_user).get_sample_records('res.partner', limit=3)
        self.assertIn('display_name', result['field_names'])
        self.assertLessEqual(len(result['records']), 3)
        self.assertGreaterEqual(result['total_count'], len(result['records']))

    def test_sample_records_excludes_relational_and_binary_fields(self):
        result = self.service.with_user(self.se_physical_user).get_sample_records('res.partner', limit=1)
        for name in result['field_names']:
            field = self.env['res.partner']._fields[name]
            self.assertNotIn(field.type, ('one2many', 'many2many', 'binary', 'html'))

    def test_sample_records_unknown_model_raises_user_error(self):
        with self.assertRaises(UserError):
            self.service.with_user(self.se_physical_user).get_sample_records('does.not.exist')
