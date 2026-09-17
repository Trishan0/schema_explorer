# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.options import Options
from odoo.addons.schema_explorer.core.scope import (
    resolve_field_owner,
    resolve_module_infos,
    resolve_owned_constraints,
    resolve_owned_fields,
    resolve_owned_model_module,
    resolve_owned_models,
    resolve_owned_relations,
    resolve_scope,
)


@tagged('schema_explorer', 'post_install', '-at_install')
class TestScope(TransactionCase):
    """Layer B (PLAN.md, section 5.1) against the always-installed `base`
    module - this is exactly the mechanism that lets Schema Explorer tell
    "which module owns this table", unlike pgAdmin/DBeaver."""

    def test_owned_models_includes_res_partner(self):
        owned = resolve_owned_models(self.env, frozenset({'base'}))
        self.assertIn('res.partner', owned)
        self.assertIn('res.users', owned)

    def test_owned_model_module_is_authoritative(self):
        mapping = resolve_owned_model_module(self.env, frozenset({'base'}))
        self.assertEqual(mapping.get('res.partner'), 'base')

    def test_owned_fields_attributes_extension_correctly(self):
        # `name` on res.partner is declared by base itself.
        owned_fields = resolve_owned_fields(self.env, frozenset({'base'}))
        self.assertIn('name', owned_fields.get('res.partner', frozenset()))

    def test_field_owner_lookup(self):
        owner = resolve_field_owner(self.env, frozenset({'base'}))
        self.assertEqual(owner.get(('res.partner', 'name')), 'base')

    def test_owned_relations_finds_the_real_m2m_table(self):
        # res.partner.category_id is a many2many with no explicit `relation=`
        # kwarg - the real table name only exists on the live field object.
        real_table = self.env['res.partner']._fields['category_id'].relation
        owned_relations = resolve_owned_relations(self.env, frozenset({'base'}))
        self.assertEqual(owned_relations.get(real_table), 'base')

    def test_owned_constraints_non_empty(self):
        owned_constraints = resolve_owned_constraints(self.env, frozenset({'base'}))
        self.assertTrue(owned_constraints)
        self.assertTrue(all(module == 'base' for module in owned_constraints.values()))

    def test_module_infos(self):
        infos = resolve_module_infos(self.env, ('base',))
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].name, 'base')
        self.assertTrue(infos[0].version)

    def test_resolve_scope_without_dependencies(self):
        options = Options(modules=('base',), include_dependencies=False)
        scope = resolve_scope(self.env, options)
        self.assertEqual(scope.modules, frozenset({'base'}))
        self.assertIn('res.partner', scope.owned_models)

    def test_resolve_scope_dependency_closure_of_base_is_itself(self):
        # base has no dependencies, so this is a safe closure assertion that
        # doesn't depend on which other modules happen to be installed in
        # the test database.
        options = Options(modules=('base',), include_dependencies=True)
        scope = resolve_scope(self.env, options)
        self.assertEqual(scope.modules, frozenset({'base'}))
