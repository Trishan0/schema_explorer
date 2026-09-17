# -*- coding: utf-8 -*-
"""Options controlling one graph build (PLAN.md, sections 7.3 and 15).

Kept dependency-free (stdlib only) so it can be unit-tested without an Odoo
environment and reused by the standalone export script.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

#: Models that fan out into large, mostly-irrelevant neighbourhoods once
#: expansion crosses them. They are still shown as boundary nodes, but never
#: expanded further (PLAN.md, section 7.3, "hub dampening").
DEFAULT_HUB_MODELS = frozenset({
    'res.users',
    'res.company',
    'res.partner',
    'ir.attachment',
    'mail.message',
    'mail.followers',
    'res.currency',
    'uom.uom',
})

MAX_DEPTH = 3
DEFAULT_MAX_NODES = 120


@dataclass(frozen=True)
class Options:
    """Immutable options for :func:`schema_explorer.core.inspector.build_graph`."""

    modules: tuple[str, ...]
    depth: int = 0
    include_dependencies: bool = False
    include_wizards: bool = False
    include_technical_fields: bool = False
    show_junctions: bool = True
    merge_inverse: bool = True
    physical: bool = False
    anonymize: bool = False
    max_nodes: int = DEFAULT_MAX_NODES
    hub_models: frozenset[str] = field(default_factory=lambda: DEFAULT_HUB_MODELS)

    @classmethod
    def from_dict(cls, data: dict) -> 'Options':
        """Build ``Options`` from a plain dict (e.g. env vars, RPC payload).

        Unknown keys are ignored rather than raising, so the caller (the
        OWL client or the shell script) doesn't need to filter its own
        convenience keys out first.
        """
        modules = data.get('modules') or ()
        if isinstance(modules, str):
            modules = tuple(m.strip() for m in modules.split(',') if m.strip())
        else:
            modules = tuple(modules)

        kwargs = {'modules': modules}
        for name in (
            'depth', 'include_dependencies', 'include_wizards',
            'include_technical_fields', 'show_junctions', 'merge_inverse',
            'physical', 'anonymize', 'max_nodes',
        ):
            if name in data and data[name] is not None:
                kwargs[name] = data[name]
        if data.get('hub_models') is not None:
            kwargs['hub_models'] = frozenset(data['hub_models'])

        options = cls(**kwargs)
        problems = options.validate()
        if problems:
            raise ValueError('; '.join(problems))
        return options

    def validate(self) -> list[str]:
        """Return a list of human-readable problems; empty means valid."""
        problems: list[str] = []
        if not self.modules:
            problems.append('options.modules must contain at least one module name')
        if not (0 <= self.depth <= MAX_DEPTH):
            problems.append(f'options.depth must be between 0 and {MAX_DEPTH}, got {self.depth}')
        if self.max_nodes < 1:
            problems.append(f'options.max_nodes must be >= 1, got {self.max_nodes}')
        return problems

    def without_physical(self) -> 'Options':
        """A copy with ``physical`` forced off - used for the cache key and
        for enforcing the physical-details access group server-side
        (PLAN.md, section 14)."""
        return replace(self, physical=False)

    def cache_key(self) -> tuple:
        """A hashable key covering everything that changes the *shape* of
        the graph. Physical data (row counts, sizes) is excluded because it
        is never cached (PLAN.md, section 15)."""
        return (
            tuple(sorted(self.modules)),
            self.depth,
            self.include_dependencies,
            self.include_wizards,
            self.include_technical_fields,
            self.show_junctions,
            self.merge_inverse,
            self.max_nodes,
            tuple(sorted(self.hub_models)),
        )
