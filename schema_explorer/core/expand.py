# -*- coding: utf-8 -*-
"""Depth expansion, hub dampening and the node cap (PLAN.md, section 7.3).

Depth 0 is owned + extended models only. Each additional hop follows
relational fields outward. "Hub" models (``res.users``, ``res.partner``,
...) are added as boundary nodes but never expanded further, or a depth-2
walk from almost any model would pull in a large slice of Odoo core.
"""
from __future__ import annotations

from dataclasses import dataclass

from .classify import MAGIC_FIELDS

RELATIONAL_TYPES = ('many2one', 'one2many', 'many2many')


@dataclass(frozen=True)
class ExpansionResult:
    #: every model name that should become a node
    node_ids: frozenset[str]
    #: the subset of node_ids reached only through expansion (not a seed)
    reached_ids: frozenset[str]
    #: True if max_nodes was hit before expansion finished
    truncated: bool
    warnings: tuple[str, ...]


def seed_models(scope) -> frozenset[str]:
    """Depth-0 models: owned, plus anything a scoped module adds fields to."""
    return scope.owned_models | frozenset(scope.owned_fields.keys())


def _get_model(env, model_name: str):
    try:
        return env[model_name]
    except KeyError:
        return None


def _relational_neighbors(model, options) -> set[str]:
    """Comodel names reachable from ``model``'s relational fields.

    Magic-field targets (``create_uid``/``write_uid`` -> ``res.users``) are
    excluded unless ``include_technical_fields`` is set, or every single
    node would connect to ``res.users`` twice (PLAN.md, section 7.3).
    """
    neighbors = set()
    for fname, f in model._fields.items():
        if f.type not in RELATIONAL_TYPES:
            continue
        if fname in MAGIC_FIELDS and not options.include_technical_fields:
            continue
        comodel = getattr(f, 'comodel_name', None)
        if comodel:
            neighbors.add(comodel)
    return neighbors


def expand(env, scope, options) -> ExpansionResult:
    """Breadth-first expansion from the seed models out to ``options.depth``."""
    seeds = seed_models(scope)
    node_ids: set[str] = set(seeds)
    reached: set[str] = set()
    warnings: list[str] = []
    truncated = False

    frontier = set(seeds)
    for _hop in range(options.depth):
        if truncated:
            break
        next_frontier: set[str] = set()
        for model_name in sorted(frontier):
            # Hubs are shown but never expanded from, whether or not they
            # happen to be a seed themselves - this is what keeps depth 2
            # from exploding.
            if model_name in options.hub_models:
                continue
            model = _get_model(env, model_name)
            if model is None:
                continue
            for comodel in sorted(_relational_neighbors(model, options)):
                if _get_model(env, comodel) is None:
                    continue
                if comodel in node_ids:
                    continue
                if len(node_ids) >= options.max_nodes:
                    truncated = True
                    break
                node_ids.add(comodel)
                reached.add(comodel)
                next_frontier.add(comodel)
            if truncated:
                break
        frontier = next_frontier

    if truncated:
        warnings.append(
            f"expansion stopped at max_nodes={options.max_nodes} before finishing "
            f"depth={options.depth}; some relations are not shown as nodes "
            "(their target model name is still visible on the field itself). "
            "Increase max_nodes or reduce depth to see more."
        )

    return ExpansionResult(
        node_ids=frozenset(node_ids),
        reached_ids=frozenset(reached),
        truncated=truncated,
        warnings=tuple(warnings),
    )
