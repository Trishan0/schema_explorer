# -*- coding: utf-8 -*-
"""The RPC surface between the OWL client and the portable core pipeline.

Everything access-sensitive lives here, in front of the pure core: the
group checks (PLAN.md, section 14) and the in-process graph cache (PLAN.md,
section 15). ``core.inspector.build_graph`` itself never checks permissions
and never caches - that would make it impossible to reuse from a plain
shell script with no request/session at all.
"""
from __future__ import annotations

from collections import OrderedDict

from odoo import api, models, _
from odoo.exceptions import AccessError, UserError

from ..core.inspector import build_graph
from ..core.options import Options

#: PLAN.md, section 15: a small module-level LRU, keyed by
#: (registry_sequence, options.cache_key()). Physical data is never cached
#: (row counts/sizes go stale and are cheap to refetch); the registry
#: sequence in the key means an install/upgrade/uninstall invalidates it
#: automatically, with no explicit invalidation hook needed.
_GRAPH_CACHE: 'OrderedDict[tuple, dict]' = OrderedDict()
_GRAPH_CACHE_MAX_SIZE = 32

GROUP_USER = 'schema_explorer.group_schema_explorer_user'
GROUP_PHYSICAL = 'schema_explorer.group_schema_explorer_physical'


class SchemaExplorerService(models.AbstractModel):
    _name = 'schema.explorer.service'
    _description = 'Schema Explorer: graph service'

    def _check_access(self) -> None:
        if not self.env.user.has_group(GROUP_USER):
            raise AccessError(_(
                "You need the 'Schema Explorer' access group to use Schema Explorer."
            ))

    @api.model
    def get_graph(self, options: dict) -> dict:
        """Build (or reuse a cached) graph for ``options`` (a plain dict
        matching :meth:`Options.from_dict`).

        Access is checked here, server-side, independently of whatever menu
        or button the client happens to render - PLAN.md, section 14: "the
        service method... check[s] it. Server-side check... not just menu
        visibility."
        """
        self._check_access()
        options = dict(options or {})

        try:
            parsed = Options.from_dict(options)
        except ValueError as exc:
            raise UserError(str(exc)) from exc

        # Physical details (row counts, sizes, drift) need the stricter
        # group; anyone without it just silently gets the non-physical view
        # rather than an error (PLAN.md, section 14: "options.physical is
        # forced to False server-side" - not rejected outright, since a
        # saved diagram or a stale UI toggle could easily carry
        # physical: true for a viewer who never asked for it).
        if parsed.physical and not self.env.user.has_group(GROUP_PHYSICAL):
            parsed = parsed.without_physical()

        if parsed.physical:
            # Never cached - row counts and sizes are meant to be current.
            return build_graph(self.env, parsed)

        cache_key = (self.env.registry.registry_sequence, parsed.cache_key())
        cached = _GRAPH_CACHE.get(cache_key)
        if cached is not None:
            _GRAPH_CACHE.move_to_end(cache_key)
            return cached

        graph = build_graph(self.env, parsed)
        _GRAPH_CACHE[cache_key] = graph
        _GRAPH_CACHE.move_to_end(cache_key)
        while len(_GRAPH_CACHE) > _GRAPH_CACHE_MAX_SIZE:
            _GRAPH_CACHE.popitem(last=False)
        return graph

    @api.model
    def get_module_choices(self, term: str = '', limit: int = 50) -> list[dict]:
        """Installed modules matching ``term``, for the module picker."""
        self._check_access()
        domain = [('state', '=', 'installed')]
        if term:
            domain = domain + ['|', ('name', 'ilike', term), ('shortdesc', 'ilike', term)]
        modules = self.env['ir.module.module'].sudo().search(domain, order='name', limit=limit)
        return [
            {'name': m.name, 'label': m.shortdesc or m.name}
            for m in modules
        ]

    @api.model
    def get_sample_records(self, model_name: str, limit: int = 5) -> dict:
        """A handful of real rows for the "Records" panel (PLAN.md, section
        9.5 point 8) - gated behind the stricter physical group, since even
        a handful of rows can be sensitive on a client database.

        Deliberately **never** ``sudo()``: it goes through the ORM as the
        current user, so the model's own access rights and record rules
        apply exactly as they would anywhere else in Odoo (PLAN.md, section
        14: "Never sudo() for business models").
        """
        self._check_access()
        if not self.env.user.has_group(GROUP_PHYSICAL):
            raise AccessError(_(
                "You need the 'Schema Explorer: physical details' access group "
                "to preview sample records."
            ))
        try:
            model = self.env[model_name]
        except KeyError as exc:
            raise UserError(_('Unknown model: %s', model_name)) from exc

        field_names = ['display_name']
        for name, field in model._fields.items():
            if name in field_names or len(field_names) >= 8:
                continue
            if not field.store or field.type in ('one2many', 'many2many', 'binary', 'html'):
                continue
            field_names.append(name)

        records = model.search([], limit=limit)
        return {
            'field_names': field_names,
            'records': records.read(field_names) if records else [],
            'total_count': model.search_count([]),
        }
