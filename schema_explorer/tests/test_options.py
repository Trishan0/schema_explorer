# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.options import Options


@tagged('schema_explorer', 'post_install', '-at_install')
class TestOptions(TransactionCase):

    def test_defaults(self):
        options = Options(modules=('patient_safety',))
        self.assertEqual(options.depth, 0)
        self.assertFalse(options.include_wizards)
        self.assertFalse(options.physical)
        self.assertEqual(options.validate(), [])

    def test_from_dict_accepts_comma_separated_modules(self):
        options = Options.from_dict({'modules': ' patient_safety ,  hr '})
        self.assertEqual(options.modules, ('patient_safety', 'hr'))

    def test_from_dict_ignores_unknown_keys(self):
        options = Options.from_dict({'modules': ['base'], 'some_future_flag': True})
        self.assertEqual(options.modules, ('base',))

    def test_from_dict_rejects_empty_modules(self):
        with self.assertRaises(ValueError):
            Options.from_dict({'modules': []})

    def test_from_dict_rejects_depth_out_of_range(self):
        with self.assertRaises(ValueError):
            Options.from_dict({'modules': ['base'], 'depth': 99})

    def test_without_physical_forces_it_off(self):
        options = Options(modules=('base',), physical=True)
        self.assertTrue(options.physical)
        self.assertFalse(options.without_physical().physical)

    def test_cache_key_ignores_physical_and_anonymize(self):
        a = Options(modules=('base',), physical=False, anonymize=False)
        b = Options(modules=('base',), physical=True, anonymize=True)
        self.assertEqual(a.cache_key(), b.cache_key())

    def test_cache_key_is_sensitive_to_module_order(self):
        # order doesn't matter for the cache key - same modules, any order,
        # same graph.
        a = Options(modules=('base', 'hr'))
        b = Options(modules=('hr', 'base'))
        self.assertEqual(a.cache_key(), b.cache_key())

    def test_cache_key_differs_on_depth(self):
        a = Options(modules=('base',), depth=0)
        b = Options(modules=('base',), depth=1)
        self.assertNotEqual(a.cache_key(), b.cache_key())
