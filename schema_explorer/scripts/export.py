# -*- coding: utf-8 -*-
"""Offline / CI entry point for the Schema Explorer core (PLAN.md, section 11.1).

Run under ``odoo-bin shell`` (which injects ``env`` as a global when a
script is piped via stdin - see ``odoo/cli/shell.py``, ``Shell.console``):

    ./odoo-bin shell -c odoo.conf -d odoo_hsapp4 --no-http \\
        < custom-addons/schema_explorer/schema_explorer/scripts/export.py

Configure with environment variables (all optional except ``SE_MODULES``):

    SE_MODULES       comma-separated module technical names (required)
    SE_DEPTH         0-3, default 0
    SE_FORMAT        comma-separated: json,mermaid,dbml,markdown,html (default: json,mermaid)
    SE_OUT           output path *without* extension (default: ./schema_explorer_export)
    SE_INCLUDE_WIZARDS        1/0, default 0
    SE_INCLUDE_TECHNICAL_FIELDS  1/0, default 0
    SE_SHOW_JUNCTIONS 1/0, default 1
    SE_MAX_NODES      integer, default 120
    SE_PHYSICAL       1/0, default 0 - include row counts/sizes/drift (PLAN.md, phase 2)
    SE_ANONYMIZE      1/0, default 0 - strips db name/version from the output
    SE_TIMINGS        1/0, default 0 - prints step timings to stderr

This script never writes to the database: it only reads via the ORM
(``sudo()`` limited to metadata models - see PLAN.md, section 14) and does
not call ``env.cr.commit()``.
"""
from __future__ import annotations

import os
import sys
import time

# ``env`` is injected as a global by ``odoo-bin shell`` when this file is
# piped via stdin. Referencing it directly (rather than importing it) keeps
# this script runnable exactly as documented above with no extra plumbing.
try:
    env  # noqa: B018 - deliberate: fail fast with a clear message below
except NameError:
    print(
        "SE ERROR: no `env` in scope. Run this file through `odoo-bin shell "
        "-d <database> < .../scripts/export.py`, not as a plain python script.",
        file=sys.stderr,
    )
    raise SystemExit(2)

from odoo.addons.schema_explorer.core.inspector import build_graph
from odoo.addons.schema_explorer.core.options import Options
from odoo.addons.schema_explorer.core.exporters.json_export import to_json
from odoo.addons.schema_explorer.core.exporters.mermaid import to_mermaid
from odoo.addons.schema_explorer.core.exporters.dbml import to_dbml
from odoo.addons.schema_explorer.core.exporters.markdown import to_markdown
from odoo.addons.schema_explorer.core.exporters.html_standalone import render_standalone_html


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def main() -> int:
    modules_raw = os.environ.get('SE_MODULES', '').strip()
    if not modules_raw:
        print('SE ERROR: SE_MODULES is required (comma-separated module names).', file=sys.stderr)
        return 2

    formats = [f.strip() for f in os.environ.get('SE_FORMAT', 'json,mermaid').split(',') if f.strip()]
    out_base = os.environ.get('SE_OUT', './schema_explorer_export')
    timings = _bool_env('SE_TIMINGS', False)

    options = Options.from_dict({
        'modules': modules_raw,
        'depth': _int_env('SE_DEPTH', 0),
        'include_wizards': _bool_env('SE_INCLUDE_WIZARDS', False),
        'include_technical_fields': _bool_env('SE_INCLUDE_TECHNICAL_FIELDS', False),
        'show_junctions': _bool_env('SE_SHOW_JUNCTIONS', True),
        'max_nodes': _int_env('SE_MAX_NODES', 120),
        'anonymize': _bool_env('SE_ANONYMIZE', False),
        'physical': _bool_env('SE_PHYSICAL', False),
    })

    t0 = time.monotonic()
    graph = build_graph(env, options)
    build_seconds = time.monotonic() - t0

    if timings:
        print(f'SE: build_graph took {build_seconds:.3f}s '
              f'({graph["stats"]["nodes"]} nodes, {graph["stats"]["edges"]} edges)',
              file=sys.stderr)
        for w in graph['warnings']:
            print(f'SE WARNING: {w}', file=sys.stderr)

    written = []
    if 'json' in formats:
        path = f'{out_base}.json'
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(to_json(graph))
        written.append(path)
    if 'mermaid' in formats:
        path = f'{out_base}.mmd'
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(to_mermaid(graph))
        written.append(path)
    if 'dbml' in formats:
        path = f'{out_base}.dbml'
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(to_dbml(graph))
        written.append(path)
    if 'markdown' in formats:
        path = f'{out_base}.md'
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(to_markdown(graph))
        written.append(path)
    if 'html' in formats:
        from odoo.modules.module import get_module_path
        path = f'{out_base}.html'
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(render_standalone_html(graph, module_path=get_module_path('schema_explorer')))
        written.append(path)

    for path in written:
        print(f'SE: wrote {path}', file=sys.stderr)

    # Defensive: this script must never leave a write pending. We only ever
    # read (PLAN.md, section 14, "strictly read-only"); nothing here should
    # have touched the database, but roll back regardless.
    env.cr.rollback()
    return 0


sys.exit(main())
