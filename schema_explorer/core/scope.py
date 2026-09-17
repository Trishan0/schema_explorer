# -*- coding: utf-8 -*-
"""Layer B: module ownership (PLAN.md, sections 5.1 and 7.1).

Generic database tools cannot answer "which module owns this table" because
that information does not live in PostgreSQL - it lives in Odoo's own
``ir.model.data``, ``ir.model.relation`` and ``ir.model.constraint`` tables.
This module reads those, and only those; it never guesses ownership from
table-name prefixes.

One subtlety worth flagging: ``ir.model.data`` (``model='ir.model'``) is not
by itself enough to decide "who owns this model". Odoo writes a
``<module>.model_<table>`` xmlid for *every* module that contributes a class
to a model - a pure extension (``mail`` or ``patient_safety`` adding fields
to ``res.company``) gets one exactly like the module that first defined it.
So this only tells us "who touches this", not "who created it"; true
ownership needs the registry too (see
:func:`schema_explorer.core.registry_reader.find_defining_module`), which is
why :func:`resolve_owned_model_module` takes ``env`` and not just ``ir.model.data``
rows.

Depends on ``odoo.api``/an environment, but not on ``odoo.http`` - safe to
import under ``odoo-bin shell``.
"""
from __future__ import annotations

from dataclasses import dataclass

from .registry_reader import find_defining_module


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    version: str
    depends: tuple[str, ...]


@dataclass(frozen=True)
class ScopeInfo:
    """Everything :mod:`classify` needs to decide ownership, computed once
    per :func:`resolve_scope` call and passed down the pipeline."""

    #: the module names actually in scope (after dependency-closure, if any)
    modules: frozenset[str]
    #: model names owned by a module in scope
    owned_models: frozenset[str]
    #: model name -> the module in scope that owns it (only for owned_models)
    owned_model_module: dict[str, str]
    #: model name -> set of field names a module in scope declared on it
    #: (includes fields added to models the module does *not* own, e.g. an
    #: extension of ``res.partner``)
    owned_fields: dict[str, frozenset[str]]
    #: field name -> the (first) module in scope that owns it, per model
    field_owner: dict[tuple[str, str], str]
    #: m2m join table name -> owning module name
    owned_relations: dict[str, str]
    #: constraint name -> owning module name
    owned_constraints: dict[str, str]
    #: module metadata for the modules explicitly requested (not the closure)
    module_infos: tuple[ModuleInfo, ...]

    def owns_model(self, model_name: str) -> bool:
        return model_name in self.owned_models

    def owns_any_field(self, model_name: str) -> bool:
        return bool(self.owned_fields.get(model_name))


def _resolve_dependency_closure(env, modules: tuple[str, ...]) -> frozenset[str]:
    """All modules ``modules`` transitively depend on, plus themselves."""
    ImmModule = env['ir.module.module'].sudo()
    seeds = ImmModule.search([('name', 'in', list(modules))])
    # An empty exclude_states tuple renders as the invalid SQL "NOT IN ()";
    # a state no real module ever has gets the same "exclude nothing" effect
    # safely.
    closure = seeds.upstream_dependencies(exclude_states=('__schema_explorer_none__',))
    names = set(closure.mapped('name')) | set(modules)
    return frozenset(names)


def resolve_owned_models(env, modules: frozenset[str]) -> frozenset[str]:
    """Model names whose ``ir.model`` record was created by a module in scope."""
    return frozenset(resolve_owned_model_module(env, modules))


def resolve_owned_model_module(env, modules: frozenset[str]) -> dict[str, str]:
    """model name -> the module in scope that truly *defined* it.

    ``ir.model.data`` narrows the candidates to models a scoped module
    touches at all (cheap, one query); :func:`find_defining_module` then
    tells us whether that module actually created the model or only
    extended one owned elsewhere - only the former counts as "owned"
    (PLAN.md, section 7.2: an extension of an unowned model is ``extended``,
    never ``owned``, even if it's the only module in scope that touches it).
    """
    Imd = env['ir.model.data'].sudo()
    records = Imd.search(
        [('module', 'in', list(modules)), ('model', '=', 'ir.model')],
        order='id',
    )
    if not records:
        return {}
    candidate_ids = set(records.mapped('res_id'))
    ir_models = env['ir.model'].sudo().browse(candidate_ids).exists()
    result: dict[str, str] = {}
    for m in ir_models:
        try:
            model = env[m.model]
        except KeyError:
            continue
        defining_module = find_defining_module(model)
        if defining_module in modules:
            result[m.model] = defining_module
    return result


def resolve_owned_fields(env, modules: frozenset[str]) -> dict[str, frozenset[str]]:
    """model name -> field names declared by a module in scope.

    This is what lets Schema Explorer attribute a field a module injects
    into *another* module's model (e.g. ``patient_safety`` adding fields to
    ``res.company``) - ``ir.model.fields`` records the model the field lives
    on, independently of who owns that model.
    """
    Imd = env['ir.model.data'].sudo()
    records = Imd.search([('module', 'in', list(modules)), ('model', '=', 'ir.model.fields')])
    if not records:
        return {}
    ir_fields = env['ir.model.fields'].sudo().browse(records.mapped('res_id')).exists()
    result: dict[str, set[str]] = {}
    for f in ir_fields:
        result.setdefault(f.model, set()).add(f.name)
    return {model: frozenset(names) for model, names in result.items()}


def resolve_field_owner(env, modules: frozenset[str]) -> dict[tuple[str, str], str]:
    """(model name, field name) -> the module in scope that declared it.

    When more than one module in scope declares the same field (rare - e.g.
    a same-module second file, or two modules both extending a core model),
    the *first* xmlid found wins; :mod:`classify` treats this as the
    "primary" owner and callers can still see every module via
    ``ir.model.fields`` directly if they need the full list (PLAN.md, R4).
    """
    Imd = env['ir.model.data'].sudo()
    records = Imd.search(
        [('module', 'in', list(modules)), ('model', '=', 'ir.model.fields')],
        order='id',
    )
    if not records:
        return {}
    by_res_id = {r.res_id: r.module for r in records}
    ir_fields = env['ir.model.fields'].sudo().browse(list(by_res_id)).exists()
    owner: dict[tuple[str, str], str] = {}
    for f in ir_fields:
        key = (f.model, f.name)
        if key not in owner:
            owner[key] = by_res_id[f.id]
    return owner


def resolve_owned_relations(env, modules: frozenset[str]) -> dict[str, str]:
    """m2m join table name -> owning module name (``ir.model.relation``)."""
    Relation = env['ir.model.relation'].sudo()
    records = Relation.search([('module.name', 'in', list(modules))])
    return {r.name: r.module.name for r in records}


def resolve_owned_constraints(env, modules: frozenset[str]) -> dict[str, str]:
    """DB constraint name -> owning module name (``ir.model.constraint``)."""
    Constraint = env['ir.model.constraint'].sudo()
    records = Constraint.search([('module.name', 'in', list(modules))])
    return {c.name: c.module.name for c in records}


def resolve_module_infos(env, modules: tuple[str, ...]) -> tuple[ModuleInfo, ...]:
    ImmModule = env['ir.module.module'].sudo()
    records = ImmModule.search([('name', 'in', list(modules))])
    by_name = {m.name: m for m in records}
    infos = []
    for name in modules:
        m = by_name.get(name)
        if m is None:
            infos.append(ModuleInfo(name=name, version='', depends=()))
            continue
        infos.append(ModuleInfo(
            name=m.name,
            version=m.latest_version or '',
            depends=tuple(sorted(m.dependencies_id.mapped('name'))),
        ))
    return tuple(infos)


def resolve_scope(env, options) -> ScopeInfo:
    """Build the full :class:`ScopeInfo` for ``options.modules``.

    ``options`` only needs ``.modules`` and ``.include_dependencies``; kept
    as a duck-typed parameter (rather than importing ``Options``) so tests
    can pass a minimal stand-in.
    """
    requested = tuple(options.modules)
    if options.include_dependencies:
        scoped_modules = _resolve_dependency_closure(env, requested)
    else:
        scoped_modules = frozenset(requested)

    owned_model_module = resolve_owned_model_module(env, scoped_modules)
    return ScopeInfo(
        modules=scoped_modules,
        owned_models=frozenset(owned_model_module),
        owned_model_module=owned_model_module,
        owned_fields=resolve_owned_fields(env, scoped_modules),
        field_owner=resolve_field_owner(env, scoped_modules),
        owned_relations=resolve_owned_relations(env, scoped_modules),
        owned_constraints=resolve_owned_constraints(env, scoped_modules),
        module_infos=resolve_module_infos(env, requested),
    )
