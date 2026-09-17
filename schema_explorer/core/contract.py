# -*- coding: utf-8 -*-
"""The Schema Explorer graph contract (PLAN.md, section 6).

This is the boundary between the portable core pipeline and every renderer
(in-app OWL view, standalone HTML export, Mermaid, DBML). Once frozen at the
end of Phase 0, changes must only *add* keys; anything that removes or
repurposes a key bumps :data:`SCHEMA_VERSION`.

Only stdlib is used here on purpose - this module must be importable without
an Odoo environment (e.g. for a client-side or CI validation script).
"""
from __future__ import annotations

SCHEMA_VERSION = 1

# -- allowed enum values -----------------------------------------------------

#: Node kinds, in the order they are tested (PLAN.md, section 7.2).
NODE_KINDS = ('owned', 'extended', 'boundary', 'wizard', 'view')

#: Where a field "comes from" (PLAN.md, section 6, "Field origin values").
FIELD_ORIGINS = ('own', 'inherits', 'related', 'mixin', 'extension', 'magic')

#: Edge kinds drawn on the canvas (PLAN.md, section 6).
EDGE_KINDS = ('many2one', 'one2many', 'many2many', 'inherits', 'related')

#: The set of Odoo's automatic bookkeeping fields (PLAN.md, section 6).
MAGIC_FIELDS = frozenset({
    'id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'display_name',
})

# -- required shape -----------------------------------------------------------

REQUIRED_TOP_KEYS = (
    'schema_version', 'generated_at', 'odoo', 'scope', 'modules',
    'nodes', 'edges', 'abstract_models', 'stats', 'warnings',
)

REQUIRED_NODE_KEYS = (
    'id', 'kind', 'table', 'label', 'module', 'mixins', 'inherits', 'fields',
)

REQUIRED_FIELD_KEYS = (
    'name', 'type', 'label', 'store', 'required', 'index', 'origin',
)

REQUIRED_EDGE_KEYS = ('id', 'kind', 'from', 'to')


def new_graph_skeleton() -> dict:
    """Return an empty, contract-shaped graph dict ready to be filled in."""
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': None,
        'odoo': {'version': None, 'database': None},
        'scope': {'modules': [], 'depth': 0, 'include': {}},
        'modules': [],
        'nodes': [],
        'edges': [],
        'abstract_models': [],
        'company': None,
        'security': None,
        'lifecycle': None,
        'drift': [],
        'stats': {},
        'warnings': [],
    }


def validate_graph(graph: dict) -> list[str]:
    """Validate ``graph`` against the contract shape.

    Returns a list of human-readable problems; an empty list means the graph
    is well-formed. This does not validate business rules (e.g. that an edge
    endpoint is a real Odoo model) - only the shape every renderer relies on.
    """
    problems: list[str] = []

    for key in REQUIRED_TOP_KEYS:
        if key not in graph:
            problems.append(f"missing top-level key: {key!r}")
    if problems:
        # Without the basic shape, the checks below would just be noisy.
        return problems

    if graph['schema_version'] != SCHEMA_VERSION:
        problems.append(
            f"schema_version {graph['schema_version']!r} does not match "
            f"the contract's {SCHEMA_VERSION!r}"
        )

    node_ids: set[str] = set()
    for i, node in enumerate(graph['nodes']):
        for key in REQUIRED_NODE_KEYS:
            if key not in node:
                problems.append(f"nodes[{i}] missing key: {key!r}")
        node_id = node.get('id')
        if node_id is None:
            continue
        if node_id in node_ids:
            problems.append(f"duplicate node id: {node_id!r}")
        node_ids.add(node_id)

        kind = node.get('kind')
        if kind not in NODE_KINDS:
            problems.append(f"nodes[{i}] ({node_id!r}) has invalid kind: {kind!r}")

        for j, fld in enumerate(node.get('fields', [])):
            for key in REQUIRED_FIELD_KEYS:
                if key not in fld:
                    problems.append(
                        f"nodes[{i}].fields[{j}] ({node_id!r}) missing key: {key!r}"
                    )
            origin = fld.get('origin')
            if origin not in FIELD_ORIGINS:
                problems.append(
                    f"nodes[{i}].fields[{j}] ({node_id!r}.{fld.get('name')!r}) "
                    f"has invalid origin: {origin!r}"
                )

    edge_ids: set[str] = set()
    for i, edge in enumerate(graph['edges']):
        for key in REQUIRED_EDGE_KEYS:
            if key not in edge:
                problems.append(f"edges[{i}] missing key: {key!r}")
        edge_id = edge.get('id')
        if edge_id is not None:
            if edge_id in edge_ids:
                problems.append(f"duplicate edge id: {edge_id!r}")
            edge_ids.add(edge_id)

        kind = edge.get('kind')
        if kind not in EDGE_KINDS:
            problems.append(f"edges[{i}] ({edge_id!r}) has invalid kind: {kind!r}")

        # Edge endpoints should reference nodes we actually emitted, unless
        # they point at a "stub" outside the expansion cap - those are
        # recorded in stats/warnings, not as dangling edges, so this check
        # is intentionally strict.
        for end in ('from', 'to'):
            target = edge.get(end)
            if target is not None and target not in node_ids:
                problems.append(
                    f"edges[{i}] ({edge_id!r}).{end} references unknown node: {target!r}"
                )

    return problems
