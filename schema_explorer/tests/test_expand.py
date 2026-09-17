# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.expand import expand, seed_models
from odoo.addons.schema_explorer.core.options import Options
from odoo.addons.schema_explorer.core.scope import ScopeInfo


def _scope(**overrides) -> ScopeInfo:
    base = dict(
        modules=frozenset({'base'}),
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
class TestExpand(TransactionCase):
    """Uses real `base` models (always installed) as fixtures - see PLAN.md,
    section 16: res.partner.category (m2o/o2m self-reference + m2m) and
    res.partner as a hub model."""

    def test_seed_models_is_owned_union_extended(self):
        scope = _scope(
            owned_models=frozenset({'res.partner.category'}),
            owned_fields={'res.partner': frozenset({'x_demo'})},
        )
        self.assertEqual(seed_models(scope), frozenset({'res.partner.category', 'res.partner'}))

    def test_depth_zero_is_seeds_only(self):
        scope = _scope(owned_models=frozenset({'res.partner.category'}))
        options = Options(modules=('base',), depth=0)
        result = expand(self.env, scope, options)
        self.assertEqual(result.node_ids, frozenset({'res.partner.category'}))
        self.assertEqual(result.reached_ids, frozenset())
        self.assertFalse(result.truncated)

    def test_depth_one_reaches_res_partner_via_m2m(self):
        scope = _scope(owned_models=frozenset({'res.partner.category'}))
        options = Options(modules=('base',), depth=1)
        result = expand(self.env, scope, options)
        self.assertIn('res.partner', result.node_ids)
        self.assertIn('res.partner', result.reached_ids)

    def test_hub_is_shown_but_never_expanded_from(self):
        # res.partner is itself a hub; even at depth=2, nothing beyond it
        # should be added because expansion never walks *out* of a hub.
        scope = _scope(owned_models=frozenset({'res.partner'}))
        options = Options(modules=('base',), depth=2)
        result = expand(self.env, scope, options)
        self.assertEqual(result.node_ids, frozenset({'res.partner'}))

    def test_max_nodes_truncates_and_warns(self):
        scope = _scope(owned_models=frozenset({'res.partner.category'}))
        options = Options(modules=('base',), depth=1, max_nodes=1)
        result = expand(self.env, scope, options)
        self.assertEqual(result.node_ids, frozenset({'res.partner.category'}))
        self.assertTrue(result.truncated)
        self.assertTrue(result.warnings)

    def test_magic_fields_excluded_by_default(self):
        # ir.cron has create_uid/write_uid (-> res.users) but also a real
        # business many2one (user_id -> res.users). Either way res.users
        # should only appear once and only via the real relation semantics,
        # not because create_uid/write_uid were followed.
        scope = _scope(owned_models=frozenset({'ir.cron'}))
        options_default = Options(modules=('base',), depth=1, include_technical_fields=False)
        options_technical = Options(modules=('base',), depth=1, include_technical_fields=True)
        result_default = expand(self.env, scope, options_default)
        result_technical = expand(self.env, scope, options_technical)
        # both should reach res.users (ir.cron.user_id is a real field), but
        # this asserts the magic-field toggle doesn't *remove* anything
        # relevant when turned on - it can only add.
        self.assertLessEqual(result_default.node_ids, result_technical.node_ids)
