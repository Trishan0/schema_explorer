# -*- coding: utf-8 -*-
"""The security analyzer (PLAN.md, section 8.3).

Batched the same way as :mod:`company` - a handful of queries total
regardless of how many nodes are in the graph, never one query per model.
Only metadata models are read (``ir.model``, ``ir.model.access``,
``ir.rule``, ``res.groups``); no business record is ever touched.
"""
from __future__ import annotations

from .rules import rules_by_model, xmlids_for

EVERYONE_LABEL = 'Everyone (no group required)'


def _access_by_model(env, node_ids: list[str]) -> tuple[dict[str, list[dict]], set[int]]:
    result: dict[str, list[dict]] = {name: [] for name in node_ids}
    referenced_group_ids: set[int] = set()
    if not node_ids:
        return result, referenced_group_ids

    ir_models = env['ir.model'].sudo().search([('model', 'in', node_ids)])
    id_to_model = {m.id: m.model for m in ir_models}
    if not id_to_model:
        return result, referenced_group_ids

    accesses = env['ir.model.access'].sudo().search([('model_id', 'in', list(id_to_model))])
    access_xmlids = xmlids_for(env, 'ir.model.access', accesses.ids)

    for acc in accesses:
        model_name = id_to_model.get(acc.model_id.id)
        if model_name is None:
            continue
        group = acc.group_id
        if group:
            referenced_group_ids.add(group.id)
        result[model_name].append({
            'xmlid': access_xmlids.get(acc.id),
            'name': acc.name,
            'group_id': group.id if group else None,
            'group_label': group.full_name if group else EVERYONE_LABEL,
            'read': acc.perm_read,
            'write': acc.perm_write,
            'create': acc.perm_create,
            'unlink': acc.perm_unlink,
        })
    return result, referenced_group_ids


def _resolve_groups(env, group_ids: set[int], field_group_xmlids: set[str]) -> list[dict]:
    """Every group referenced (by id, from ACLs/rules, or by xmlid, from
    field-level ``groups=``), plus - one hop out - whatever they each
    directly imply, so the UI has enough to draw "X implies Y" without a
    full transitive closure (PLAN.md, section 8.3: "groups tree...
    Include implied_ids")."""
    all_ids = set(group_ids)
    for xmlid in field_group_xmlids:
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec is not None and rec._name == 'res.groups':
            all_ids.add(rec.id)

    if not all_ids:
        return []

    groups = env['res.groups'].sudo().browse(all_ids).exists()
    all_ids |= set(groups.implied_ids.ids)
    groups = env['res.groups'].sudo().browse(all_ids).exists()

    xmlids = xmlids_for(env, 'res.groups', list(all_ids))
    out = []
    for g in groups:
        out.append({
            'id': g.id,
            'xmlid': xmlids.get(g.id),
            'name': g.full_name,
            'implied_ids': [xmlids[i.id] for i in g.implied_ids if i.id in xmlids],
        })
    return sorted(out, key=lambda g: g['name'] or '')


def analyze_security(env, nodes: list[dict], modules: list[str]) -> dict:
    """Build the ``security`` section of the graph (PLAN.md, section 8.3).

    ``modules`` is accepted (unused for now) for symmetry with
    :func:`schema_explorer.core.analyzers.company.analyze_company` and in
    case a later pass wants to scope groups to only those a module itself
    defines.
    """
    node_ids = [n['id'] for n in nodes]
    access, referenced_group_ids = _access_by_model(env, node_ids)
    models_without_access = sorted(name for name, rows in access.items() if not rows)

    rules = rules_by_model(env, node_ids)
    for model_rules in rules.values():
        for rule in model_rules:
            referenced_group_ids.update(rule.get('group_ids', ()))

    field_groups = []
    field_group_xmlids: set[str] = set()
    for node in nodes:
        for field in node['fields']:
            groups = field.get('groups')
            if groups:
                field_groups.append({'model': node['id'], 'field': field['name'], 'groups': groups})
                field_group_xmlids.update(groups)

    return {
        'access': access,
        'models_without_access': models_without_access,
        'rules': rules,
        'field_groups': field_groups,
        'groups': _resolve_groups(env, referenced_group_ids, field_group_xmlids),
    }
