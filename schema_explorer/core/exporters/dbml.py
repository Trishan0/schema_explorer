# -*- coding: utf-8 -*-
"""DBML export (PLAN.md, section 11) - tables, refs and per-column notes
recording origin/kind, meant for a "handover" that imports cleanly into
dbdiagram.io. Reads only the already-built graph dict, exactly like
:mod:`mermaid` - never touches the ORM.
"""
from __future__ import annotations

_TYPE_MAP = {
    'integer': 'integer',
    'float': 'float',
    'monetary': 'decimal',
    'boolean': 'boolean',
    'date': 'date',
    'datetime': 'timestamp',
    'char': 'varchar',
    'text': 'text',
    'html': 'text',
    'selection': 'varchar',
    'binary': 'bytea',
    'json': 'jsonb',
    'properties': 'jsonb',
    'properties_definition': 'jsonb',
    'reference': 'varchar',
    'many2one_reference': 'integer',
    'many2one': 'integer',
}


def _sanitize_id(name: str) -> str:
    """DBML table/column identifiers can't contain dots."""
    return name.replace('.', '_')


def _dbml_type(field_type: str) -> str:
    return _TYPE_MAP.get(field_type, 'varchar')


def _column_line(field: dict) -> str | None:
    # one2many/many2many are not columns on this table (PLAN.md, section 6,
    # field origin table) - they become Refs, not fields, further down.
    if field['type'] in ('one2many', 'many2many'):
        return None
    # Borrowed through _inherits: lives on the parent's table, not this one.
    if field['origin'] == 'inherits':
        return None
    # A non-stored many2one (computed/related) has no column either.
    if field['type'] == 'many2one' and not field.get('has_column'):
        return None

    settings = []
    if field['name'] == 'id':
        settings.append('primary key')
    if field.get('required'):
        settings.append('not null')
    if field.get('index'):
        settings.append('index')

    note_bits = [f"origin: {field['origin']}"]
    if field.get('target'):
        note_bits.append(f"-> {field['target']}")
    settings.append("note: '" + '; '.join(note_bits).replace("'", "\\'") + "'")

    return f"  {field['name']} {_dbml_type(field['type'])} [{', '.join(settings)}]"


def _table_block(node: dict) -> list[str]:
    lines = [f"Table {_sanitize_id(node['table'])} {{"]
    for field in node['fields']:
        line = _column_line(field)
        if line:
            lines.append(line)
    note = f"{node['id']} ({node['kind']}"
    if node.get('module'):
        note += f", module: {node['module']}"
    note += ')'
    lines.append("  Note: '" + note.replace("'", "\\'") + "'")
    lines.append('}')
    return lines


def to_dbml(graph: dict) -> str:
    lines: list[str] = []
    table_by_model: dict[str, str] = {}

    for node in sorted(graph['nodes'], key=lambda n: n['id']):
        if not node.get('table'):
            # SQL views / models with no physical table have nothing to
            # declare as a DBML table (PLAN.md, section 7.2, kind 'view').
            continue
        table_by_model[node['id']] = node['table']
        lines.extend(_table_block(node))
        lines.append('')

    seen_junctions: set[str] = set()
    for edge in sorted(graph['edges'], key=lambda e: e['id']):
        if not edge.get('physical', True):
            continue

        if edge['kind'] == 'many2one':
            src_table = table_by_model.get(edge['from'])
            dst_table = table_by_model.get(edge['to'])
            if not src_table or not dst_table:
                continue
            lines.append(
                f"Ref: {_sanitize_id(src_table)}.{edge['field']} > {_sanitize_id(dst_table)}.id"
            )

        elif edge['kind'] == 'many2many':
            junction = edge.get('junction')
            src_table = table_by_model.get(edge['from'])
            dst_table = table_by_model.get(edge['to'])
            if not junction or not src_table or not dst_table or junction in seen_junctions:
                continue
            seen_junctions.add(junction)
            col1 = edge.get('column1') or 'id1'
            col2 = edge.get('column2') or 'id2'
            lines.append(f"Table {_sanitize_id(junction)} {{")
            lines.append(f"  {col1} integer")
            lines.append(f"  {col2} integer")
            lines.append(f"  Note: 'many2many join table for {edge['from']}.{edge['field']}'")
            lines.append('}')
            lines.append(f"Ref: {_sanitize_id(junction)}.{col1} > {_sanitize_id(src_table)}.id")
            lines.append(f"Ref: {_sanitize_id(junction)}.{col2} > {_sanitize_id(dst_table)}.id")

    return '\n'.join(lines) + '\n'
