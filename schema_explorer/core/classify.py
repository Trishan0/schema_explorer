# -*- coding: utf-8 -*-
"""Node-kind and field-origin classification (PLAN.md, section 7).

Pure functions: everything they need is passed in as plain data (a
:class:`~schema_explorer.core.scope.ScopeInfo`, a registry descriptor dict,
a set of field names), so they are unit-testable with hand-built fixtures
and never touch an Odoo environment themselves.
"""
from __future__ import annotations

#: Odoo's automatic bookkeeping fields (PLAN.md, section 6).
MAGIC_FIELDS = frozenset({
    'id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'display_name',
})


def classify_node_kind(model_name: str, descriptor: dict, scope, *, reached: bool = False) -> str | None:
    """Decide the node kind for ``model_name`` (PLAN.md, section 7.2).

    Checked in order; the first match wins. Returns ``None`` when the model
    is none of these things - i.e. it exists but is out of scope and was
    not reached by expansion, so it should not become a node at all.
    Callers must filter abstract models out *before* calling this (abstract
    models never become nodes; they go in ``abstract_models`` instead).
    """
    if descriptor['transient']:
        return 'wizard'
    if descriptor['is_view']:
        return 'view'
    if scope.owns_model(model_name):
        return 'owned'
    if scope.owns_any_field(model_name):
        return 'extended'
    if reached:
        return 'boundary'
    return None


def classify_field_origin(
    model_name: str,
    field_name: str,
    field_descriptor: dict,
    scope,
    mixin_field_names: frozenset[str] = frozenset(),
) -> str:
    """Decide where a field "comes from" (PLAN.md, section 6).

    Order: magic > inherits (``_inherits`` delegation) > related > mixin >
    extension (added by a scoped module to a model it doesn't own) > own.
    """
    if field_name in MAGIC_FIELDS:
        return 'magic'
    if field_descriptor['inherited']:
        return 'inherits'
    if field_descriptor['related']:
        return 'related'
    if field_name in mixin_field_names:
        return 'mixin'
    owner_module = scope.field_owner.get((model_name, field_name))
    if owner_module is not None and not scope.owns_model(model_name):
        return 'extension'
    return 'own'
