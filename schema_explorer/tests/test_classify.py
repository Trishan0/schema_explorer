# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.classify import classify_field_origin, classify_node_kind
from odoo.addons.schema_explorer.core.scope import ScopeInfo


def _descriptor(**overrides) -> dict:
    base = {
        'transient': False,
        'is_view': False,
    }
    base.update(overrides)
    return base


def _scope(**overrides) -> ScopeInfo:
    base = dict(
        modules=frozenset({'demo_module'}),
        owned_models=frozenset(),
        owned_model_module={},
        owned_fields={},
        field_owner={},
        owned_relations={},
        owned_constraints={},
        module_infos=(),
    )
    base.update(overrides)
    return ScopeInfo(**base)


@tagged('schema_explorer', 'post_install', '-at_install')
class TestClassifyNodeKind(TransactionCase):
    """PLAN.md, section 7.2 - the node-kind decision table, unit tested with
    hand-built descriptors so no Odoo environment is actually exercised."""

    def test_transient_wins_even_if_owned(self):
        scope = _scope(owned_models=frozenset({'demo.wizard'}))
        kind = classify_node_kind('demo.wizard', _descriptor(transient=True), scope)
        self.assertEqual(kind, 'wizard')

    def test_view_model(self):
        scope = _scope()
        kind = classify_node_kind('res.device', _descriptor(is_view=True), scope)
        self.assertEqual(kind, 'view')

    def test_owned_model(self):
        scope = _scope(owned_models=frozenset({'demo.model'}))
        kind = classify_node_kind('demo.model', _descriptor(), scope)
        self.assertEqual(kind, 'owned')

    def test_extended_model_not_owned_but_field_added(self):
        scope = _scope(owned_fields={'res.partner': frozenset({'x_demo_field'})})
        kind = classify_node_kind('res.partner', _descriptor(), scope)
        self.assertEqual(kind, 'extended')

    def test_boundary_only_when_reached(self):
        scope = _scope()
        self.assertIsNone(classify_node_kind('res.currency', _descriptor(), scope, reached=False))
        self.assertEqual(
            classify_node_kind('res.currency', _descriptor(), scope, reached=True), 'boundary',
        )

    def test_owned_wins_over_boundary(self):
        scope = _scope(owned_models=frozenset({'demo.model'}))
        kind = classify_node_kind('demo.model', _descriptor(), scope, reached=True)
        self.assertEqual(kind, 'owned')


def _field(**overrides) -> dict:
    base = {'inherited': False, 'related': None}
    base.update(overrides)
    return base


@tagged('schema_explorer', 'post_install', '-at_install')
class TestClassifyFieldOrigin(TransactionCase):
    """PLAN.md, section 6 - field origin decision order."""

    def test_magic_field(self):
        scope = _scope()
        origin = classify_field_origin('demo.model', 'create_uid', _field(), scope)
        self.assertEqual(origin, 'magic')

    def test_inherited_via_delegation(self):
        scope = _scope()
        origin = classify_field_origin('demo.child', 'company_id', _field(inherited=True), scope)
        self.assertEqual(origin, 'inherits')

    def test_related_field(self):
        scope = _scope()
        origin = classify_field_origin(
            'demo.model', 'partner_name', _field(related='partner_id.name'), scope,
        )
        self.assertEqual(origin, 'related')

    def test_mixin_field(self):
        scope = _scope()
        origin = classify_field_origin(
            'demo.model', 'message_ids', _field(), scope,
            mixin_field_names=frozenset({'message_ids'}),
        )
        self.assertEqual(origin, 'mixin')

    def test_extension_field_on_unowned_model(self):
        scope = _scope(field_owner={('res.partner', 'x_demo_field'): 'demo_module'})
        origin = classify_field_origin('res.partner', 'x_demo_field', _field(), scope)
        self.assertEqual(origin, 'extension')

    def test_own_field_on_owned_model_even_if_module_matches(self):
        # a module extending its *own* model in a second file is still "own",
        # not "extension" - extension only applies to models the module
        # doesn't own (PLAN.md, section 7.2 note on the same-module case).
        scope = _scope(
            owned_models=frozenset({'demo.model'}),
            field_owner={('demo.model', 'extra_field'): 'demo_module'},
        )
        origin = classify_field_origin('demo.model', 'extra_field', _field(), scope)
        self.assertEqual(origin, 'own')

    def test_plain_own_field(self):
        scope = _scope()
        origin = classify_field_origin('demo.model', 'name', _field(), scope)
        self.assertEqual(origin, 'own')

    def test_related_takes_priority_over_mixin(self):
        scope = _scope()
        origin = classify_field_origin(
            'demo.model', 'related_and_mixin', _field(related='x.y'), scope,
            mixin_field_names=frozenset({'related_and_mixin'}),
        )
        self.assertEqual(origin, 'related')
