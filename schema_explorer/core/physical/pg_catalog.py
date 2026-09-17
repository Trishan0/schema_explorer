# -*- coding: utf-8 -*-
"""Layer C: the physical PostgreSQL catalog (PLAN.md, sections 5.1 and 8.5).

Read-only, and every query is parameterized against a table-name list that
is itself only ever built from :mod:`schema_explorer.core.registry_reader`
output (never from anything a caller supplies directly) - PLAN.md, section
14: "Every table name is validated against registry ``_table`` values
before use."

One batched query per catalog source, for every table in scope - never one
query per table (PLAN.md, section 8.5: "always batched").
"""
from __future__ import annotations

#: `pg_constraint.contype` -> a readable kind.
_CONSTRAINT_TYPES = {
    'f': 'foreign_key',
    'u': 'unique',
    'p': 'primary_key',
    'c': 'check',
}

#: `pg_constraint.confdeltype` (the FK's ON DELETE action) -> Odoo's own
#: `ondelete` vocabulary, so a drift check can compare them directly.
_FK_ACTION_TO_ONDELETE = {
    'a': 'restrict',   # NO ACTION behaves like RESTRICT for our purposes
    'r': 'restrict',
    'c': 'cascade',
    'n': 'set null',
    'd': 'set default',
}


def _new_table_entry() -> dict:
    return {
        'exists': False,
        'is_view': False,
        'columns': {},
        'constraints': [],
        'indexes': [],
        'rows_estimate': None,
        'rows_estimate_is_exact': False,
        'total_bytes': None,
    }


def count_public_tables(env) -> int:
    """Total number of ordinary tables in the ``public`` schema.

    This is the "of 320" half of the "70 of 320 tables shown" pitch
    (PLAN.md, section 9.2) - a single aggregate count, not gated behind
    the physical group (unlike per-table row counts/sizes/drift), since it
    reveals nothing about any specific table.
    """
    env.cr.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"
    )
    return env.cr.fetchone()[0]


def fetch_physical(env, table_names: list[str]) -> dict[str, dict]:
    """Physical facts for every table in ``table_names``.

    Returns a dict keyed by table name; a table with no matching row in
    ``pg_class`` (i.e. it doesn't exist) is still present in the result
    with ``exists: False`` and everything else empty - that is itself the
    input to drift check D7 (PLAN.md, section 8.5).
    """
    tables = sorted(set(t for t in table_names if t))
    if not tables:
        return {}

    result = {t: _new_table_entry() for t in tables}
    cr = env.cr

    # -- which of these are real tables vs. SQL views vs. missing --------
    cr.execute(
        """
        SELECT c.relname, c.relkind, c.reltuples, c.oid
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY(%s)
        """,
        (tables,),
    )
    oid_by_table: dict[str, int] = {}
    for relname, relkind, reltuples, oid in cr.fetchall():
        entry = result[relname]
        entry['exists'] = True
        entry['is_view'] = relkind in ('v', 'm')  # view or materialized view
        entry['rows_estimate'] = None if reltuples is None or reltuples < 0 else int(reltuples)
        entry['rows_estimate_is_exact'] = False
        oid_by_table[relname] = oid

    if not oid_by_table:
        return result

    oids = list(oid_by_table.values())
    oid_to_table = {oid: name for name, oid in oid_by_table.items()}

    # -- sizes -------------------------------------------------------------
    cr.execute(
        "SELECT oid, pg_total_relation_size(oid) FROM pg_class WHERE oid = ANY(%s)",
        (oids,),
    )
    for oid, size in cr.fetchall():
        table = oid_to_table.get(oid)
        if table:
            result[table]['total_bytes'] = int(size) if size is not None else None

    # -- columns -------------------------------------------------------------
    cr.execute(
        """
        SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(%s)
        """,
        (tables,),
    )
    for table_name, column_name, data_type, udt_name, is_nullable, column_default in cr.fetchall():
        result[table_name]['columns'][column_name] = {
            'data_type': data_type,
            'udt_name': udt_name,
            'nullable': is_nullable == 'YES',
            'default': column_default,
        }

    # -- constraints (FK/unique/PK/check) ------------------------------------
    cr.execute(
        """
        SELECT conrelid, conname, contype, confdeltype,
               pg_get_constraintdef(oid) AS definition,
               confrelid
        FROM pg_constraint
        WHERE conrelid = ANY(%s)
        """,
        (oids,),
    )
    for conrelid, conname, contype, confdeltype, definition, confrelid in cr.fetchall():
        table = oid_to_table.get(conrelid)
        if not table:
            continue
        result[table]['constraints'].append({
            'name': conname,
            'type': _CONSTRAINT_TYPES.get(contype, contype),
            'definition': definition,
            'fk_ondelete': _FK_ACTION_TO_ONDELETE.get(confdeltype) if contype == 'f' else None,
            'fk_target_table': oid_to_table.get(confrelid) if contype == 'f' else None,
        })

    # -- indexes -------------------------------------------------------------
    cr.execute(
        """
        SELECT ix.indrelid, ic.relname AS index_name, ix.indisunique, ix.indisprimary,
               pg_get_indexdef(ix.indexrelid) AS definition
        FROM pg_index ix
        JOIN pg_class ic ON ic.oid = ix.indexrelid
        WHERE ix.indrelid = ANY(%s)
        """,
        (oids,),
    )
    for indrelid, index_name, is_unique, is_primary, definition in cr.fetchall():
        table = oid_to_table.get(indrelid)
        if not table:
            continue
        result[table]['indexes'].append({
            'name': index_name,
            'unique': bool(is_unique),
            'primary': bool(is_primary),
            'definition': definition,
        })

    return result
