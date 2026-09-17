# -*- coding: utf-8 -*-
"""Tests for the Phase 4 exporters (PLAN.md, section 11): DBML, Markdown and
the standalone HTML file. Mirrors test_mermaid.py's approach for the
pure-data exporters - a hand-crafted graph dict, no real ORM data needed -
and only reaches into the ORM for the HTML export, which needs a real
``module_path`` to inline the vendored assets from.
"""
from odoo.modules.module import get_module_path
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.exporters.dbml import to_dbml
from odoo.addons.schema_explorer.core.exporters.markdown import to_markdown
from odoo.addons.schema_explorer.core.exporters.html_standalone import render_standalone_html


def _node(model, table, fields, **overrides):
    base = {
        'id': model, 'kind': 'owned', 'table': table, 'label': table,
        'module': 'demo', 'mixins': [], 'inherits': {}, 'fields': fields,
    }
    base.update(overrides)
    return base


def _field(name, ftype, **overrides):
    base = {'name': name, 'type': ftype, 'label': name, 'target': None,
            'store': True, 'has_column': ftype not in ('one2many', 'many2many'),
            'required': False, 'index': False, 'origin': 'own'}
    base.update(overrides)
    return base


def _sample_graph():
    parent = _node('demo.parent', 'demo_parent', [
        _field('id', 'integer'),
        _field('name', 'char', required=True),
    ])
    child = _node('demo.child', 'demo_child', [
        _field('id', 'integer'),
        _field('parent_id', 'many2one', target='demo.parent', required=True, index=True),
        _field('inherited_field', 'char', origin='inherits'),
        _field('tag_ids', 'many2many', target='demo.tag'),
    ])
    tag = _node('demo.tag', 'demo_tag', [_field('id', 'integer'), _field('name', 'char')])
    edges = [
        {'id': 'e1', 'kind': 'many2one', 'from': 'demo.child', 'to': 'demo.parent',
         'field': 'parent_id', 'required': True, 'physical': True},
        {'id': 'e2', 'kind': 'many2many', 'from': 'demo.child', 'to': 'demo.tag',
         'field': 'tag_ids', 'junction': 'demo_child_tag_rel', 'column1': 'child_id',
         'column2': 'tag_id', 'physical': True},
    ]
    return {
        'schema_version': 1,
        'modules': [{'name': 'demo', 'version': '1.0', 'depends': []}],
        'nodes': [parent, child, tag],
        'edges': edges,
        'company': None,
        'security': None,
        'drift': None,
        'stats': {'nodes': 3, 'edges': 2, 'db_tables_total': 320},
    }


@tagged('schema_explorer', 'post_install', '-at_install')
class TestDBML(TransactionCase):

    def test_tables_and_columns(self):
        dbml = to_dbml(_sample_graph())
        self.assertIn('Table demo_parent {', dbml)
        self.assertIn('Table demo_child {', dbml)

    def test_inherited_field_excluded(self):
        dbml = to_dbml(_sample_graph())
        self.assertNotIn('inherited_field', dbml)

    def test_many2one_becomes_ref(self):
        dbml = to_dbml(_sample_graph())
        self.assertIn('Ref: demo_child.parent_id > demo_parent.id', dbml)

    def test_many2many_becomes_junction_table_and_refs(self):
        dbml = to_dbml(_sample_graph())
        self.assertIn('Table demo_child_tag_rel {', dbml)
        self.assertIn('Ref: demo_child_tag_rel.child_id > demo_child.id', dbml)
        self.assertIn('Ref: demo_child_tag_rel.tag_id > demo_tag.id', dbml)

    def test_many2many_attribute_row_excluded_from_owning_table(self):
        dbml = to_dbml(_sample_graph())
        table_block = dbml.split('Table demo_child {')[1].split('}')[0]
        self.assertNotIn('tag_ids', table_block)

    def test_id_is_marked_primary_key(self):
        dbml = to_dbml(_sample_graph())
        self.assertIn('primary key', dbml)

    def test_view_node_with_no_table_is_skipped(self):
        graph = _sample_graph()
        graph['nodes'].append(_node('demo.view', None, [], kind='view'))
        dbml = to_dbml(graph)
        self.assertNotIn('demo.view', dbml)


@tagged('schema_explorer', 'post_install', '-at_install')
class TestMarkdown(TransactionCase):

    def test_contains_models_and_relations_sections(self):
        md = to_markdown(_sample_graph())
        self.assertIn('## Models', md)
        self.assertIn('## Relations', md)
        self.assertIn('`demo.parent`', md)
        self.assertIn('`demo.child`', md)

    def test_stats_summary_line(self):
        md = to_markdown(_sample_graph())
        self.assertIn('320 tables in the database', md)

    def test_no_company_or_security_section_when_absent(self):
        md = to_markdown(_sample_graph())
        self.assertNotIn('## Multi-company', md)
        self.assertNotIn('## Security', md)


@tagged('schema_explorer', 'post_install', '-at_install')
class TestHtmlStandalone(TransactionCase):

    def setUp(self):
        super().setUp()
        self.module_path = get_module_path('schema_explorer')

    def test_page_is_self_contained_and_mentions_the_renderer(self):
        html = render_standalone_html(_sample_graph(), module_path=self.module_path)
        self.assertIn('<!DOCTYPE html>', html)
        self.assertIn('function createRenderer', html)
        self.assertIn('function graphToElements', html)
        self.assertIn('demo.parent', html)

    def test_no_ES_module_import_or_export_keywords_remain(self):
        # The renderer files are real ES modules on disk; the whole point of
        # inlining them into one <script> is that none of that syntax
        # survives into the final page (PLAN.md, section 11.1).
        html = render_standalone_html(_sample_graph(), module_path=self.module_path)
        script_start = html.index('<script>')
        script_body = html[script_start:]
        self.assertNotIn('\nimport ', script_body)
        self.assertNotIn('export function', script_body)
        self.assertNotIn('export const', script_body)

    def test_stories_are_embedded(self):
        stories = [{'name': 'Tour', 'steps': [{'title': 'Step one', 'narration': 'Hello', 'view': 'erd',
                                                'focus_nodes': ['demo.parent'], 'highlight_edges': [], 'camera': {}}]}]
        html = render_standalone_html(_sample_graph(), module_path=self.module_path, stories=stories)
        self.assertIn('Step one', html)
        self.assertIn('initStoryPlayer', html)

    def test_anonymized_graph_leaves_no_db_name_or_absolute_path(self):
        graph = _sample_graph()
        graph['odoo'] = {'version': None, 'database': None}
        graph['nodes'][0]['source'] = []
        html = render_standalone_html(graph, module_path=self.module_path)
        self.assertNotIn(self.env.cr.dbname, html)
        self.assertNotIn(self.module_path, html)
