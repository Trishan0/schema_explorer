# -*- coding: utf-8 -*-
"""Pure unit tests for the drift checks (PLAN.md, section 8.5), against
hand-built registry/physical fixtures rather than a real database - each
check is exercised independently with a synthetic mismatch."""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.schema_explorer.core.physical.drift import compute_drift


def _node(model, table, fields, kind='owned'):
    return {'id': model, 'kind': kind, 'table': table, 'fields': fields}


def _field(name, ftype, **overrides):
    base = {
        'name': name, 'type': ftype, 'store': True,
        'has_column': ftype not in ('one2many', 'many2many'),
        'required': False, 'index': False, 'origin': 'own',
    }
    base.update(overrides)
    return base


def _physical(exists=True, is_view=False, columns=None, constraints=None, indexes=None):
    return {
        'exists': exists, 'is_view': is_view,
        'columns': columns or {}, 'constraints': constraints or [], 'indexes': indexes or [],
        'rows_estimate': None, 'total_bytes': None,
    }


def _column(udt_name='varchar', nullable=True):
    return {'data_type': udt_name, 'udt_name': udt_name, 'nullable': nullable, 'default': None}


@tagged('schema_explorer', 'post_install', '-at_install')
class TestDrift(TransactionCase):

    def _checks(self, items, code):
        return [i for i in items if i['check'] == code]

    def test_d7_missing_table_for_active_model(self):
        nodes = [_node('demo.a', 'demo_a', [])]
        items = compute_drift(nodes, {}, {})
        d7 = self._checks(items, 'D7')
        self.assertEqual(len(d7), 1)
        self.assertEqual(d7[0]['severity'], 'error')

    def test_d7_not_raised_for_boundary_kind(self):
        # a boundary node might genuinely be a view or something we don't
        # own - only owned/extended models are expected to have a table.
        nodes = [_node('demo.a', 'demo_a', [], kind='boundary')]
        items = compute_drift(nodes, {}, {})
        self.assertFalse(self._checks(items, 'D7'))

    def test_view_kind_is_skipped_entirely(self):
        nodes = [_node('demo.a', 'demo_a', [_field('missing', 'char')], kind='view')]
        physical = {'demo_a': _physical(columns={})}
        items = compute_drift(nodes, physical, {})
        self.assertEqual(items, [])

    def test_d2_stored_field_with_no_column(self):
        nodes = [_node('demo.a', 'demo_a', [_field('name', 'char')])]
        physical = {'demo_a': _physical(columns={})}
        items = compute_drift(nodes, physical, {})
        d2 = self._checks(items, 'D2')
        self.assertEqual(len(d2), 1)
        self.assertEqual(d2[0]['field'], 'name')

    def test_d2_not_raised_for_attachment_backed_binary(self):
        # has_column=False (attachment=True Binary field) must not be
        # treated as a missing column - PLAN.md, section 18 risk list.
        nodes = [_node('demo.a', 'demo_a', [_field('image', 'binary', has_column=False)])]
        physical = {'demo_a': _physical(columns={})}
        items = compute_drift(nodes, physical, {})
        self.assertFalse(self._checks(items, 'D2'))

    def test_d3_missing_index(self):
        nodes = [_node('demo.a', 'demo_a', [_field('code', 'char', index=True)])]
        physical = {'demo_a': _physical(columns={'code': _column()}, indexes=[])}
        items = compute_drift(nodes, physical, {})
        self.assertEqual(len(self._checks(items, 'D3')), 1)

    def test_d3_partial_index_on_plain_column_is_recognised(self):
        # e.g. res.partner.company_registry: a partial index with a WHERE
        # clause - a naive "first ( to last )" parse breaks on this.
        nodes = [_node('demo.a', 'demo_a', [_field('code', 'char', index=True)])]
        physical = {'demo_a': _physical(
            columns={'code': _column()},
            indexes=[{
                'name': 'demo_a__code_index', 'unique': False, 'primary': False,
                'definition': "CREATE INDEX demo_a__code_index ON public.demo_a "
                              "USING btree (code) WHERE (code IS NOT NULL)",
            }],
        )}
        items = compute_drift(nodes, physical, {})
        self.assertFalse(self._checks(items, 'D3'))

    def test_d3_expression_index_on_field_is_recognised(self):
        # e.g. res.partner.barcode: USING btree (((barcode IS NOT NULL)))
        nodes = [_node('demo.a', 'demo_a', [_field('flag', 'boolean', index=True)])]
        physical = {'demo_a': _physical(
            columns={'flag': _column()},
            indexes=[{
                'name': 'demo_a__flag_index', 'unique': False, 'primary': False,
                'definition': "CREATE INDEX demo_a__flag_index ON public.demo_a "
                              "USING btree (((flag IS NOT NULL))) WHERE (flag IS NOT NULL)",
            }],
        )}
        items = compute_drift(nodes, physical, {})
        self.assertFalse(self._checks(items, 'D3'))

    def test_d5_many2one_with_no_foreign_key(self):
        nodes = [_node('demo.a', 'demo_a', [_field('partner_id', 'many2one', target='res.partner')])]
        physical = {'demo_a': _physical(columns={'partner_id': _column('int4')}, constraints=[])}
        items = compute_drift(nodes, physical, {})
        self.assertEqual(len(self._checks(items, 'D5')), 1)

    def test_d4_ondelete_mismatch(self):
        nodes = [_node('demo.a', 'demo_a', [
            _field('partner_id', 'many2one', target='res.partner', ondelete='cascade'),
        ])]
        physical = {'demo_a': _physical(
            columns={'partner_id': _column('int4')},
            constraints=[{
                'name': 'demo_a_partner_id_fkey', 'type': 'foreign_key',
                'definition': 'FOREIGN KEY (partner_id) REFERENCES res_partner(id) ON DELETE SET NULL',
                'fk_ondelete': 'set null', 'fk_target_table': 'res_partner',
            }],
        )}
        items = compute_drift(nodes, physical, {})
        d4 = self._checks(items, 'D4')
        self.assertEqual(len(d4), 1)
        self.assertEqual(d4[0]['expected'], 'cascade')
        self.assertEqual(d4[0]['found'], 'set null')

    def test_d4_not_raised_when_ondelete_matches(self):
        nodes = [_node('demo.a', 'demo_a', [
            _field('partner_id', 'many2one', target='res.partner', ondelete='cascade'),
        ])]
        physical = {'demo_a': _physical(
            columns={'partner_id': _column('int4')},
            constraints=[{
                'name': 'demo_a_partner_id_fkey', 'type': 'foreign_key',
                'definition': 'FOREIGN KEY (partner_id) REFERENCES res_partner(id) ON DELETE CASCADE',
                'fk_ondelete': 'cascade', 'fk_target_table': 'res_partner',
            }],
        )}
        items = compute_drift(nodes, physical, {})
        self.assertFalse(self._checks(items, 'D4'))

    def test_d6_required_but_nullable(self):
        nodes = [_node('demo.a', 'demo_a', [_field('name', 'char', required=True)])]
        physical = {'demo_a': _physical(columns={'name': _column(nullable=True)})}
        items = compute_drift(nodes, physical, {})
        self.assertEqual(len(self._checks(items, 'D6')), 1)

    def test_d10_company_dependent_wrong_type(self):
        nodes = [_node('demo.a', 'demo_a', [_field('cost', 'monetary', company_dependent=True)])]
        physical = {'demo_a': _physical(columns={'cost': _column('numeric')})}
        items = compute_drift(nodes, physical, {})
        d10 = self._checks(items, 'D10')
        self.assertEqual(len(d10), 1)
        self.assertEqual(d10[0]['expected'], 'jsonb')

    def test_d10_not_raised_when_jsonb(self):
        nodes = [_node('demo.a', 'demo_a', [_field('cost', 'monetary', company_dependent=True)])]
        physical = {'demo_a': _physical(columns={'cost': _column('jsonb')})}
        items = compute_drift(nodes, physical, {})
        self.assertFalse(self._checks(items, 'D10'))

    def test_d1_orphan_column(self):
        nodes = [_node('demo.a', 'demo_a', [_field('name', 'char')])]
        physical = {'demo_a': _physical(columns={
            'name': _column(), 'leftover_field': _column(),
        })}
        items = compute_drift(nodes, physical, {})
        d1 = self._checks(items, 'D1')
        self.assertEqual(len(d1), 1)
        self.assertEqual(d1[0]['field'], 'leftover_field')

    def test_d1_ignores_magic_columns(self):
        nodes = [_node('demo.a', 'demo_a', [_field('name', 'char')])]
        physical = {'demo_a': _physical(columns={
            'name': _column(), 'id': _column('int4'), 'create_uid': _column('int4'),
            'create_date': _column('timestamp'), 'write_uid': _column('int4'),
            'write_date': _column('timestamp'),
        })}
        items = compute_drift(nodes, physical, {})
        self.assertFalse(self._checks(items, 'D1'))

    def test_d8_missing_junction_table(self):
        items = compute_drift([], {}, {'demo_a_demo_b_rel': 'demo_module'})
        d8 = self._checks(items, 'D8')
        self.assertEqual(len(d8), 1)
        self.assertEqual(d8[0]['table'], 'demo_a_demo_b_rel')

    def test_d8_not_raised_when_junction_exists(self):
        items = compute_drift([], {'demo_a_demo_b_rel': _physical(exists=True)}, {'demo_a_demo_b_rel': 'demo_module'})
        self.assertFalse(self._checks(items, 'D8'))

    def test_item_ids_are_unique(self):
        nodes = [_node(f'demo.{i}', f'demo_{i}', [_field('name', 'char')]) for i in range(5)]
        physical = {f'demo_{i}': _physical(columns={}) for i in range(5)}
        items = compute_drift(nodes, physical, {})
        ids = [i['id'] for i in items]
        self.assertEqual(len(ids), len(set(ids)))
