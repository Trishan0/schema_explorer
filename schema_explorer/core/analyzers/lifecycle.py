# -*- coding: utf-8 -*-
"""The lifecycle analyzer (PLAN.md, section 8.4).

Finds Selection fields that look like a workflow/state field and lists
their values (via the field's own resolved selection, already on the
graph's field dicts - PLAN.md, section 6, ``registry_reader``). Transitions
are a best-effort, always-labelled *guess*: a regex scan of the model's own
source file for ``write({'state': 'x'})`` / ``self.state = 'x'`` patterns.
This is not a verified state machine - PLAN.md, section 8.4 and risk R10:
"Lifecycle transitions from regex are wrong... treated as best-effort."

Reads only static `.py` source text already known to belong to the model
(from its own ``source`` entries); never imports or executes anything.
"""
from __future__ import annotations

import os
import re

_LIFECYCLE_FIELD_RE = re.compile(r'^(state|stage|status)$|(_state|_stage|_status)$')


def _is_lifecycle_field(field: dict) -> bool:
    return field['type'] == 'selection' and bool(_LIFECYCLE_FIELD_RE.search(field['name']))


def _source_paths_for(node: dict) -> list[str]:
    """Filesystem paths for every source file the graph already attributed
    to this node (empty when the graph was built with ``anonymize=True``,
    which is fine - transitions just can't be guessed then)."""
    try:
        from odoo.modules.module import get_module_path
    except ImportError:  # pragma: no cover - only reachable outside Odoo
        return []

    paths = []
    for src in node.get('source', []):
        module_name, file_rel = src.get('module'), src.get('file')
        if not module_name or not file_rel:
            continue
        base = get_module_path(module_name, display_warning=False)
        if base:
            paths.append(os.path.join(base, file_rel))
    return paths


def _guess_transitions(source_path: str, field_name: str) -> set[str]:
    """Values this field gets set to, per a plain regex scan of one file -
    matches ``write({'state': 'done'})`` and ``self.state = 'done'`` (and
    the ``"``-quoted equivalents), nothing more sophisticated."""
    try:
        with open(source_path, encoding='utf-8') as fh:
            content = fh.read()
    except OSError:
        return set()

    name = re.escape(field_name)
    targets: set[str] = set()
    for m in re.finditer(rf"write\(\s*\{{[^}}]*['\"]{name}['\"]\s*:\s*['\"](\w+)['\"]", content):
        targets.add(m.group(1))
    for m in re.finditer(rf"\.{name}\s*=\s*['\"](\w+)['\"]", content):
        targets.add(m.group(1))
    return targets


def analyze_lifecycle(nodes: list[dict]) -> dict:
    """Build the ``lifecycle`` section of the graph (PLAN.md, section 8.4).

    Only models that actually have a state-like Selection field appear in
    the output - most nodes in a typical graph won't.
    """
    nodes_by_id = {n['id']: n for n in nodes}
    models_out = []
    for node in nodes:
        lifecycle_fields = [f for f in node['fields'] if _is_lifecycle_field(f)]
        if not lifecycle_fields:
            continue

        own_source_paths = _source_paths_for(node)
        fields_out = []
        for field in lifecycle_fields:
            source_paths = own_source_paths
            # A field borrowed through _inherits has no code of its own on
            # this model - the write({'state': ...}) calls that actually
            # move it live on the model it's delegated to (found while
            # testing against patient.safety.adverse.drug.reaction, whose
            # `state` transitions all live in patient_safety_incident.py,
            # not in this subclass's own file).
            stored_on = field.get('stored_on')
            if stored_on and stored_on in nodes_by_id:
                source_paths = own_source_paths + _source_paths_for(nodes_by_id[stored_on])

            targets: set[str] = set()
            for path in source_paths:
                targets |= _guess_transitions(path, field['name'])
            values = [v for v, _label in field.get('selection', [])]
            fields_out.append({
                'field': field['name'],
                'values': field.get('selection', []),
                # only keep guesses that are actually one of the field's
                # declared values - a regex hit on an unrelated same-named
                # field elsewhere in the file is otherwise indistinguishable.
                'transitions_guess': sorted(t for t in targets if t in values),
            })
        models_out.append({'model': node['id'], 'fields': fields_out})

    return {'models': models_out}
