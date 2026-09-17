# -*- coding: utf-8 -*-
"""Markdown report export (PLAN.md, section 11) - tables of models, fields,
relations, multi-company findings, security and drift, for pasting straight
into tech docs. Reads only the already-built graph dict.
"""
from __future__ import annotations


def _check(value: bool) -> str:
    return '✓' if value else ''


def _models_section(graph: dict) -> list[str]:
    lines = ['## Models', '', '| Model | Kind | Table | Module | Fields |', '|---|---|---|---|---|']
    for node in sorted(graph['nodes'], key=lambda n: n['id']):
        lines.append(
            f"| `{node['id']}` | {node['kind']} | `{node['table'] or '-'}` | "
            f"{node.get('module') or '-'} | {len(node['fields'])} |"
        )
    return lines


def _relations_section(graph: dict) -> list[str]:
    lines = ['', '## Relations', '', '| Kind | From | Field | To | Physical |', '|---|---|---|---|---|']
    for edge in sorted(graph['edges'], key=lambda e: (e['kind'], e['from'], e.get('field') or '')):
        lines.append(
            f"| {edge['kind']} | `{edge['from']}` | {edge.get('field') or '-'} | "
            f"`{edge['to']}` | {_check(edge.get('physical', True))} |"
        )
    return lines


def _company_section(graph: dict) -> list[str]:
    company = graph.get('company')
    if not company:
        return []
    lines = ['', '## Multi-company', '', '### Company-scoped models', '',
              '| Model | Company field | Required | check_company_auto |', '|---|---|---|---|']
    for m in company['company_models']:
        lines.append(
            f"| `{m['model']}` | {m['company_field']} | {_check(m['required'])} | "
            f"{_check(m['check_company_auto'])} |"
        )
    if company['inherits_company']:
        lines += ['', '### Company-scoped via `_inherits`', '', '| Model | Via |', '|---|---|']
        for m in company['inherits_company']:
            lines.append(f"| `{m['model']}` | `{m['via']}` |")
    if company['leaks']:
        lines += ['', '### Findings', '', '| Severity | Check | From | To | Message |', '|---|---|---|---|---|']
        for leak in company['leaks']:
            lines.append(
                f"| {leak['severity']} | {leak['check']} | `{leak['from']}` | "
                f"`{leak.get('to') or '-'}` | {leak['message']} |"
            )
    return lines


def _security_section(graph: dict) -> list[str]:
    security = graph.get('security')
    if not security:
        return []
    lines = ['', '## Security', '']
    if security['models_without_access']:
        models = ', '.join(f'`{m}`' for m in security['models_without_access'])
        lines += [f'**No ACL at all (superuser only):** {models}', '']
    lines += ['| Model | Group | R | W | C | D |', '|---|---|---|---|---|---|']
    for model, rows in sorted(security['access'].items()):
        for row in rows:
            lines.append(
                f"| `{model}` | {row['group_label']} | {_check(row['read'])} | "
                f"{_check(row['write'])} | {_check(row['create'])} | {_check(row['unlink'])} |"
            )
    return lines


def _drift_section(graph: dict) -> list[str]:
    drift = graph.get('drift')
    if not drift:
        return []
    lines = ['', '## Drift (code vs. database)', '',
              '| Severity | Check | Model | Field | Table | Message |', '|---|---|---|---|---|---|']
    for item in drift:
        lines.append(
            f"| {item['severity']} | {item['check']} | `{item.get('model') or '-'}` | "
            f"{item.get('field') or '-'} | `{item.get('table') or '-'}` | {item['message']} |"
        )
    return lines


def to_markdown(graph: dict) -> str:
    modules = ', '.join(m['name'] for m in graph.get('modules', [])) or '(no modules)'
    lines = [f'# Schema Explorer report: {modules}', '']

    stats = graph.get('stats', {})
    if stats:
        summary = f"{stats.get('nodes', 0)} models shown"
        if stats.get('db_tables_total'):
            summary += f" of {stats['db_tables_total']} tables in the database"
        summary += f" · {stats.get('edges', 0)} relations · schema v{graph.get('schema_version')}"
        lines += [summary, '']

    lines += _models_section(graph)
    lines += _relations_section(graph)
    lines += _company_section(graph)
    lines += _security_section(graph)
    lines += _drift_section(graph)
    return '\n'.join(lines) + '\n'
