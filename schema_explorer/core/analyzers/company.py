# -*- coding: utf-8 -*-
"""The multi-company analyzer (PLAN.md, section 8.2).

Operates on the graph's own already-built ``nodes``/``edges`` (from
:mod:`schema_explorer.core.inspector`), plus a handful of direct ``ir.rule``
lookups for the rule-in-English summaries and the C2 "not isolated" check.
No field on any business record is ever read - only metadata models
(``ir.rule``, ``ir.model``) and static module files (``hooks.py``,
``migrations/``).
"""
from __future__ import annotations

import ast
import os
import re

from .rules import rules_by_model

COMPANY_FIELD_NAMES = ('company_id', 'company_ids')


def _own_company_field(node: dict) -> dict | None:
    """The node's own (non-inherited) company field, if it has one."""
    for f in node['fields']:
        if f['name'] in COMPANY_FIELD_NAMES and f['origin'] != 'inherits':
            return f
    return None


def _inherited_company_field(node: dict) -> dict | None:
    for f in node['fields']:
        if f['name'] in COMPANY_FIELD_NAMES and f['origin'] == 'inherits':
            return f
    return None


def _mentions_company(domain_text: str) -> bool:
    return 'company_id' in (domain_text or '') or 'company_ids' in (domain_text or '')


def _detect_company_touching_hooks(modules: list[str]) -> list[dict]:
    """Static scan of ``hooks.py`` and ``migrations/**/*.py`` for
    ``company_id`` mentions (PLAN.md, section 8.2, "Hooks detection").

    File-level granularity, informational only - it never runs anything,
    just greps source text and lists the functions defined in a matching
    file so a developer knows where to look.
    """
    try:
        from odoo.modules.module import get_module_path
    except ImportError:  # pragma: no cover - only reachable outside Odoo
        return []

    results = []
    for module_name in modules:
        path = get_module_path(module_name, display_warning=False)
        if not path:
            continue
        candidates = []
        hooks_file = os.path.join(path, 'hooks.py')
        if os.path.isfile(hooks_file):
            candidates.append(hooks_file)
        migrations_dir = os.path.join(path, 'migrations')
        if os.path.isdir(migrations_dir):
            for root, _dirs, files in os.walk(migrations_dir):
                for fname in files:
                    if fname.endswith('.py'):
                        candidates.append(os.path.join(root, fname))

        for file_path in candidates:
            try:
                with open(file_path, encoding='utf-8') as fh:
                    content = fh.read()
            except OSError:
                continue
            if 'company_id' not in content and 'company_ids' not in content:
                continue
            try:
                tree = ast.parse(content)
                functions = [
                    n.name for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
            except SyntaxError:
                functions = []
            rel_file = os.path.relpath(file_path, path)
            results.append({
                'module': module_name,
                'file': rel_file.replace(os.sep, '/'),
                'functions': functions,
            })
    return results


def analyze_company(env, nodes: list[dict], edges: list[dict], modules: list[str]) -> dict:
    """Build the ``company`` section of the graph (PLAN.md, section 8.2)."""
    company_models = []
    inherits_company = []
    global_models = []
    company_dependent_fields = []
    scoped_ids: set[str] = set()

    for node in nodes:
        for f in node['fields']:
            if f.get('company_dependent'):
                company_dependent_fields.append({
                    'model': node['id'], 'field': f['name'], 'storage': 'jsonb',
                })

        own_field = _own_company_field(node)
        inherited_field = _inherited_company_field(node)

        if own_field is not None:
            scoped_ids.add(node['id'])
            company_models.append({
                'model': node['id'],
                'company_field': own_field['name'],
                'required': own_field['required'],
                'check_company_auto': bool(node.get('check_company_auto')),
                'rules': [],  # filled in below, once we know all rules
            })
        elif inherited_field is not None:
            scoped_ids.add(node['id'])
            inherits_company.append({
                'model': node['id'],
                'via': inherited_field.get('stored_on'),
            })
        else:
            global_models.append(node['id'])

    # -- check_company edges (from the edges the relations analyzer already built) --
    check_company_edges = [e['id'] for e in edges if e.get('kind') == 'many2one' and e.get('check_company')]

    # -- C1: company-scoped -> company-scoped m2o with no check_company guard --
    # -- C4: company-scoped -> global m2o (informational "shared data") --
    global_set = set(global_models)
    leaks = []
    check_company_edge_set = set(check_company_edges)
    node_check_company_auto = {n['id']: bool(n.get('check_company_auto')) for n in nodes}
    for edge in edges:
        if edge.get('kind') != 'many2one':
            continue
        if not edge.get('physical', True):
            # A non-stored many2one (e.g. mail.activity.mixin's
            # activity_user_id) has no column and so no real
            # cross-company-link risk to flag - found while testing this
            # against every mail.thread-using model in patient_safety.
            continue
        src, dst = edge['from'], edge['to']
        if src not in scoped_ids:
            continue
        if dst in scoped_ids:
            guarded = edge['id'] in check_company_edge_set or node_check_company_auto.get(src, False)
            if not guarded:
                leaks.append({
                    'severity': 'warning',
                    'check': 'C1',
                    'from': src,
                    'field': edge.get('field'),
                    'to': dst,
                    'message': (
                        f"{src}.{edge.get('field')} points at another company-scoped "
                        f"model ({dst}) without check_company - it's possible to link "
                        "records that belong to different companies."
                    ),
                })
        elif dst in global_set and edge.get('field') not in COMPANY_FIELD_NAMES:
            # A model's own company_id/company_ids pointing at res.company
            # is exactly what "company-scoped" means, not a leak - every
            # scoped model would otherwise flag itself here, drowning out
            # genuinely interesting shared-lookup-table cases like a
            # classification or category field with no company scoping.
            leaks.append({
                'severity': 'info',
                'check': 'C4',
                'from': src,
                'field': edge.get('field'),
                'to': dst,
                'message': (
                    f"{src}.{edge.get('field')} links to {dst}, which is not "
                    "company-scoped - that data is shared across every company."
                ),
            })

    # -- rules, C2 (no company-referencing rule at all) and C3 --
    rules_plain: list[dict] = []
    all_scoped_entries = {m['model']: m for m in company_models}
    rules_map = rules_by_model(env, sorted(scoped_ids))
    for model_name in sorted(scoped_ids):
        rules = rules_map.get(model_name, [])
        rules_plain.extend(rules)
        entry = all_scoped_entries.get(model_name)
        if entry is not None:
            entry['rules'] = [r['xmlid'] for r in rules if r['xmlid']]
        has_company_rule = any(_mentions_company(r['domain']) for r in rules)
        if not has_company_rule:
            leaks.append({
                'severity': 'warning',
                'check': 'C2',
                'from': model_name,
                'field': None,
                'to': None,
                'message': (
                    f"{model_name} has a company field but no record rule filters on "
                    "it - records may be visible across every company."
                ),
            })
        elif entry is not None and not entry['required'] and has_company_rule:
            leaks.append({
                'severity': 'info',
                'check': 'C3',
                'from': model_name,
                'field': entry['company_field'],
                'to': None,
                'message': (
                    f"{model_name}.{entry['company_field']} is optional, but a rule "
                    "filters on it - a record with no company set may be invisible to "
                    "everyone, or visible to everyone, depending on the rule."
                ),
            })

    return {
        'company_models': company_models,
        'inherits_company': inherits_company,
        'check_company_edges': check_company_edges,
        'company_dependent_fields': company_dependent_fields,
        'global_models': sorted(global_models),
        'leaks': leaks,
        'rules_plain': rules_plain,
        'hooks': _detect_company_touching_hooks(modules),
    }
