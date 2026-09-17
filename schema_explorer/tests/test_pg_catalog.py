# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.physical.pg_catalog import count_public_tables, fetch_physical


@tagged('schema_explorer', 'post_install', '-at_install')
class TestPgCatalog(TransactionCase):
    """PLAN.md, section 8.5 - against the real res.partner table."""

    def test_count_public_tables_is_positive(self):
        self.assertGreater(count_public_tables(self.env), 0)

    def test_fetch_physical_for_real_table(self):
        physical = fetch_physical(self.env, ['res_partner'])
        entry = physical['res_partner']
        self.assertTrue(entry['exists'])
        self.assertFalse(entry['is_view'])
        self.assertIn('name', entry['columns'])
        self.assertIsInstance(entry['total_bytes'], int)

    def test_fetch_physical_finds_a_foreign_key(self):
        physical = fetch_physical(self.env, ['res_partner'])
        fk_columns = {
            c['definition'] for c in physical['res_partner']['constraints'] if c['type'] == 'foreign_key'
        }
        self.assertTrue(any('company_id' in d for d in fk_columns))

    def test_fetch_physical_missing_table(self):
        physical = fetch_physical(self.env, ['this_table_does_not_exist_xyz'])
        entry = physical['this_table_does_not_exist_xyz']
        self.assertFalse(entry['exists'])
        self.assertEqual(entry['columns'], {})
        self.assertEqual(entry['constraints'], [])

    def test_fetch_physical_empty_input(self):
        self.assertEqual(fetch_physical(self.env, []), {})

    def test_fetch_physical_res_device_is_a_view(self):
        # res.device is `_auto = False` in base - a real SQL view.
        physical = fetch_physical(self.env, ['res_device'])
        self.assertTrue(physical['res_device']['exists'])
        self.assertTrue(physical['res_device']['is_view'])
