# -*- coding: utf-8 -*-
"""Tests for the RPC service layer (PLAN.md, sections 14 and 15) - the
access checks and caching that sit in front of the pure core pipeline."""
from odoo.exceptions import AccessError
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
            'group_ids': [(4, cls.env.ref(GROUP_PHYSICAL).id)],
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
