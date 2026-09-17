# -*- coding: utf-8 -*-
"""Layer A: the live ORM registry (PLAN.md, sections 5.1 and 6).

Field metadata is read from the *live* ``Model._fields`` objects, not from
``ir.model.fields`` - the ``relation``/``column1``/``column2`` attributes on
a many2many are only reliably populated on the live field object
(``ir.model.fields.relation_table`` is documented for custom m2m only).

Depends on an Odoo environment, but never on ``odoo.http``.
"""
from __future__ import annotations

RELATIONAL_TYPES = ('many2one', 'one2many', 'many2many')


def get_mixin_chain(model) -> tuple[str, ...]:
    """Abstract ancestor model names mixed into ``model``, closest first.

    Walks the full MRO of the model's dynamically-composed class. Because
    Odoo builds each mixin's own class by first composing *its* ``_inherit``
    chain, a mixin-of-a-mixin (e.g. ``patient.safety.workflow.mixin``
    pulling in ``mail.thread``) is already flattened into the MRO by Python -
    no manual recursion needed.

    ``base`` is excluded even though it is technically an abstract model:
    every single Odoo model implicitly inherits from it (Odoo adds it to
    every model's parents unless the model *is* ``base`` itself), so it
    carries no teaching value as a "mixin" badge - it would just show up on
    every node in every diagram.
    """
    own_name = model._name
    seen: list[str] = []
    for klass in type(model).__mro__:
        name = getattr(klass, '_name', None)
        if not name or name == own_name or name == 'base':
            continue
        if not getattr(klass, '_abstract', False):
            continue
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def _source_from_class(klass) -> dict | None:
    """A relative-to-addon source reference for one contributing class.

    Uses ``__module__`` (e.g. ``odoo.addons.patient_safety.models.foo``)
    rather than the filesystem path, so the result never leaks an absolute
    server path (PLAN.md, section 14).
    """
    mod_path = getattr(klass, '__module__', '') or ''
    parts = mod_path.split('.')
    if 'addons' not in parts:
        return None
    idx = parts.index('addons')
    if idx + 1 >= len(parts):
        return None
    module_name = parts[idx + 1]
    rel_parts = parts[idx + 2:]
    rel_file = '/'.join(rel_parts) + '.py' if rel_parts else None
    return {
        'module': module_name,
        'file': rel_file,
        'class': getattr(klass, '__name__', None),
    }


def find_defining_module(model) -> str | None:
    """The module that truly *created* ``model`` (as opposed to one that
    merely extends it with ``_inherit``).

    This is not the same question as "which modules does ``ir.model.data``
    list for this model" - Odoo creates a ``module.model_<table>`` xmlid for
    *every* module that contributes a class to a model, including pure
    extensions (e.g. ``mail``, ``hr`` and ``patient_safety`` each get one
    for ``res.company``). That table answers "who touches this", not "who
    owns it" - conflating the two would misclassify every extended core
    model (``res.company``, ``res.users``, ...) as "owned" by whichever
    scoped module happens to extend it.

    A naive first attempt here checked which contributing class sets
    ``_name`` directly in its own ``__dict__`` (as opposed to a pure
    ``_inherit`` extension inheriting it) - that turned out to be wrong:
    empirically, Odoo's model-definition machinery gives *every*
    contributing class (extensions included) a literal ``_name`` in its own
    ``__dict__``, not just the one that first introduced the model. The
    actual, framework-maintained answer is ``model._original_module``,
    set exactly once - when the model name is first registered - and never
    touched again by later extensions (see
    ``odoo/orm/model_classes.py:add_to_registry`` and its own use in
    ``odoo/addons/base/models/ir_model.py`` for the equivalent
    field-ownership check).
    """
    return getattr(model, '_original_module', None) or None


def describe_source(model) -> tuple[dict, ...]:
    """Every direct contributing class for ``model`` (one per module/file
    that declares or extends it), deduplicated."""
    seen = set()
    sources = []
    for klass in type(model).__bases__:
        if not getattr(klass, '_name', None):
            continue
        src = _source_from_class(klass)
        if src is None:
            continue
        key = (src['module'], src['file'], src['class'])
        if key in seen:
            continue
        seen.add(key)
        sources.append(src)
    return tuple(sources)


def describe_model(env, model_name: str) -> dict:
    """Raw registry facts about ``model_name`` (PLAN.md, section 5.1, layer A)."""
    model = env[model_name]
    return {
        'model': model_name,
        'table': getattr(model, '_table', '') or '',
        'label': model._description or model_name,
        'abstract': bool(model._abstract),
        'transient': bool(model._transient),
        'auto': bool(model._auto),
        'is_view': bool(getattr(model, '_table_query', None)) or not bool(model._auto),
        'inherits': dict(model._inherits) if model._inherits else {},
        'check_company_auto': bool(getattr(model, '_check_company_auto', False)),
        'mixins': get_mixin_chain(model),
        'source': describe_source(model),
        'field_names': tuple(model._fields.keys()),
    }


def describe_field(model, field_name: str) -> dict:
    """Raw registry facts about one field (PLAN.md, section 6)."""
    f = model._fields[field_name]
    info = {
        'name': field_name,
        'type': f.type,
        'label': f.string or field_name,
        'help': f.help or None,
        'store': bool(f.store),
        # `store=True` is not the same as "has a database column" - a
        # Binary field defaults to `attachment=True` (stored as
        # ir.attachment, not a column) while still being `store=True`.
        # `column_type` is None whenever there is genuinely no column
        # (Odoo's own drift/init logic uses exactly this check - see
        # odoo/orm/fields.py, e.g. line ~503).
        'has_column': bool(f.store and getattr(f, 'column_type', None)),
        'required': bool(getattr(f, 'required', False)),
        'index': bool(getattr(f, 'index', False)),
        'related': f.related if getattr(f, 'related', None) else None,
        'computed': bool(getattr(f, 'compute', None)) and not getattr(f, 'related', None),
        'company_dependent': bool(getattr(f, 'company_dependent', False)),
        'check_company': bool(getattr(f, 'check_company', False)),
        # csv of group xmlids restricting who even sees this field
        # (PLAN.md, section 8.3, "field groups").
        'groups': [g.strip() for g in (getattr(f, 'groups', None) or '').split(',') if g.strip()],
        'inherited': bool(getattr(f, 'inherited', False)),
        'inherited_from': None,
        'target': None,
        'relation_table': None,
        'column1': None,
        'column2': None,
        'ondelete': None,
        'inverse_name': None,
    }
    if info['inherited']:
        inherited_field = getattr(f, 'inherited_field', None)
        if inherited_field is not None:
            info['inherited_from'] = inherited_field.model_name

    if f.type == 'many2one':
        info['target'] = f.comodel_name
        info['ondelete'] = getattr(f, 'ondelete', None)
    elif f.type == 'one2many':
        info['target'] = f.comodel_name
        info['inverse_name'] = getattr(f, 'inverse_name', None)
    elif f.type == 'many2many':
        info['target'] = f.comodel_name
        info['relation_table'] = getattr(f, 'relation', None)
        info['column1'] = getattr(f, 'column1', None)
        info['column2'] = getattr(f, 'column2', None)
    elif f.type == 'selection':
        # `_description_selection` is the same call Odoo itself uses to
        # render a Selection widget - it resolves a static list, a method
        # name, or a callable uniformly. It runs the field's own declared
        # selection-provider method (no records involved), which is safe
        # and expected, unlike evaluating a domain against real data.
        try:
            info['selection'] = list(f._description_selection(model.env))
        except Exception:  # noqa: BLE001 - a selection provider can do anything
            info['selection'] = []

    return info


def describe_fields(model) -> dict[str, dict]:
    """``describe_field`` for every field on ``model``, keyed by name."""
    return {name: describe_field(model, name) for name in model._fields}
