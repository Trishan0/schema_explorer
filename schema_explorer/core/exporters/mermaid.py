# -*- coding: utf-8 -*-
"""Mermaid ``erDiagram`` export (PLAN.md, section 11).

Near zero cost, and it is what you paste into a README or hand to someone
who would rather use a plain-text diagram than the canvas.
"""
from __future__ import annotations

_TYPE_MAP = {
    'many2one': 'FK',
    'integer': 'int',
    'float': 'float',
    'monetary': 'float',
    'boolean': 'bool',
    'date': 'date',
    'datetime': 'datetime',
    'char': 'string',
    'text': 'string',
    'html': 'string',
    'selection': 'string',
    'binary': 'binary',
    'json': 'json',
    'properties': 'json',
    'properties_definition': 'json',
    'reference': 'string',
    'many2one_reference': 'int',
}


def _sanitize_id(model_name: str) -> str:
    """Mermaid entity identifiers can't contain dots; Odoo model names always
    do. The real dotted name is kept as the entity's first attribute row."""
    return model_name.replace('.', '_')


def _attr_type(field_type: str) -> str:
    return _TYPE_MAP.get(field_type, field_type)


def _entity_block(node: dict) -> list[str]:
    lines = [f'    {_sanitize_id(node["id"])} {{']
    lines.append(f'        string _model "{node["id"]}"')
    for fld in node['fields']:
        # one2many/many2many aren't columns - they become relationship
        # lines below, not attribute rows.
        if fld['type'] in ('one2many', 'many2many'):
            continue
        # Fields borrowed through _inherits have no column on this table.
        if fld['origin'] == 'inherits':
            continue
        # many2one already renders as type "FK" - only 'id' needs its own
        # marker, or many2one rows would read "FK field_id FK".
        marker = ' PK' if fld['name'] == 'id' else ''
        lines.append(f'        {_attr_type(fld["type"])} {fld["name"]}{marker}')
    lines.append('    }')
    return lines


def to_mermaid(graph: dict) -> str:
    lines = ['erDiagram']

    for node in sorted(graph['nodes'], key=lambda n: n['id']):
        lines.extend(_entity_block(node))

    # A one2many edge is the mirror of a many2one already drawn from the
    # other side; skip it once that many2one is present, so the diagram
    # doesn't show the same relationship as two contradictory lines.
    covered_many2one = {
        (edge['from'], edge['field']) for edge in graph['edges'] if edge['kind'] == 'many2one'
    }

    for edge in sorted(graph['edges'], key=lambda e: e['id']):
        kind = edge['kind']
        src, dst = _sanitize_id(edge['from']), _sanitize_id(edge['to'])
        label = edge['field']

        if kind == 'many2one':
            near_target = '||' if edge.get('required') else 'o|'
            lines.append(f'    {dst} {near_target}--o{{ {src} : "{label}"')
        elif kind == 'one2many':
            if (edge['to'], edge.get('inverse')) in covered_many2one:
                continue
            lines.append(f'    {dst} }}o--o{{ {src} : "{label} (no column)"')
        elif kind == 'many2many':
            lines.append(f'    {src} }}o--o{{ {dst} : "{label}"')
        elif kind == 'inherits':
            lines.append(f'    {dst} ||--|| {src} : "_inherits ({label})"')
        # 'related' edges are informational only and omitted here - Mermaid
        # erDiagram has no good notation for "derived from".

    return '\n'.join(lines) + '\n'
