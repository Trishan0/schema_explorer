# -*- coding: utf-8 -*-
"""Shared, batched ``ir.rule``/xmlid lookups (PLAN.md, sections 8.2 and 8.3).

Used by both the company analyzer (its C2/C3 checks and ``rules_plain``)
and the security analyzer (its per-model rule listing), so a rule's English
translation is computed once, the same way, in both places - and so
neither one issues a query per model or per record (``get_external_id()``
issues its own query per call; the batched form here is one query for
however many ids are needed).
"""
from __future__ import annotations

from .domain_english import domain_to_english


def xmlids_for(env, model_name: str, ids: list[int]) -> dict[int, str]:
    """res_id -> ``module.name`` external id, for every id in ``ids`` that
    has one - one query total, not one per id."""
    ids = [i for i in ids if i]
    if not ids:
        return {}
    records = env['ir.model.data'].sudo().search([
        ('model', '=', model_name), ('res_id', 'in', ids),
    ])
    result: dict[int, str] = {}
    for r in records:
        # a record can in principle have more than one xmlid; keep the first.
        result.setdefault(r.res_id, f'{r.module}.{r.name}')
    return result


def rules_by_model(env, model_names: list[str]) -> dict[str, list[dict]]:
    """``ir.rule`` records for every model in ``model_names``, each with an
    English summary - batched into two queries total regardless of how
    many models are asked for."""
    model_names = list(model_names)
    result: dict[str, list[dict]] = {name: [] for name in model_names}
    if not model_names:
        return result

    ir_models = env['ir.model'].sudo().search([('model', 'in', model_names)])
    id_to_model = {m.id: m.model for m in ir_models}
    if not id_to_model:
        return result

    rules = env['ir.rule'].sudo().search([('model_id', 'in', list(id_to_model))])
    rule_xmlids = xmlids_for(env, 'ir.rule', rules.ids)

    for rule in rules:
        model_name = id_to_model.get(rule.model_id.id)
        if model_name is None:
            continue
        domain_text = rule.domain_force or ''
        result[model_name].append({
            'xmlid': rule_xmlids.get(rule.id),
            'model': model_name,
            'name': rule.name,
            'global': not bool(rule.groups),
            'group_names': rule.groups.mapped('full_name'),
            'group_ids': rule.groups.ids,
            'perm_read': rule.perm_read,
            'perm_write': rule.perm_write,
            'perm_create': rule.perm_create,
            'perm_unlink': rule.perm_unlink,
            'domain': domain_text,
            'english': domain_to_english(domain_text),
        })
    return result
