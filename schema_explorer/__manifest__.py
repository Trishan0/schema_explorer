# -*- coding: utf-8 -*-
{
    'name': 'Schema Explorer',
    'version': '19.0.2.0.0',
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

Phase 1 adds the in-app ERD/Models view: a menu, a "View Schema" button on
the module form, and an OWL client action rendering the graph on a
Cytoscape.js canvas with a sidebar, an inspector panel and a legend.
Phase 0's portable core pipeline (``core/``) and shell export script are
unchanged and still run with no server at all. See ``PLAN.md`` in the
repository root for the full roadmap.
    """,
    'author': 'Trishan',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/schema_explorer_groups.xml',
        'views/schema_explorer_action.xml',
        'views/ir_module_module_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'schema_explorer/static/src/renderer/*.js',
            'schema_explorer/static/src/owl/schema_explorer_action.js',
            'schema_explorer/static/src/owl/schema_explorer_action.xml',
            'schema_explorer/static/src/owl/schema_explorer_action.scss',
        ],
        # Lazily loaded only when the client action actually opens (PLAN.md,
        # section 10) - Cytoscape is ~450KB and most backend sessions will
        # never touch Schema Explorer in a given day.
        'schema_explorer.assets_canvas': [
            'schema_explorer/static/lib/cytoscape/3.34.3/cytoscape.min.js',
            'schema_explorer/static/lib/cytoscape-dagre/4.0.1/cytoscape-dagre.js',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
