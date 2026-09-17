# -*- coding: utf-8 -*-
{
    'name': 'Schema Explorer',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Module-scoped database and ORM schema visualizer for developers and demos',
    'description': """
Schema Explorer
================
Point it at one (or a few) installed modules and see only what they own:
models, fields, relations, multi-company design and security - not the
other ~300 tables that make up the rest of an Odoo database.

Merges three sources of truth:

* the live ORM registry (fields, ``_inherits``, mixins, ``check_company``)
* module ownership metadata (``ir.model.data``, ``ir.model.relation``,
  ``ir.model.constraint``)
* the physical PostgreSQL catalog (columns, indexes, foreign keys, sizes)

Phase 0 of this module ships the portable core pipeline only
(``core/``) plus a shell export script. It has no user interface yet.
See ``PLAN.md`` in the repository root for the full roadmap.
    """,
    'author': 'Trishan',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/schema_explorer_groups.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
