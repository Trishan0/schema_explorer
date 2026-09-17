# -*- coding: utf-8 -*-
"""The "View schema" button on the module form (PLAN.md, section 9.1)."""
from __future__ import annotations

from odoo import models, _


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def action_open_schema_explorer(self):
        """Open Schema Explorer pre-scoped to this module."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'schema_explorer.action',
            'name': _('Schema Explorer: %s', self.shortdesc or self.name),
            'params': {'modules': [self.name]},
        }
