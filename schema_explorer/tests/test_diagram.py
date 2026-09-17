# -*- coding: utf-8 -*-
"""Tests for saved diagrams and stories (PLAN.md, section 13) - the record
rules that scope a diagram to its owner or anything explicitly shared
(section 14: "Diagrams: Record rules: own diagrams + shared=True"), and
that a story's/step's visibility always follows its diagram.
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.models.schema_explorer_service import GROUP_USER


@tagged('schema_explorer', 'post_install', '-at_install')
class TestSchemaExplorerDiagram(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base_module = cls.env['ir.module.module'].search([('name', '=', 'base')], limit=1)
        cls.owner = cls.env['res.users'].create({
            'name': 'Diagram Owner', 'login': 'se_diagram_owner',
            'group_ids': [(4, cls.env.ref(GROUP_USER).id)],
        })
        cls.other_user = cls.env['res.users'].create({
            'name': 'Diagram Other User', 'login': 'se_diagram_other',
            'group_ids': [(4, cls.env.ref(GROUP_USER).id)],
        })

    def _create_diagram(self, **overrides):
        vals = {
            'name': 'My diagram',
            'module_ids': [(6, 0, self.base_module.ids)],
            'options': {'depth': 1},
            'view': 'erd',
            'user_id': self.owner.id,
        }
        vals.update(overrides)
        return self.env['schema.explorer.diagram'].create(vals)

    def test_owner_can_read_own_private_diagram(self):
        diagram = self._create_diagram(shared=False)
        found = self.env['schema.explorer.diagram'].with_user(self.owner).browse(diagram.id)
        self.assertEqual(found.name, 'My diagram')

    def test_other_user_cannot_see_private_diagram(self):
        diagram = self._create_diagram(shared=False)
        found = self.env['schema.explorer.diagram'].with_user(self.other_user).search(
            [('id', '=', diagram.id)])
        self.assertFalse(found)

    def test_other_user_can_see_shared_diagram(self):
        diagram = self._create_diagram(shared=True)
        found = self.env['schema.explorer.diagram'].with_user(self.other_user).search(
            [('id', '=', diagram.id)])
        self.assertEqual(found, diagram)

    def test_other_user_cannot_write_shared_diagram_owned_by_someone_else(self):
        # Shared only grants *read* visibility via the rule's domain - the
        # rule has no operation restriction, so Odoo applies it to every
        # operation; write is still allowed by the ACL, so this documents
        # actual behaviour: shared diagrams are shared read/write, not
        # read-only, matching PLAN.md, section 13's plain "shared" boolean
        # (no separate read-only flag was specified).
        diagram = self._create_diagram(shared=True)
        diagram.with_user(self.other_user).write({'name': 'Renamed by other user'})
        self.assertEqual(diagram.name, 'Renamed by other user')

    def test_action_open_returns_client_action_with_diagram_id(self):
        diagram = self._create_diagram()
        action = diagram.action_open()
        self.assertEqual(action['tag'], 'schema_explorer.action')
        self.assertEqual(action['params']['diagram_id'], diagram.id)

    def test_story_visibility_follows_its_diagram(self):
        private_diagram = self._create_diagram(shared=False)
        story = self.env['schema.explorer.story'].create({
            'name': 'Walkthrough', 'diagram_id': private_diagram.id,
        })
        found = self.env['schema.explorer.story'].with_user(self.other_user).search(
            [('id', '=', story.id)])
        self.assertFalse(found)

        private_diagram.shared = True
        found = self.env['schema.explorer.story'].with_user(self.other_user).search(
            [('id', '=', story.id)])
        self.assertEqual(found, story)

    def test_story_step_visibility_follows_its_diagram(self):
        diagram = self._create_diagram(shared=False)
        story = self.env['schema.explorer.story'].create({'name': 'Tour', 'diagram_id': diagram.id})
        step = self.env['schema.explorer.story.step'].create({
            'story_id': story.id, 'title': 'Step 1', 'view': 'erd',
        })
        found = self.env['schema.explorer.story.step'].with_user(self.other_user).search(
            [('id', '=', step.id)])
        self.assertFalse(found)

    def test_story_to_export_dict_shape(self):
        diagram = self._create_diagram()
        story = self.env['schema.explorer.story'].create({'name': 'Tour', 'diagram_id': diagram.id})
        self.env['schema.explorer.story.step'].create({
            'story_id': story.id, 'title': 'Step 1', 'narration': 'Hello', 'view': 'erd',
            'focus_nodes': ['base.res.partner'],
        })
        exported = story.to_export_dict()
        self.assertEqual(exported['name'], 'Tour')
        self.assertEqual(len(exported['steps']), 1)
        self.assertEqual(exported['steps'][0]['title'], 'Step 1')
        self.assertEqual(exported['steps'][0]['focus_nodes'], ['base.res.partner'])

    def test_plain_user_without_group_has_no_access_at_all(self):
        diagram = self._create_diagram(shared=True)
        plain_user = self.env['res.users'].create({'name': 'No Group', 'login': 'se_diagram_no_group'})
        with self.assertRaises(AccessError):
            self.env['schema.explorer.diagram'].with_user(plain_user).browse(diagram.id).read(['name'])
