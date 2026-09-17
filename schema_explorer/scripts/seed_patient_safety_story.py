# -*- coding: utf-8 -*-
"""Seed story for the reference module, `patient_safety` (PLAN.md, section
9.7, "Seed story for patient_safety (built in Phase 4 as acceptance
content)"). Creates one shared `schema.explorer.diagram` plus its
8-step story, matching the walkthrough PLAN.md lays out.

Unlike `export.py`, this **does** write to the database - a saved diagram
and its story are the tool's own admin data (PLAN.md, section 13), not a
change to the schema being explored, so committing them is the point, not
a violation of the "strictly read-only" rule in section 2 (which is about
never touching the *inspected* database's schema/data).

Run under `odoo-bin shell` exactly like `export.py`:

    ./odoo-bin shell -c odoo.conf -d odoo_hsapp4 --no-http \\
        < custom-addons/schema_explorer/schema_explorer/scripts/seed_patient_safety_story.py

Idempotent: re-running it updates the existing diagram/story by name
rather than creating duplicates, skipping cleanly (with a message) if
`patient_safety` isn't installed on this database at all.
"""
from __future__ import annotations

import sys

try:
    env  # noqa: B018 - see export.py for why this is deliberate
except NameError:
    print(
        "SE ERROR: no `env` in scope. Run this file through `odoo-bin shell "
        "-d <database> < .../scripts/seed_patient_safety_story.py`.",
        file=sys.stderr,
    )
    raise SystemExit(2)

DIAGRAM_NAME = 'Patient Safety: Reference Demo'
STORY_NAME = 'The 70 of 320 tour'

# 9 _inherits children of patient.safety.incident (PLAN.md, section 4).
_DELEGATED_INCIDENT_TYPES = [
    'patient.safety.fall.incident',
    'patient.safety.medication.incident',
    'patient.safety.adverse.drug.reaction',
    'patient.safety.unsafe.behaviour',
    'patient.safety.laboratory.incident',
    'patient.safety.medical.device.incident',
    'patient.safety.hazard.risk',
    'patient.safety.public.relative.incident',
    'patient.safety.body.fluid.incident',
]

# Building -> floor -> room -> location, all _check_company_auto
# (PLAN.md, section 4 and section 9.7, step 5).
_LOCATION_CHAIN = [
    'patient.safety.building',
    'patient.safety.floor',
    'patient.safety.room',
    'patient.safety.location',
]

# Investigation tools (PLAN.md, section 9.7, step 8): fishbone, bowtie,
# 5-why, SBAR.
_INVESTIGATION_TOOLS = [
    'patient.safety.fishbone.cause',
    'patient.safety.fishbone.why',
    'patient.safety.bowtie.barrier',
    'patient.safety.five.why',
    'patient.safety.sbar',
]

_STEPS = [
    {
        'title': '70 of 320',
        'narration': (
            'This canvas shows 70 of the 320 tables in this database. '
            'Everything else is Odoo core, unrelated to patient safety.'
        ),
        'view': 'erd', 'focus_nodes': [],
    },
    {
        'title': 'The incident hub',
        'narration': (
            'patient.safety.incident is the center of the module: every '
            'specific incident type and most of the workflow hangs off it.'
        ),
        'view': 'erd', 'focus_nodes': ['patient.safety.incident'],
    },
    {
        'title': 'Delegation',
        'narration': (
            'These 9 incident types each _inherits patient.safety.incident. '
            'Most of their data is not in their own table at all - it lives '
            'in the parent row they delegate to.'
        ),
        'view': 'erd', 'focus_nodes': ['patient.safety.incident'] + _DELEGATED_INCIDENT_TYPES,
    },
    {
        'title': 'Where the workflow lives',
        'narration': (
            'patient.safety.workflow.mixin has no table of its own - open '
            "the incident node's inspector and look at its mixin badges to "
            'see it and the chatter/activity mixins it in turn inherits.'
        ),
        'view': 'erd', 'focus_nodes': ['patient.safety.incident'],
        'inspector_section': 'mixins',
    },
    {
        'title': 'Locations',
        'narration': (
            'building -> floor -> room -> location: every step of this '
            'chain is company-checked, so a location can never be assigned '
            'to the wrong company by accident.'
        ),
        'view': 'erd', 'focus_nodes': _LOCATION_CHAIN,
    },
    {
        'title': 'Multi-company',
        'narration': (
            'Green-bordered nodes carry their own company_id or inherit one; '
            'grey nodes are shared classification data visible to every '
            'company. The inspector translates each record rule into plain '
            'English.'
        ),
        'view': 'company', 'focus_nodes': ['patient.safety.incident', 'patient.safety.building'],
    },
    {
        'title': 'Security',
        'narration': (
            'The access matrix and record rules for every model in scope, '
            'read straight from ir.model.access and ir.rule - nothing here '
            'is hand-maintained documentation that can drift from reality.'
        ),
        'view': 'security', 'focus_nodes': ['patient.safety.incident'],
    },
    {
        'title': 'Investigation tools',
        'narration': (
            'Fishbone (cause and why), bow-tie barriers, 5-why and SBAR: '
            'the structured investigation methods a safety team fills in '
            'once an incident is reported.'
        ),
        'view': 'erd', 'focus_nodes': _INVESTIGATION_TOOLS,
    },
]


def main() -> int:
    module = env['ir.module.module'].sudo().search([('name', '=', 'patient_safety')], limit=1)
    if not module or module.state != 'installed':
        print(
            "SE: 'patient_safety' is not installed on this database - "
            "skipping the seed story (PLAN.md, section 16.3's acceptance "
            "tests skip the same way).",
            file=sys.stderr,
        )
        return 0

    Diagram = env['schema.explorer.diagram']
    diagram = Diagram.search([('name', '=', DIAGRAM_NAME)], limit=1)
    diagram_vals = {
        'module_ids': [(6, 0, module.ids)],
        'options': {'depth': 1, 'include_wizards': False, 'include_technical_fields': False},
        'view': 'erd',
        'shared': True,
    }
    if diagram:
        diagram.write(diagram_vals)
        print(f'SE: updated existing diagram {diagram.id!r}', file=sys.stderr)
    else:
        diagram = Diagram.create({**diagram_vals, 'name': DIAGRAM_NAME})
        print(f'SE: created diagram {diagram.id!r}', file=sys.stderr)

    Story = env['schema.explorer.story']
    story = Story.search([('diagram_id', '=', diagram.id), ('name', '=', STORY_NAME)], limit=1)
    if story:
        story.step_ids.unlink()
    else:
        story = Story.create({'name': STORY_NAME, 'diagram_id': diagram.id})

    Step = env['schema.explorer.story.step']
    for i, step in enumerate(_STEPS):
        Step.create({
            'story_id': story.id,
            'sequence': (i + 1) * 10,
            'title': step['title'],
            'narration': step['narration'],
            'view': step['view'],
            'focus_nodes': step['focus_nodes'],
            'highlight_edges': [],
            'camera': {},
            'inspector_section': step.get('inspector_section'),
        })

    env.cr.commit()
    print(f'SE: wrote {len(_STEPS)} steps to story {story.id!r} on diagram {diagram.id!r}', file=sys.stderr)
    return 0


sys.exit(main())
