# -*- coding: utf-8 -*-
"""Tests for the export controller (PLAN.md, section 12:
"/schema_explorer/export/<fmt> (file download), auth='user'").

Exercises the actual HTTP route rather than calling the exporters
directly, so it also proves the group check really is enforced
server-side here too, not just in the RPC service (PLAN.md, section 14).
"""
from odoo import http
from odoo.tests.common import HttpCase, tagged

from odoo.addons.schema_explorer.models.schema_explorer_service import GROUP_USER


@tagged('schema_explorer', 'post_install', '-at_install')
class TestSchemaExplorerExportController(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.se_user = cls.env['res.users'].create({
            'name': 'Export User', 'login': 'se_export_user', 'password': 'se_export_user',
            'group_ids': [(4, cls.env.ref(GROUP_USER).id)],
        })
        cls.plain_user = cls.env['res.users'].create({
            'name': 'Export Plain User', 'login': 'se_export_plain', 'password': 'se_export_plain',
        })

    def _export(self, fmt, options=None, **kwargs):
        self.authenticate('se_export_user', 'se_export_user')
        data = {'csrf_token': http.Request.csrf_token(self), 'options': options or '{"modules": ["base"]}'}
        data.update(kwargs)
        return self.url_open(f'/schema_explorer/export/{fmt}', data=data)

    def test_json_export_returns_attachment(self):
        response = self._export('json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response.headers.get('Content-Disposition', ''))
        self.assertIn('base', response.text)

    def test_mermaid_export(self):
        response = self._export('mermaid')
        self.assertEqual(response.status_code, 200)
        self.assertIn('erDiagram', response.text)

    def test_dbml_export(self):
        response = self._export('dbml')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Table ', response.text)

    def test_markdown_export(self):
        response = self._export('markdown')
        self.assertEqual(response.status_code, 200)
        self.assertIn('## Models', response.text)

    def test_html_export_is_self_contained(self):
        response = self._export('html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('<!DOCTYPE html>', response.text)
        self.assertIn('function createRenderer', response.text)

    def test_unknown_format_is_404(self):
        response = self._export('yaml')
        self.assertEqual(response.status_code, 404)

    def test_invalid_options_json_is_400(self):
        response = self._export('json', options='not json')
        self.assertEqual(response.status_code, 400)

    def test_plain_user_without_group_is_rejected(self):
        self.authenticate('se_export_plain', 'se_export_plain')
        data = {'csrf_token': http.Request.csrf_token(self), 'options': '{"modules": ["base"]}'}
        response = self.url_open('/schema_explorer/export/json', data=data)
        self.assertEqual(response.status_code, 403)
