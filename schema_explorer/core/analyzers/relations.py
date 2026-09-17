# -*- coding: utf-8 -*-
"""The relationship analyzer (PLAN.md, section 8.1).

Builds every edge between nodes already selected by
:func:`schema_explorer.core.expand.expand`. An edge is only emitted when
*both* endpoints are already nodes - a relational field pointing outside the
current scope/depth stays visible as plain text on the field itself
(``field['target']``, from :mod:`registry_reader`), it just doesn't grow the
graph. This is what makes depth 0 show "owned + extended only" without any
special-casing here.

Note on ``one2many``/``many2one`` pairs: this module deliberately emits both
sides as separate edges (matching the frozen JSON contract, PLAN.md section
6) rather than merging them into one line. ``options.merge_inverse`` is a
*rendering* hint - a renderer can match a one2many edge's ``inverse`` field
name against a many2one edge's ``field`` name between the same two models
and draw a single line with both labels. The data always has both.
"""
from __future__ import annotations

from ..classify import MAGIC_FIELDS

RELATIONAL_TYPES = ('many2one', 'one2many', 'many2many')


def _related_target(model, field) -> str | None:
    """Best-effort target model for a ``related=`` field.

    Only resolves the simple, common case: the first hop of the related
    path is a many2one on ``model`` itself (e.g. ``related='partner_id.name'``).
    Longer or non-many2one first hops are left unresolved rather than guessed.
    """
    related = getattr(field, 'related', None)
    if not related:
        return None
    first_step = related.split('.', 1)[0]
    first_field = model._fields.get(first_step)
    if first_field is None or first_field.type != 'many2one':
        return None
    return first_field.comodel_name


def build_edges(env, node_ids: frozenset[str], options) -> list[dict]:
    """Build all edges between models in ``node_ids``.

    Returns a list of edge dicts matching the contract (PLAN.md, section 6),
    sorted deterministically and assigned sequential ids, so output is
    reproducible for tests and for diffing two exports.
    """
    edges: list[dict] = []

    for model_name in sorted(node_ids):
        model = env[model_name]

        for parent_model, delegate_field in dict(getattr(model, '_inherits', {}) or {}).items():
            if parent_model in node_ids:
                edges.append({
                    'kind': 'inherits',
                    'from': model_name,
                    'to': parent_model,
                    'field': delegate_field,
                })

        for fname, f in model._fields.items():
            if fname in MAGIC_FIELDS and not options.include_technical_fields:
                continue
            if getattr(f, 'inherited', False):
                # Borrowed through _inherits: Odoo copies every field from
                # the parent onto the child (internally as a related field
                # through the delegate column), so without this guard a
                # model with N inherited relational fields would draw N
                # near-duplicate edges to whatever those fields point at -
                # on top of the one real 'inherits' edge above. There is no
                # column for this field on the child's own table at all
                # (PLAN.md, section 6, field origin 'inherits'); the single
                # delegation edge already says "this model's data lives over
                # there".
                continue

            if f.type == 'many2one':
                target = f.comodel_name
                if target in node_ids:
                    edges.append({
                        'kind': 'many2one',
                        'from': model_name,
                        'to': target,
                        'field': fname,
                        'ondelete': getattr(f, 'ondelete', None) or None,
                        'required': bool(getattr(f, 'required', False)),
                        'check_company': bool(getattr(f, 'check_company', False)),
                    })
            elif f.type == 'one2many':
                target = f.comodel_name
                if target in node_ids:
                    edges.append({
                        'kind': 'one2many',
                        'from': model_name,
                        'to': target,
                        'field': fname,
                        'inverse': getattr(f, 'inverse_name', None),
                        # No database column backs a one2many - it is purely
                        # the reverse side of a many2one (PLAN.md, section 9.4).
                        'physical': False,
                    })
            elif f.type == 'many2many':
                target = f.comodel_name
                if target in node_ids:
                    edges.append({
                        'kind': 'many2many',
                        'from': model_name,
                        'to': target,
                        'field': fname,
                        'junction': getattr(f, 'relation', None),
                        'column1': getattr(f, 'column1', None),
                        'column2': getattr(f, 'column2', None),
                    })
            elif getattr(f, 'related', None):
                target = _related_target(model, f)
                if target and target in node_ids and target != model_name:
                    edges.append({
                        'kind': 'related',
                        'from': model_name,
                        'to': target,
                        'field': fname,
                        'related_path': f.related,
                    })

    edges.sort(key=lambda e: (e['kind'], e['from'], e['field'], e['to']))
    for i, edge in enumerate(edges, start=1):
        edge['id'] = f'e{i}'
    return edges
