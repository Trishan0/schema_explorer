# -*- coding: utf-8 -*-
"""Code-vs-database drift checks (PLAN.md, section 8.5).

Compares what the registry expects (from the already-built graph nodes)
against what :mod:`pg_catalog` found. Nothing here executes anything or
touches record data - only structural comparison of two already-fetched
metadata dicts.

D9 (orphan tables matching an owned-model prefix with no model/relation at
all) is **not implemented yet** - it needs a wildcard scan of every table in
the database for each module's table prefix, which is a different shape of
query (and a different risk of false positives from unrelated modules that
happen to share a prefix) than the other nine checks here. Deferred to a
later pass; PLAN.md section 18 tracks it.
"""
from __future__ import annotations

import re

#: fields whose expected Postgres column type is always jsonb, if they had
#: an ordinary type mapping otherwise (PLAN.md, section 18, risk R6).
_COMPANY_DEPENDENT_EXPECTED_UDT = 'jsonb'

_USING_METHOD_RE = re.compile(r'USING\s+\w+\s*\(')


def _first_balanced_group(text: str, open_paren_end: int) -> str:
    """The text inside the first balanced ``(...)`` group starting right
    after ``open_paren_end`` (the position just past its opening paren).

    A plain ``rindex(')')``/``index(')')`` pair breaks on Postgres index
    definitions the moment there's a ``WHERE`` clause (partial index) or an
    expression index, both of which add parens of their own - found while
    testing D3 against ``res.partner.barcode``/``company_registry`` and
    ``res.company.alias_domain_id``, all three genuinely indexed, but as
    partial/expression indexes that a naive "first ( to last )" span
    mis-parsed as not matching.
    """
    depth = 1
    i = open_paren_end
    while i < len(text) and depth > 0:
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
        i += 1
    return text[open_paren_end:i - 1]


def _index_column_text(definition: str) -> str:
    """Raw text of an index's column/expression list, e.g. for
    ``... USING btree (((barcode IS NOT NULL))) WHERE (barcode IS NOT NULL)``
    this returns ``((barcode IS NOT NULL))`` - a field name is considered
    "indexed" if it appears as a whole word anywhere in this text, which
    covers both a plain column and an expression index that references it.
    """
    match = _USING_METHOD_RE.search(definition)
    if not match:
        return ''
    return _first_balanced_group(definition, match.end())


def _fk_column_text(definition: str) -> str:
    """Column list text of a ``FOREIGN KEY (...)`` constraint definition."""
    match = re.search(r'FOREIGN KEY\s*\(', definition)
    if not match:
        return ''
    return _first_balanced_group(definition, match.end())


def compute_drift(
    nodes: list[dict],
    physical: dict[str, dict],
    owned_relations: dict[str, str],
) -> list[dict]:
    """Build the ``drift`` list (PLAN.md, section 8.5).

    Item ids are assigned once at the end (rather than while appending) so
    building the list needs no shared mutable counter.
    """
    items: list[dict] = []

    for node in nodes:
        table = node.get('table')
        if not table:
            continue
        phys = physical.get(table)

        # D7: owned/extended model, but the table itself is missing.
        if phys is None or not phys['exists']:
            if node['kind'] in ('owned', 'extended'):
                items.append({
                    'severity': 'error', 'check': 'D7',
                    'model': node['id'], 'table': table, 'field': None,
                    'expected': f'table {table!r} to exist', 'found': 'missing',
                    'message': f"{node['id']} is an active model, but its table {table!r} does not exist.",
                })
            continue

        # A SQL view (`_auto=False`/`_table_query`) has no real columns in
        # the sense these checks care about - skip it (PLAN.md, R5).
        if node['kind'] == 'view' or phys['is_view']:
            continue

        columns = phys['columns']
        index_texts = [_index_column_text(idx['definition']) for idx in phys['indexes']]

        def _is_indexed(field_name: str, _texts=index_texts) -> bool:
            pattern = re.compile(rf'\b{re.escape(field_name)}\b')
            return any(pattern.search(text) for text in _texts)

        fk_by_column = {}
        for c in phys['constraints']:
            if c['type'] != 'foreign_key':
                continue
            column_text = _fk_column_text(c['definition'])
            # a plain (non-composite) FK's column list is just the one
            # identifier - composite FKs are rare enough in Odoo that we
            # only match the simple case, matching one column exactly.
            column_name = column_text.strip().strip('"')
            if column_name and ',' not in column_name:
                fk_by_column[column_name] = c

        registry_field_names = set()
        for field in node['fields']:
            fname = field['name']
            # A field with no real column at all - o2m/m2m are relationship
            # lines, not columns; an inherited field's data lives on the
            # parent's table, not this one.
            if field['type'] in ('one2many', 'many2many'):
                continue
            if field['origin'] == 'inherits':
                continue
            registry_field_names.add(fname)

            column = columns.get(fname)

            # D2: registry expects a stored column, but it isn't there.
            # `store` alone isn't enough - a Binary field defaults to
            # `attachment=True` (stored as ir.attachment, not a column)
            # while still being `store=True`; `has_column` already accounts
            # for that (PLAN.md, section 18 risk list; found while testing
            # against patient_safety/res.partner's image fields).
            if not field.get('has_column'):
                continue
            if column is None:
                items.append({
                    'severity': 'error', 'check': 'D2',
                    'model': node['id'], 'table': table, 'field': fname,
                    'expected': 'a column', 'found': 'no column',
                    'message': f"{node['id']}.{fname} is stored, but {table!r} has no {fname!r} column.",
                })
                continue

            # D3: index=True but no matching index.
            if field.get('index') and not _is_indexed(fname):
                items.append({
                    'severity': 'warning', 'check': 'D3',
                    'model': node['id'], 'table': table, 'field': fname,
                    'expected': 'an index', 'found': 'no index',
                    'message': f"{node['id']}.{fname} is declared index=True, but no index on {table}.{fname} was found.",
                })

            # D6: required=True but the column allows NULL.
            if field.get('required') and column['nullable']:
                items.append({
                    'severity': 'info', 'check': 'D6',
                    'model': node['id'], 'table': table, 'field': fname,
                    'expected': 'NOT NULL', 'found': 'nullable',
                    'message': (
                        f"{node['id']}.{fname} is required, but the column still allows NULL "
                        "(Odoo can't always backfill NOT NULL on an existing table)."
                    ),
                })

            # D10: company_dependent fields must be jsonb.
            if field.get('company_dependent') and column['udt_name'] != _COMPANY_DEPENDENT_EXPECTED_UDT:
                items.append({
                    'severity': 'warning', 'check': 'D10',
                    'model': node['id'], 'table': table, 'field': fname,
                    'expected': _COMPANY_DEPENDENT_EXPECTED_UDT, 'found': column['udt_name'],
                    'message': (
                        f"{node['id']}.{fname} is company_dependent, which Odoo stores as "
                        f"jsonb, but the column is {column['udt_name']!r}."
                    ),
                })

            if field['type'] == 'many2one':
                fk = fk_by_column.get(fname)
                # D5: many2one stored, but no FK constraint at all.
                if fk is None:
                    items.append({
                        'severity': 'warning', 'check': 'D5',
                        'model': node['id'], 'table': table, 'field': fname,
                        'expected': 'a foreign key constraint', 'found': 'none',
                        'message': f"{node['id']}.{fname} is a many2one, but {table}.{fname} has no foreign key constraint.",
                    })
                else:
                    # D4: ondelete doesn't match the real FK action.
                    expected_ondelete = field.get('ondelete') or 'set null'
                    if fk['fk_ondelete'] and fk['fk_ondelete'] != expected_ondelete:
                        items.append({
                            'severity': 'warning', 'check': 'D4',
                            'model': node['id'], 'table': table, 'field': fname,
                            'expected': expected_ondelete, 'found': fk['fk_ondelete'],
                            'message': (
                                f"{node['id']}.{fname} declares ondelete={expected_ondelete!r}, "
                                f"but the database foreign key is ON DELETE {fk['fk_ondelete'].upper()}."
                            ),
                        })

        # D1: a column exists that no stored field in the registry claims.
        # Odoo's own bookkeeping columns are expected and excluded.
        magic_columns = {'id', 'create_uid', 'create_date', 'write_uid', 'write_date'}
        for column_name in columns:
            if column_name in registry_field_names or column_name in magic_columns:
                continue
            items.append({
                'severity': 'warning', 'check': 'D1',
                'model': node['id'], 'table': table, 'field': column_name,
                'expected': 'no column (field removed from code, or never added)',
                'found': f'column {column_name!r} exists',
                'message': (
                    f"{table} has a column {column_name!r} that no field on {node['id']} "
                    "claims - likely left over from a field that was removed from the code."
                ),
            })

    # D8: an m2m relation this scope owns, but the join table is missing.
    for relation_table, module_name in owned_relations.items():
        phys = physical.get(relation_table)
        if phys is None or not phys['exists']:
            items.append({
                'severity': 'error', 'check': 'D8',
                'model': None, 'table': relation_table, 'field': None,
                'expected': f'join table {relation_table!r} to exist', 'found': 'missing',
                'message': (
                    f"{module_name} owns the many2many relation {relation_table!r} "
                    "(ir.model.relation), but that table does not exist."
                ),
            })

    for i, item in enumerate(items, start=1):
        item['id'] = f'd{i}'

    return items
