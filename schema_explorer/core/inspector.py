# -*- coding: utf-8 -*-
"""The pipeline orchestrator (PLAN.md, section 5.2).

:func:`build_graph` is the one entry point every renderer (in-app OWL
action, standalone HTML export, ``odoo-bin shell`` script) calls. It is a
pure function of ``(env, options)`` - no ``odoo.http``, no ``request`` - so
it also runs unmodified from a shell script with no web server involved
(PLAN.md, decision D1).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import odoo

from .classify import MAGIC_FIELDS, classify_field_origin, classify_node_kind
from .contract import new_graph_skeleton, validate_graph
from .expand import expand
from .registry_reader import describe_field, describe_model
from .scope import resolve_scope
from .analyzers.relations import build_edges


def _get_model(env, model_name: str):
    try:
        return env[model_name]
    except KeyError:
        return None


def _field_output(model_name: str, fdesc: dict, origin: str, defined_in_module: str | None) -> dict:
    out = {
        'name': fdesc['name'],
        'type': fdesc['type'],
        'label': fdesc['label'],
        'target': fdesc['target'],
        'store': fdesc['store'],
        'required': fdesc['required'],
        'index': fdesc['index'],
        'origin': origin,
        'defined_in_module': defined_in_module,
    }
    if fdesc['type'] == 'many2one':
        out['ondelete'] = fdesc['ondelete']
    elif fdesc['type'] == 'one2many':
        out['inverse_name'] = fdesc['inverse_name']
    elif fdesc['type'] == 'many2many':
        out['relation_table'] = fdesc['relation_table']
        out['column1'] = fdesc['column1']
        out['column2'] = fdesc['column2']
    if fdesc['inherited_from']:
        # Borrowed through _inherits: not a real column on this table.
        out['stored_on'] = fdesc['inherited_from']
    if fdesc['related']:
        out['related_path'] = fdesc['related']
    if fdesc['check_company']:
        out['check_company'] = True
    if fdesc['company_dependent']:
        out['company_dependent'] = True
    return out


def _node_module(model_name: str, descriptor: dict, scope) -> str | None:
    """Best display attribution for "which module is this".

    Authoritative for owned models (``ir.model.data``); for anything else
    (extended/boundary/wizard/view) falls back to the first module whose
    Python class contributes to this model, per the live registry.
    """
    owner = scope.owned_model_module.get(model_name)
    if owner:
        return owner
    for src in descriptor['source']:
        if src.get('module'):
            return src['module']
    return None


def build_graph(env, options) -> dict:
    """Build the full schema graph for ``options`` (PLAN.md, section 6).

    ``options`` is a :class:`schema_explorer.core.options.Options` (or any
    duck-typed equivalent exposing the same attributes).
    """
    started = time.monotonic()
    graph = new_graph_skeleton()

    graph['generated_at'] = datetime.now(timezone.utc).isoformat()
    graph['odoo'] = {
        'version': None if options.anonymize else odoo.release.version,
        'database': None if options.anonymize else env.cr.dbname,
    }
    graph['scope'] = {
        'modules': list(options.modules),
        'depth': options.depth,
        'include': {
            'wizards': options.include_wizards,
            'technical_fields': options.include_technical_fields,
            'junctions': options.show_junctions,
            'physical': options.physical,
        },
    }

    scope = resolve_scope(env, options)
    graph['modules'] = [
        {'name': m.name, 'version': m.version, 'depends': list(m.depends)}
        for m in scope.module_infos
    ]

    expansion = expand(env, scope, options)
    warnings: list[str] = list(expansion.warnings)

    abstract_models: dict[str, set[str]] = {}
    nodes: list[dict] = []
    final_node_ids: set[str] = set()

    for model_name in sorted(expansion.node_ids):
        model = _get_model(env, model_name)
        if model is None or model._abstract:
            # Abstract models never become nodes (PLAN.md, section 7.2);
            # they are only reachable as mixins on a concrete node.
            continue

        descriptor = describe_model(env, model_name)
        reached = model_name in expansion.reached_ids
        kind = classify_node_kind(model_name, descriptor, scope, reached=reached)
        if kind is None:
            continue
        if kind == 'wizard' and not options.include_wizards:
            continue

        mixins = descriptor['mixins']
        mixin_field_names: set[str] = set()
        for mixin_name in mixins:
            mixin_model = _get_model(env, mixin_name)
            if mixin_model is not None:
                mixin_field_names.update(mixin_model._fields.keys())
            abstract_models.setdefault(mixin_name, set()).add(model_name)

        fields_out = []
        for fname in sorted(descriptor['field_names']):
            if fname in MAGIC_FIELDS and not options.include_technical_fields:
                continue
            fdesc = describe_field(model, fname)
            origin = classify_field_origin(
                model_name, fname, fdesc, scope, frozenset(mixin_field_names),
            )
            defined_in_module = scope.field_owner.get((model_name, fname))
            fields_out.append(_field_output(model_name, fdesc, origin, defined_in_module))

        nodes.append({
            'id': model_name,
            'kind': kind,
            'table': descriptor['table'],
            'label': descriptor['label'],
            'module': _node_module(model_name, descriptor, scope),
            'mixins': list(mixins),
            'inherits': dict(descriptor['inherits']),
            'fields': fields_out,
            'source': [] if options.anonymize else [dict(s) for s in descriptor['source']],
        })
        final_node_ids.add(model_name)

    edges = build_edges(env, frozenset(final_node_ids), options)

    graph['nodes'] = nodes
    graph['edges'] = edges
    graph['abstract_models'] = [
        {'id': name, 'used_by': sorted(used_by)}
        for name, used_by in sorted(abstract_models.items())
    ]
    graph['warnings'] = warnings
    graph['stats'] = {
        'nodes': len(nodes),
        'edges': len(edges),
        'abstract_models': len(abstract_models),
        'hidden_by_caps': int(expansion.truncated),
        'build_seconds': round(time.monotonic() - started, 4),
    }

    problems = validate_graph(graph)
    if problems:
        graph['warnings'].extend(f'internal contract issue: {p}' for p in problems)

    return graph
