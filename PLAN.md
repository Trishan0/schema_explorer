# Schema Explorer — Implementation Plan

> A module-scoped database and ORM schema visualizer for Odoo 19.
> Point it at **one module**. See **only that module's** tables, relationships, multi-company design and security, without the other ~300 core tables.

| | |
|---|---|
| **Status** | Planning, nothing built yet |
| **Target Odoo** | 19.0 |
| **Technical name** | `schema_explorer` (proposed) |
| **License** | LGPL-3 |
| **Reference module** | `patient_safety` (`crede_psls_odoo`) |
| **Reference database** | `odoo_hsapp4` |
| **Plan date** | 2026-09-17 |

---

## Contents

1. [Problem](#1-problem)
2. [Goals and non-goals](#2-goals-and-non-goals)
3. [Decisions already made](#3-decisions-already-made)
4. [Reference module profile: patient_safety](#4-reference-module-profile-patient_safety)
5. [Architecture](#5-architecture)
6. [The graph contract (JSON v1)](#6-the-graph-contract-json-v1)
7. [Classification rules](#7-classification-rules)
8. [Analyzers](#8-analyzers)
9. [User interface](#9-user-interface)
10. [Rendering and libraries](#10-rendering-and-libraries)
11. [Exports and offline mode](#11-exports-and-offline-mode)
12. [Module structure](#12-module-structure)
13. [Stored models](#13-stored-models)
14. [Security of the tool itself](#14-security-of-the-tool-itself)
15. [Performance and caching](#15-performance-and-caching)
16. [Testing strategy](#16-testing-strategy)
17. [Phased delivery](#17-phased-delivery)
18. [Risks and edge cases](#18-risks-and-edge-cases)
19. [Open questions](#19-open-questions)
20. [Future ideas](#20-future-ideas)

---

## 1. Problem

Generic database tools like pgAdmin, DBeaver and the VS Code PostgreSQL extensions show an Odoo database as a flat list of 300–400 tables. That causes three problems:

- **No module scoping.** They can't tell which tables belong to the module you want to explain. People new to Odoo get lost.
- **No ORM meaning.** They only see what Postgres stores. They can't show that a `one2many` has no column behind it, that an `_inherits` child keeps most of its data in the parent table, that a field is computed or related, or that a model is an abstract mixin with no table.
- **No Odoo architecture.** Multi-company isolation, record rules, access rights and `check_company` checks all live in Odoo's metadata, not in the SQL schema.

Odoo already records all of this in its registry and in `ir.model.data`, `ir.model.relation` and `ir.model.constraint`. Those last two record **which module created each object**. No external tool reads them. This module will.

## 2. Goals and non-goals

### Goals

- **G1: Scope.** Select one or more modules and see only what they own, plus a controlled number of hops outward.
- **G2: Truth.** Merge three sources: ORM registry, module ownership, and the physical Postgres catalog.
- **G3: Teach.** Every visual style (node kind, line style, badge) has a plain-language legend entry, written for someone who has never seen Odoo.
- **G4: Demo.** Presentation mode with scripted walkthroughs ("stories").
- **G5: Portable.** The same graph can be exported as a standalone HTML file that opens with no Odoo server.
- **G6: Diagnose.** Report differences between what the ORM expects and what exists in Postgres ("drift").

### Non-goals

- Not a database editor. **Strictly read-only.** No DDL, no data edits.
- Not a replacement for Odoo Studio or the Technical → Models menu.
- Not a general Postgres tool. Tables no Odoo model knows about are only reported as drift, never modelled.
- No reverse engineering of Python business logic (compute bodies, onchanges). Only dependencies are shown.

## 3. Decisions already made

| # | Decision | Consequence |
|---|---|---|
| D1 | **The core must be portable.** | `schema_inspector` is a pure function `(env, options) → dict`, with no `request`/`http`/web client dependency. It works under `odoo-bin shell`. |
| D2 | **Access through a dedicated group** (`group_schema_explorer_user`), not `base.group_system`. | Developers and consultants can use it without Settings access. Physical and data-level details sit behind a stricter sub-group. |
| D3 | **Reference module: `patient_safety`.** | All acceptance criteria are measured against it (section 4). |
| D4 | **Three data layers:** registry + ownership + pg_catalog. | See section 5. |
| D5 | **Canvas: Cytoscape.js** in an OWL 2 client action. | See section 10. |
| D6 | **The graph JSON is versioned** (`schema_version`). | Exported files keep working as the module changes. |

## 4. Reference module profile: patient_safety

Measured on 2026-09-17 from source and from `odoo_hsapp4`.

| Metric | Value | Source |
|---|---|---|
| Tables in whole DB | **320** | `pg_tables` |
| Models owned | **54** | `ir_model_data` (`module='patient_safety'`, `model='ir.model'`) |
| M2M join tables owned | **13** | `ir_model_relation` |
| DB constraints owned | **192** | `ir_model_constraint` (FK + unique + check) |
| Relational fields | 73 m2o / 17 o2m / 15 m2m | source grep |
| Record rules | 48 (+2 menu rules) | `security/*.xml` |
| Python LOC (models) | ~6.5k | `wc -l` |
| Depends on | `base, mail, web, hr, auth_signup, custom_barcode_hs` | manifest |

**Structures the tool must handle correctly:**

| Structure | Where | What the tool must do |
|---|---|---|
| **9 `_inherits` children** of `patient.safety.incident` (fall, medication, adverse drug reaction, unsafe behaviour, laboratory, medical device, hazard risk, public relative, body fluid) | `patient_safety_specific_incidents.py` | Draw a delegation line. Show borrowed fields greyed out, with the parent table they're stored in. **This is the main demo story.** |
| **Abstract mixin** `patient.safety.workflow.mixin` (itself inherits `mail.thread`, `mail.activity.mixin`) | same file | No node. Show as a badge, with mixin-of-mixin resolved. |
| **AbstractModel** `patient.scan.provider` | `patient_scan_provider.py` | No node. List under "Abstract models" in the sidebar. |
| **3 TransientModels** (wizards) | `wizard/` | "Wizard" node kind, hidden by default. |
| **Extensions of core models**: `res.company`, `res.users`, `res.groups`, `res.partner` | `res_*.py` | "Extended" node, showing only fields this module adds. |
| **Same-module extension** of `patient.safety.incident` | `patient_safety_incident_inherit.py` | Merge into the owned node. **Not** shown as "extended". |
| **Multi-company**: `_check_company_auto` on building, floor, room, location, unit, incident; `check_company=True` fields; `company_id` on `res.groups` | several | Multi-company view (section 8.2). |
| **Hook** `_backfill_incident_company` (post-init / post-migrate) | `hooks.py` | Detect and note as "data migration touches `company_id`" (informational only). |
| **External relation targets** | — | `res.users` (16), `res.company` (13), `ir.attachment` (3), `res.partner`, `hr.employee` | These become boundary nodes. |

**Cross-database note:** other local databases with the module installed have 53–61 `patient%` tables and 54–57 owned models. The cause is **module version differences** (one DB is "to upgrade"), not leftover tables. This motivates the database-compare idea in section 20.

## 5. Architecture

### 5.1 Data layers

| Layer | Source | Provides | Authority |
|---|---|---|---|
| **A: Registry** | `env.registry`, `Model._fields` | Field objects, `_inherits`, `_abstract`, `_transient`, `_auto`, `_table`, `_table_query`, `_check_company_auto`, m2m `relation/column1/column2`, `inherited`/`inherited_field`, `related`, `compute`, `store`, `company_dependent`, `check_company`, `ondelete`, `index` | **What the code defines** |
| **B: Ownership** | `ir.model.data`, `ir.model.relation.module`, `ir.model.constraint.module`, `ir.module.module` dependencies | Which module owns each model, field, join table and constraint | **Who owns what** |
| **C: Physical** | `pg_catalog`, `information_schema` | Real column types, nullability, FK actions, indexes, check constraints, row estimates, sizes, views | **What exists in Postgres** |
| **D: Security** | `ir.model.access`, `ir.rule`, `res.groups` | Access matrix, record rule domains, group hierarchy | **Who can see what** |

> Read field metadata from the **live registry**, not `ir.model.fields`. `ir.model.fields.relation_table` / `column1` / `column2` are documented for custom m2m only. The live `Many2many` object always has `relation`, `column1` and `column2`.

### 5.2 Pipeline

```
               ┌───────────────────── schema_inspector (pure) ─────────────────────┐
options ─────► │ 1 resolve scope   → module set (+ optional dependency closure)       │
               │ 2 collect owned   → Layer B: models, fields, relations, constraints  │
               │ 3 enrich          → Layer A: registry objects for each               │
               │ 4 classify        → node kinds, field provenance (section 7)         │
               │ 5 expand          → hops outward, boundary nodes, caps               │
               │ 6 analyze         → company, security, lifecycle (section 8)         │
               │ 7 physical        → Layer C, optional, needs a flag                  │
               │ 8 drift           → A vs C checks, optional                          │
               │ 9 emit            → graph dict, schema_version = 1                   │
               └────────────────────────────────────┬────────────────────────────────┘
                                                    │
             ┌──────────────────┬───────────────────┼──────────────────┬─────────────────┐
             ▼                  ▼                   ▼                  ▼                 ▼
      OWL client action   standalone .html     Mermaid erDiagram      DBML           raw .json
      (in-app)            (offline demo)       (docs/README)          (dbdiagram.io) (tooling)
```

Rules:

- `schema_inspector` imports only `odoo.api`, `odoo.models`, `odoo.tools` and stdlib. **No `odoo.http`.**
- Each step is a separate function that takes and returns plain data, so it can be unit-tested alone.
- Renderers only consume the dict. They never call the ORM.

## 6. The graph contract (JSON v1)

This contract sits between the core and every renderer. **Freeze it at the end of Phase 0.** After that, changes only add fields; anything breaking bumps `schema_version`.

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-09-17T10:00:00Z",
  "odoo": { "version": "19.0", "database": "odoo_hsapp4" },   // database name omitted when options.anonymize
  "scope": {
    "modules": ["patient_safety"],
    "depth": 1,
    "include": { "wizards": false, "technical_fields": false, "boundary": true, "physical": true }
  },
  "modules": [
    { "name": "patient_safety", "version": "19.0.3.2.0", "depends": ["base","mail","web","hr","auth_signup","custom_barcode_hs"] }
  ],
  "nodes": [
    {
      "id": "patient.safety.fall.incident",
      "kind": "owned",                  // owned | extended | boundary | junction | wizard | view
      "table": "patient_safety_fall_incident",
      "label": "Fall Incident",         // _description
      "module": "patient_safety",
      "mixins": ["patient.safety.workflow.mixin", "mail.thread", "mail.activity.mixin"],
      "inherits": { "patient.safety.incident": "incident_id" },
      "company": { "has_company_id": false, "via_inherits": "patient.safety.incident", "check_company_auto": false },
      "fields": [
        {
          "name": "incident_id", "type": "many2one", "label": "Incident",
          "target": "patient.safety.incident",
          "store": true, "required": true, "index": true, "ondelete": "cascade",
          "origin": "own",               // own | inherits | related | mixin | extension | magic
          "defined_in_module": "patient_safety",
          "column": { "type": "int4", "nullable": false }   // physical, only when requested
        },
        {
          "name": "company_id", "type": "many2one", "target": "res.company",
          "origin": "inherits", "stored_on": "patient.safety.incident",   // borrowed through _inherits
          "store": false
        }
      ],
      "physical": { "rows_estimate": 1240, "total_bytes": 262144, "indexes": [], "constraints": [] },
      "source": { "file": "models/patient_safety_specific_incidents.py", "class": "PatientSafetyFallIncident" }
    }
  ],
  "edges": [
    { "id": "e1", "kind": "many2one", "from": "patient.safety.fall.incident", "to": "patient.safety.incident",
      "field": "incident_id", "ondelete": "cascade", "required": true, "check_company": false },
    { "id": "e2", "kind": "inherits", "from": "patient.safety.fall.incident", "to": "patient.safety.incident", "field": "incident_id" },
    { "id": "e3", "kind": "many2many", "from": "patient.safety.incident", "to": "patient.safety.contributing.factor",
      "field": "contributing_factor_ids", "junction": "patient_safety_incident_factor_rel", "column1": "incident_id", "column2": "factor_id" },
    { "id": "e4", "kind": "one2many", "from": "patient.safety.incident", "to": "patient.safety.action.plan",
      "field": "action_plan_ids", "inverse": "incident_id", "physical": false }
  ],
  "abstract_models": [ { "id": "patient.safety.workflow.mixin", "used_by": ["..."] } ],
  "company": { /* section 8.2 */ },
  "security": { /* section 8.3 */ },
  "lifecycle": { /* section 8.4 */ },
  "drift": [ /* section 8.5 */ ],
  "stats": { "db_tables_total": 320, "nodes": 70, "edges": 0, "hidden_by_caps": 0 },
  "warnings": []
}
```

(Field and relation names in the example are illustrative. Real values come from Phase 0.)

**Edge kinds:** `many2one`, `one2many`, `many2many`, `inherits`, `related` (derived-from), `compute_depends` (optional, off by default).

**Field `origin` values:**

| origin | Meaning | How to detect |
|---|---|---|
| `own` | Declared on this model by an owning module | default |
| `inherits` | Delegated from an `_inherits` parent; stored on the parent table | `field.inherited is True` → `field.inherited_field.model_name` |
| `related` | `related=` field | `field.related` |
| `mixin` | Comes from an abstract mixin | field's defining class is an `_abstract` model (walk the MRO / `ir.model.fields` xmlid) |
| `extension` | Added to a model by a different module than the model owner | field xmlid module ≠ model xmlid module |
| `magic` | `id`, `create_uid`, `create_date`, `write_uid`, `write_date`, `display_name` | fixed set; hidden unless `technical_fields` |

## 7. Classification rules

### 7.1 Scope resolution

1. Input: `modules: list[str]`, `depth: 0..3`, `include_dependencies: bool` (default false).
2. Owned models are the `ir.model.data` rows where `module ∈ scope` and `model='ir.model'` → `res_id` → `ir.model.model`.
3. Owned fields are `ir.model.data` rows where `module ∈ scope` and `model='ir.model.fields'`. This catches fields the module injects into **other** modules' models.
4. Owned junction tables come from `ir.model.relation` where `module ∈ scope`. Owned constraints come from `ir.model.constraint` where `module ∈ scope`.

### 7.2 Node kind

Checked in this order; the first match wins:

| Order | Condition | Kind | Default visible |
|---|---|---|---|
| 1 | `Model._abstract` | *(not a node; goes to `abstract_models`)* | — |
| 2 | `Model._transient` | `wizard` | hidden |
| 3 | `_auto is False` or `_table_query` set | `view` | shown |
| 4 | Model is owned by a module in scope | `owned` | shown |
| 5 | Not owned, but a module in scope adds ≥1 stored or relational field | `extended` | shown |
| 6 | Reached by an edge within `depth` hops | `boundary` | shown, collapsed |
| — | m2m relation table | `junction` (synthetic node) | shown when `show_junctions` |

**Ownership edge case:** a model is "owned" when its `model_<x>` xmlid is in a scoped module, **even if the module also extends it in a second file** (`patient_safety_incident_inherit.py`). It merges into a single `owned` node.

### 7.3 Expansion and caps

- Depth 0: owned + extended only. Edges to anything else end in a small labelled "stub" arrow and add no node.
- Depth n: breadth-first from scoped nodes, adding `boundary` nodes.
- **Hub dampening:** `res.users`, `res.company`, `res.partner`, `ir.attachment`, `mail.message`, `mail.followers`, `res.currency`, `uom.uom` are "hubs". They are added as boundary nodes, **but never expanded further**, or depth 2 would pull in half of Odoo. The hub list is configurable.
- **Hard cap:** `max_nodes` (default 120). If it's exceeded, stop expanding, set `stats.hidden_by_caps` and add a warning.
- Magic-field edges (`create_uid` / `write_uid` → `res.users`) are **excluded** from expansion and drawing unless `technical_fields` is on. Otherwise every node connects to `res.users` twice.

### 7.4 Mixin resolution

- For each node, walk the registry's `_inherit` chain recursively, keeping `_abstract` models only.
- `patient.safety.fall.incident` → `workflow.mixin` → `mail.thread`, `mail.activity.mixin` gives badges `[workflow] [chatter] [activities]`.
- Known mixins get friendly names and one-line explanations (legend). `mail.thread` gets: "adds chatter; messages stored in `mail_message`, followers in `mail_followers`. No columns on this table except `message_main_attachment_id`" (verify per version).

## 8. Analyzers

### 8.1 Relationship analyzer

- Build edges from each field in scope.
- `one2many` edges set `physical: false`. **The legend must say: "No database column. This is the reverse side of a many2one."**
- `many2many` edges carry `junction`, `column1` and `column2`. They are drawn through a junction diamond when `show_junctions`, otherwise as one edge with a table-name tooltip.
- If a `one2many` and its inverse `many2one` are both visible, render them as **one line** with both labels (option `merge_inverse`, default on). This halves visual noise.
- `inherits` edges also produce greyed, inherited field rows on the child node.

### 8.2 Multi-company analyzer

Output `company` section:

```jsonc
{
  "company_models": [
    { "model": "patient.safety.building", "company_field": "company_id", "required": true,
      "check_company_auto": true, "rules": ["rule_xmlid", "..."] }
  ],
  "inherits_company": [
    { "model": "patient.safety.fall.incident", "via": "patient.safety.incident" }
  ],
  "check_company_edges": ["e7", "e12"],
  "company_dependent_fields": [ { "model": "...", "field": "...", "storage": "jsonb" } ],
  "global_models": [ "patient.safety.category", "..." ],        // no company_id and not via inherits
  "leaks": [
    { "severity": "warning", "from": "patient.safety.location", "field": "...", "to": "patient.safety.category",
      "message": "Company-scoped model links to a global model; records are shared across companies." }
  ],
  "rules_plain": [
    { "xmlid": "...", "model": "...", "global": true, "domain": "[('company_id', 'in', company_ids)]",
      "english": "Only records whose Company is one of the companies selected in the company switcher." }
  ],
  "hooks": [ { "module": "patient_safety", "function": "_backfill_incident_company", "touches": "company_id" } ]
}
```

Rules:

- **Company-scoped model:** has a stored `company_id` or `company_ids`, **or** gets one through `_inherits`. The second case is important for the 9 incident types.
- **Global model:** none of the above.
- **Checks:**
  - **C1** A company-scoped model has an m2o to another company-scoped model **without** `check_company=True` and without `_check_company_auto` → *possible cross-company link*.
  - **C2** A company-scoped model has **no** `ir.rule` referencing `company_id`/`company_ids` → *not isolated*.
  - **C3** `company_id` is not required but a rule filters on it → *records with empty company are visible to all companies* (may be intended; informational).
  - **C4** A company-scoped model links to a global model → informational "shared data" note.
- **Domain to English:** a small translator for common patterns (`company_ids`, `company_id`, `user.id`, `user.company_id`, `user.employee_id`, `in`, `=`, `|`/`&`). Anything it can't translate is shown raw. **Never `eval` domains.** Parse them with `ast.literal_eval`, where safe, into a token tree; if that isn't possible, show the text as-is.
- **Hooks detection** is a static scan of the module's `hooks.py` and `migrations/` for `company_id` mentions. Informational only; no execution.

**Multi-company view** visuals: company-scoped nodes get a 🏢 badge. Global nodes are drawn neutral. `check_company` edges get a 🔒. C1 edges are drawn in warning colour. A side panel explains `res.company` ↔ `res.users.company_ids` ↔ the company switcher once, as a small fixed diagram.

### 8.3 Security analyzer

- **Groups:** groups defined by scoped modules, plus groups referenced by their ACLs and rules. Include `implied_ids` to show the hierarchy tree.
- **Access matrix:** model × group → `R W C D`, from `ir.model.access`. Models with **no ACL row** get flagged ("inaccessible except to superuser").
- **Record rules:** per model, global vs group rules, with plain-English domains (same translator as 8.2), per-operation flags.
- **Field groups:** fields declared with `groups=` get a 🔑 badge in the inspector.

### 8.4 Lifecycle analyzer

- For each node, find Selection fields named `state`, `stage`, `status` or matching `*_state`, plus the `selection` values.
- Where possible, find transitions by scanning `write({'state': ...})` / `self.state = ...` in the model's source file with a regex. **Always marked "static guess".** Precision is secondary; the diagram is teaching material.
- `patient.safety.workflow.mixin` is expected to hold the shared workflow; show it once and reference it from the 9 children.

### 8.5 Physical layer and drift analyzer (Layer C)

Only runs with `options.physical = true` **and** the user in `group_schema_explorer_physical`.

**Queries**, all parameterized, with table names checked against the registry first:

| Data | Source |
|---|---|
| Columns, types, nullability, defaults | `information_schema.columns` where `table_name = ANY(%s)` |
| FKs + actions | `pg_constraint` (`contype='f'`), `confdeltype` |
| Unique / check / PK | `pg_constraint` |
| Indexes | `pg_index` + `pg_class`, `pg_get_indexdef` |
| Row estimate | `pg_class.reltuples` (**estimate**, labelled as such; `COUNT(*)` is never run by default) |
| Size | `pg_total_relation_size(oid)` |
| Views | `pg_views` for `view` nodes |

**Drift checks:**

| ID | Check | Severity |
|---|---|---|
| D1 | Column exists in table, but no stored field in registry (**field removed from code but column remains**) | warning |
| D2 | Stored field in registry, but no column | error |
| D3 | `index=True` (or `models.Index`) but no matching index | warning |
| D4 | m2o `ondelete` differs from the FK's `confdeltype` | warning |
| D5 | m2o stored, but no FK constraint at all | warning |
| D6 | `required=True` but column nullable | info (Odoo can't always add NOT NULL on existing data) |
| D7 | Owned model in `ir_model` but table missing | error |
| D8 | `ir_model_relation` row but junction table missing | error |
| D9 | Table name matches an owned-model prefix but has no model/relation (orphan) | info |
| D10 | Column type differs from the field's expected column type (e.g. `company_dependent` should be `jsonb`) | warning |

Each drift item has an id, severity, model, field or table, what was expected, what was found, and a one-line explanation.

## 9. User interface

### 9.1 Entry points

- Menu: **Settings → Technical → Schema Explorer** (visible to `group_schema_explorer_user`), plus a top-level app menu when installed with `application=True`.
- A **"View schema"** button on the `ir.module.module` form opens the explorer scoped to that module.
- A **saved diagram** record opens the explorer with stored options, layout and story.

### 9.2 Layout

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ [Module ▾ patient_safety]  View: (ERD)(Models)(Company)(Security)(Lifecycle)(Physical)  │
│ Depth [0|1|2]  🔍 search      Save · Export ▾ · ▶ Present                                │
├───────────────┬──────────────────────────────────────────────────────────┬───────────────┤
│ SIDEBAR       │                         CANVAS                           │ INSPECTOR     │
│               │                                                          │               │
│ Models (54)   │    ┌────────────┐            ┌─────────────────────┐     │ Fall Incident │
│ ☑ incident    │    │ building   │◄───────────│ incident   🏢 💬     │     │ patient_safety│
│ ☑ fall        │    └────────────┘  m2o       └─────────▲───────────┘     │ _fall_incident│
│ ☐ wizards (3) │                                        ║ _inherits       │               │
│               │                              ┌─────────╨───────────┐     │ Fields        │
│ Toggles       │                              │ fall.incident 🔁     │     │  own: 14      │
│ ☑ junctions   │                              └─────────────────────┘     │  inherited: 62│
│ ☐ tech fields │                                                          │ Rules (2)     │
│ ☑ merge o2m   │                                                          │ ACL matrix    │
│               │                                              [legend ▾]  │ Physical      │
│ Abstract (2)  │                                                          │ Source: file  │
│ Drift (3) ⚠   │                                                          │ Records ▸     │
└───────────────┴──────────────────────────────────────────────────────────┴───────────────┘
│ 70 of 320 tables shown · 13 junctions · 192 constraints · schema v1                      │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

The status bar line **"70 of 320 tables shown"** is deliberate. It's the pitch in one sentence.

### 9.3 Views

| View | Nodes | Edges | Emphasis |
|---|---|---|---|
| **ERD** (default) | Boxes with field rows | all | Columns, types, keys |
| **Models** | Compact boxes, no fields | all, merged | 10-second overview |
| **Company** | Company-scoped vs global colouring | `check_company` 🔒, C1 warnings | 8.2 |
| **Security** | Nodes coloured by ACL coverage | none; groups panel | 8.3 |
| **Lifecycle** | Per-model state diagram (select a model) | transitions | 8.4 |
| **Physical** | Sized by row estimate or bytes | FKs only (real constraints) | 8.5 + drift list |

Views are **filters and styles over the same graph dict**. Switching views never refetches.

### 9.4 Visual language

| Element | Style |
|---|---|
| Owned node | Solid border, module colour header |
| Extended node | Dashed border, only injected fields, "+ from patient_safety" chip |
| Boundary node | Collapsed grey pill; click to expand fields (read-only) |
| Junction | Small diamond with table name |
| Wizard | Dotted border, ⚡ badge |
| View (`_auto=False`) | Double border, "SQL view" chip |
| many2one | Solid arrow → target; end marker: ✕ cascade, ⊘ restrict, ○ set null |
| one2many | Dashed; label "(reverse, no column)" |
| many2many | Solid line through junction |
| `_inherits` | Thick double line, "delegates to" |
| related | Dotted, "derived from" |
| Field row, inherited | Greyed, ↗ icon, tooltip "stored in `patient_safety_incident`" |
| Field row, computed non-stored | Italic, ƒ icon, "not in database" |
| Required | Bold name |
| Indexed | ⚡ small |
| Badges | 💬 chatter · 📅 activities · 🔁 workflow mixin · 🏢 company-scoped · 🔑 field groups |

**Accessibility:** colour is never the only signal; every style has a shape or text marker. Palette must work in light and dark (Odoo 19 dark mode).

### 9.5 Inspector panel

Sections for the selected node:

1. Header: label, technical name, table, owning module, node kind, badges.
2. **Fields** table, grouped by origin (own / inherited / extension / mixin / magic): name, label, type, target, required, stored, indexed, and physical column type when available.
3. **Relations**: in and out, clickable to focus the connected node.
4. **Company**: scoped or global, rules, C1–C4 findings.
5. **Security**: ACL mini-matrix, rules in English.
6. **Physical**: row estimate, size, indexes, constraints, drift items.
7. **Source**: `models/<file>.py` → `ClassName`, from `inspect.getsourcefile`, shown relative to the addon path. **Never an absolute server path in exports.**
8. **Records ▸** (sub-group only): first 5 records via **ORM `search_read`**, so record rules apply. Never raw SQL.

### 9.6 Interactions

- Click node → inspector. Double-click → focus mode (node + 1 hop, others faded).
- Click edge → highlight both ends + field rows.
- Search → fuzzy on model, table, field; pressing Enter centres the match.
- Drag nodes; **Save** stores positions on the diagram record.
- Right-click node → *Hide*, *Expand neighbours*, *Show only this subgraph*, *Copy table name*.
- Keyboard: `/` search, `1–6` views, `F` fit, `P` present, `Esc` clear focus.

### 9.7 Presentation mode and stories

- Fullscreen, sidebar and inspector hidden, larger fonts, fixed legend.
- A **story** is an ordered list of steps. Each step stores: title, 1–3 lines of narration, a view, visible or highlighted node ids, highlighted edge ids, a camera (zoom + pan), and an optional inspector section to open.
- Arrow keys step through. Animated camera between steps.
- **Author mode:** set up the canvas, click **"+ Add step from current view"**.
- Stories are saved with the diagram and **included in HTML export**, so an offline demo keeps its script.

**Seed story for `patient_safety`** (built in Phase 4 as acceptance content):

1. *70 of 320.* Everything else is Odoo core.
2. *The incident hub:* `patient.safety.incident` and its direct relations.
3. *Delegation:* 9 incident types, with most data stored in the parent table.
4. *Where the workflow lives:* the mixin badge, no table.
5. *Locations:* building → floor → room → location, all company-checked.
6. *Multi-company:* scoped vs global, record rules in English.
7. *Security:* groups and the access matrix.
8. *Investigation tools:* fishbone, bowtie, 5-why, SBAR.

## 10. Rendering and libraries

| Concern | Choice | License | Notes |
|---|---|---|---|
| UI framework | **OWL 2** (bundled with Odoo 19) | LGPL | Client action via `registry.category("actions").add("schema_explorer", …)` |
| Graph canvas | **Cytoscape.js** | MIT | Handles 150+ nodes, compound nodes, styling, PNG/JPG export built in |
| Layout (default) | **cytoscape-dagre + dagre** | MIT | Layered layout, good for ERDs, small |
| Layout (optional) | cytoscape-elk + elkjs | **EPL-2.0** | Better orthogonal edge routing. **License check needed before bundling** in an LGPL-3 module (section 19) |
| SVG export | cytoscape-svg | MIT | For vector docs |
| Field rows inside nodes | HTML labels overlay (e.g. cytoscape-node-html-label, MIT) **or** compound nodes | — | Spike in Phase 1; pick by performance with 54 nodes × ~30 fields |

- All libraries are **vendored into `static/lib/<name>/<version>/`** with their LICENSE files. No CDN, because Odoo installs are often offline and the standalone HTML must work offline.
- Load them in a **lazy asset bundle** (`schema_explorer.assets_canvas`), loaded only when the action opens, so every other backend page stays fast.

## 11. Exports and offline mode

| Format | Content | Produced by | Use |
|---|---|---|---|
| **HTML (standalone)** | One file: inlined Cytoscape + renderer JS + CSS + graph JSON + stories | Python template (no browser needed) | Offline client demo, email to a colleague |
| **JSON** | Graph contract v1 | core | Tooling, diffing, CI |
| **Mermaid** | `erDiagram` for current visible subgraph | Python | README, GitHub, docs |
| **DBML** | Tables, refs, notes (origin/kind in `Note`) | Python | dbdiagram.io, handover |
| **PNG / SVG** | Current canvas | Cytoscape (browser) | Slides |
| **Markdown report** | Tables of models, fields, relations, company, security, drift | Python | Tech docs |

### 11.1 Standalone HTML

- The **same JS renderer** as the in-app view, built as a plain ES module with no OWL dependency. The OWL component only wraps it. **This is how D1 (portability) holds for the UI too.**
  - `static/src/renderer/` holds pure JS: `render(container, graph, options)`, views, styles, legend, stories.
  - `static/src/owl/` holds the OWL client action: sidebar, inspector, toolbar, RPC; it calls `render`.
  - The standalone template inlines `renderer/*` plus a minimal vanilla sidebar and inspector.
- CLI:
  ```bash
  ./odoo-bin shell -c odoo.conf -d odoo_hsapp4 --no-http < custom-addons/schema_explorer/scripts/export.py
  # env vars: SE_MODULES=patient_safety SE_DEPTH=1 SE_FORMAT=html SE_OUT=./patient_safety.html SE_PHYSICAL=0 SE_ANONYMIZE=1
  ```
- **Export safety (`anonymize`)**, on by default for HTML:
  - Strip database name, hostnames, absolute paths.
  - Row counts rounded to buckets (`<100`, `100–1k`, `1k–10k`, `>10k`) or removed.
  - **Never include record data.** Sample records are in-app only.
  - Rule domains are kept (schema, not data).

## 12. Module structure

```
schema_explorer/
├── __init__.py
├── __manifest__.py                  # depends: base, web (mail optional for badges)
├── PLAN.md                          # this file
├── README.md
│
├── core/                            # ── PORTABLE: no odoo.http ──
│   ├── __init__.py
│   ├── inspector.py                 # build_graph(env, options) -> dict   (pipeline orchestration)
│   ├── options.py                   # dataclass Options + validation + defaults
│   ├── scope.py                     # step 1-2: modules → owned models/fields/relations/constraints
│   ├── registry_reader.py           # step 3: registry → field/model descriptors
│   ├── classify.py                  # step 4: node kinds, field origin, mixins
│   ├── expand.py                    # step 5: depth, hubs, caps
│   ├── analyzers/
│   │   ├── relations.py             # 8.1
│   │   ├── company.py               # 8.2
│   │   ├── security.py              # 8.3
│   │   ├── lifecycle.py             # 8.4
│   │   └── domain_english.py        # domain → plain English (shared)
│   ├── physical/
│   │   ├── pg_catalog.py            # parameterized catalog queries
│   │   └── drift.py                 # D1-D10
│   ├── exporters/
│   │   ├── json_export.py
│   │   ├── mermaid.py
│   │   ├── dbml.py
│   │   ├── markdown.py
│   │   └── html_standalone.py       # inlines static/src/renderer + static/lib
│   └── contract.py                  # SCHEMA_VERSION, TypedDicts for the graph
│
├── models/
│   ├── __init__.py
│   ├── schema_explorer_service.py   # AbstractModel: @api.model get_graph(options) → wraps core, checks groups
│   ├── schema_explorer_diagram.py   # stored: saved diagram
│   ├── schema_explorer_story.py     # stored: story + steps
│   └── ir_module_module.py          # "View schema" button
│
├── controllers/
│   └── main.py                      # /schema_explorer/export/<fmt> (file download), auth='user'
│
├── security/
│   ├── schema_explorer_groups.xml   # group_schema_explorer_user, group_schema_explorer_physical
│   ├── ir.model.access.csv
│   └── schema_explorer_rules.xml    # diagrams: own + shared
│
├── views/
│   ├── schema_explorer_action.xml   # ir.actions.client tag=schema_explorer
│   ├── schema_explorer_diagram_views.xml
│   ├── ir_module_module_views.xml
│   └── menus.xml
│
├── data/
│   └── hub_models.xml               # ir.config_parameter: default hub list, max_nodes
│
├── static/
│   ├── lib/                         # vendored cytoscape, dagre, cytoscape-dagre, cytoscape-svg (+ LICENSES)
│   ├── src/
│   │   ├── renderer/                # PORTABLE vanilla JS: render(), styles, views, legend, story player
│   │   ├── owl/                     # OWL client action, sidebar, inspector, toolbar, story editor
│   │   └── scss/
│   └── description/                 # icon, banner, index.html
│
├── templates/
│   └── standalone.html.j2           # or QWeb; see open question Q3
│
├── scripts/
│   └── export.py                    # odoo-bin shell entry point
│
└── tests/
    ├── __init__.py
    ├── fixtures/                    # tiny test modules (see 16.2)
    ├── test_scope.py
    ├── test_classify.py
    ├── test_company.py
    ├── test_security.py
    ├── test_domain_english.py
    ├── test_drift.py
    ├── test_exporters.py
    ├── test_contract.py
    └── test_access.py
```

## 13. Stored models

### `schema.explorer.diagram`

| Field | Type | Notes |
|---|---|---|
| `name` | Char, required | |
| `module_ids` | M2m `ir.module.module` | scope |
| `options` | Json | serialized `Options` |
| `view` | Selection | erd, models, company, security, lifecycle, physical |
| `layout` | Json | `{node_id: {x, y}}`, `hidden: [...]`, camera |
| `story_ids` | O2m `schema.explorer.story` | |
| `user_id` | M2o `res.users`, default current | owner |
| `shared` | Boolean | visible to all `group_schema_explorer_user` |
| `graph_snapshot` | Json, optional | frozen graph for "as of" comparisons (Phase 5+) |

### `schema.explorer.story` / `schema.explorer.story.step`

| Model | Fields |
|---|---|
| story | `name`, `diagram_id`, `sequence`, `step_ids` |
| step | `sequence`, `title`, `narration` (Text), `view`, `focus_nodes` (Json), `highlight_edges` (Json), `camera` (Json), `inspector_section` (Char) |

**No stored copy of the schema itself.** The graph is always computed live (or cached, see 15). Saved node ids that no longer exist are ignored with a warning.

## 14. Security of the tool itself

| Concern | Control |
|---|---|
| Who can open it | `group_schema_explorer_user`. Menu, client action and service method all check it. **Server-side check in `get_graph`**, not just menu visibility. |
| Physical details (row counts, sizes, drift) | `group_schema_explorer_physical` (implies user). Without it, `options.physical` is forced to `False` server-side. |
| Sample records | Physical group + **ORM `search_read` as the current user** (ACLs + record rules apply), limit 5. Never `sudo()`, never raw SQL. |
| The service reads `ir.model.access`, `ir.rule`, `ir.model.data` | These need admin rights, so the service uses `sudo()` **only for metadata models**, never for business models. Code review checklist item. |
| SQL injection | pg_catalog queries use `%s` params only. Every table name is **validated against registry `_table` values** before use. `psycopg2.sql.Identifier` if an identifier must be composed. |
| Domain parsing | `ast.literal_eval` or a tokenizer only. **Never `safe_eval` against a real env.** |
| Source file paths | Relative to the addon root only. |
| Exports | `anonymize` default on for HTML. Record data never exported. |
| Diagrams | Record rules: own diagrams + `shared=True`. |
| Multi-company | The tool's own models are not company-scoped. Schema is database-wide. |
| Audit | Optional: log exports (who, which modules, format) through `_logger.info`. |

## 15. Performance and caching

- **Cache key:** `(registry.registry_sequence, frozenset(modules), options_hash_without_physical)`.
  `registry_sequence` changes when the registry reloads (install, upgrade, uninstall), so it invalidates automatically.
- **Storage:** module-level LRU dict (size ~32) per process. Don't use `ormcache`; it would conflict with its own invalidation semantics.
- **Physical layer is never cached** (row counts change). It's fetched in **one batched query per catalog source** for all tables in scope, never per table.
- **Targets on `patient_safety`, depth 1:**
  - Graph without physical: **< 300 ms**
  - Graph with physical: **< 800 ms**
  - Canvas first render (~70 nodes): **< 1 s**
- **Canvas:** field rows collapse to "N fields" below a zoom threshold (level-of-detail). Only nodes in the viewport render full field HTML.
- **Profiling harness:** `scripts/export.py` prints step timings when `SE_TIMINGS=1`.

## 16. Testing strategy

### 16.1 Unit tests (core, `TransactionCase`, tagged `schema_explorer`)

- `test_scope`: owned models/fields/relations/constraints count for fixture modules.
- `test_classify`: every node kind, including the same-module extension merge and `_auto=False`.
- `test_classify`: field `origin` for `_inherits`, `related`, mixin, extension, magic.
- `test_expand`: depth 0/1/2, hub dampening, `max_nodes` cap + warning.
- `test_company`: C1–C4 on fixtures; `_inherits` company propagation.
- `test_domain_english`: table-driven cases of domain → English; malformed input falls back to raw text, never raises.
- `test_drift`: create fixture drift (add an orphan column with `ALTER TABLE` inside the test transaction; drop an index) → D1, D3 detected.
- `test_contract`: output validates against `contract.py` TypedDicts / JSON Schema; `schema_version == 1`.
- `test_exporters`: Mermaid and DBML snapshots; HTML contains no absolute paths or DB name when anonymized.
- `test_access`: user without group → `AccessError`; user without physical group → no `physical` or `drift` keys.

### 16.2 Test fixtures

Small modules in `tests/fixtures/` (installed only in the test database) covering each structure in isolation:

| Fixture | Covers |
|---|---|
| `se_fixture_basic` | m2o, o2m, m2m, required, index, ondelete |
| `se_fixture_inherits` | `_inherits` child + abstract mixin chain |
| `se_fixture_extend` | extends `res.partner`; extends its own model in a second file |
| `se_fixture_company` | `_check_company_auto`, `check_company`, missing rule (C2), cross-company link (C1) |
| `se_fixture_view` | `_auto=False` SQL view model, TransientModel |

These keep tests fast and independent of `patient_safety`.

### 16.3 Acceptance tests (reference module)

A `post_install` test tagged `schema_explorer_reference`, **skipped unless `patient_safety` is installed**:

| Assertion | Expected (hsapp4, 19.0.3.2.0) |
|---|---|
| owned models | 54 |
| junction tables | 13 |
| `inherits` edges to `patient.safety.incident` | 9 |
| `patient.safety.workflow.mixin` in `abstract_models`, not in `nodes` | ✓ |
| `patient.scan.provider` in `abstract_models` | ✓ |
| `res.company`, `res.users`, `res.groups`, `res.partner` are `extended` | ✓ |
| `patient.safety.incident` is a single `owned` node (inherit file merged) | ✓ |
| 3 `wizard` nodes when wizards included | ✓ |
| all 9 delegated incident types listed in `company.inherits_company` | ✓ |

> Numbers depend on the module version. The test reads `ir_module_module.latest_version` and **skips with a message** on a mismatch, instead of failing.

### 16.4 JS tests

- Hoot tests (Odoo 19 JS test framework) for: renderer builds the right element count from a fixture graph; view switching doesn't refetch; story player step navigation.
- Manual QA checklist per phase (below).

## 17. Phased delivery

### Phase 0: Core spike and contract freeze

**Goal:** prove the data model before any UI exists.

| Task |
|---|
| Module skeleton, manifest, groups |
| `core/options.py`, `contract.py` (v1 draft) |
| `scope.py`, `registry_reader.py`, `classify.py`, `expand.py` |
| `analyzers/relations.py` |
| `exporters/json_export.py`, `exporters/mermaid.py` |
| `scripts/export.py` (shell entry, `SE_*` env vars, `SE_TIMINGS`) |
| Fixtures `se_fixture_basic`, `se_fixture_inherits`, `se_fixture_extend` + unit tests |

**Exit criteria**

- `patient_safety.graph.json` and `.mmd` generated from `odoo_hsapp4`.
- All section 16.3 assertions pass, except the company ones.
- Mermaid output reviewed and judged "correct and readable".
- **Contract v1 frozen.**

### Phase 1: In-app MVP (ERD + Models views)

| Task |
|---|
| Vendor Cytoscape + dagre; lazy asset bundle |
| `static/src/renderer/`: render, styles, legend, ERD + Models views |
| **Spike:** field rows (HTML label vs compound); pick one, note the reason in README |
| `schema_explorer_service.get_graph` with group check + cache (section 15) |
| OWL client action: toolbar, module picker, depth, toggles, sidebar model list, inspector (sections 1–3, 7) |
| Interactions: select, focus, search, fit, hide, expand |
| `_inherits` inherited-field rows and delegation edge style |
| "View schema" button on module form |
| Menus, action, access |

**Exit criteria**

- `patient_safety` renders at depth 0 and 1 within the section 15 targets.
- A person unfamiliar with Odoo can answer from the canvas alone: *"where is a fall incident's company stored?"* (Answer: the parent incident table.)
- User without group gets no menu and an `AccessError` on direct RPC.

### Phase 2: Multi-company + Physical + Drift

| Task |
|---|
| `analyzers/company.py` (C1–C4) + `domain_english.py` |
| Company view + inspector section 4 |
| `physical/pg_catalog.py`, `physical/drift.py` (D1–D10) |
| Physical view + inspector section 6 + sidebar drift list |
| `group_schema_explorer_physical`; server-side enforcement |
| Fixtures `se_fixture_company`, `se_fixture_view` + tests |

**Exit criteria**

- All section 16.3 assertions pass, including company.
- Drift run on `odoo_hsapp4` produces a list reviewed by a developer. Every item is either a real finding or a documented false positive that is then fixed.
- Company view explains the building → floor → room → location chain and incident isolation without narration.

### Phase 3: Security + Lifecycle

| Task |
|---|
| `analyzers/security.py`: groups tree, ACL matrix, rules, field groups |
| Security view + inspector section 5 |
| `analyzers/lifecycle.py` + Lifecycle view |
| Records ▸ panel (ORM, physical group) |

**Exit criteria**

- ACL matrix for `patient_safety` matches `security/ir.model.access.csv`.
- All 48 rules listed with English or a raw fallback. **Zero crashes on any domain.**

### Phase 4: Exports + Presentation

| Task |
|---|
| Diagram + story models, views, rules |
| Save/load layout |
| Presentation mode + story player + author mode |
| Exporters: DBML, Markdown, PNG/SVG, **standalone HTML** (`html_standalone.py` + template) |
| `anonymize` option |
| Seed story for `patient_safety` (section 9.7) |

**Exit criteria**

- The standalone HTML opens with **no network and no Odoo** (tested with Wi-Fi off) and plays the seed story.
- `grep` on the exported HTML finds no DB name, hostname, absolute path or record data.
- DBML imports cleanly into dbdiagram.io.

### Phase 5: Polish

| Task |
|---|
| Dark mode palette check |
| Level-of-detail rendering; test at 150 nodes |
| Multi-module scope (e.g. `patient_safety` + `custom_barcode_hs`), with module colours |
| README with screenshots, `static/description/index.html` |
| Hoot JS tests |
| Performance pass against section 15 targets |

### Summary

| Phase | Theme | Depends on |
|---|---|---|
| 0 | Core + contract | — |
| 1 | In-app ERD MVP | 0 |
| 2 | Multi-company + physical + drift | 1 |
| 3 | Security + lifecycle | 1 |
| 4 | Exports + presentation | 1 (best after 2–3 for story content) |
| 5 | Polish | 1–4 |

Phases 2 and 3 are independent and can run in parallel.

## 18. Risks and edge cases

| # | Risk / edge case | Mitigation |
|---|---|---|
| R1 | Depth 2 through `res.users`/`res.partner` explodes | Hub dampening + `max_nodes` cap (7.3) |
| R2 | Every node links to `res.users` via `create_uid`/`write_uid` | Magic-field edges excluded by default |
| R3 | Mixin field attribution is ambiguous (field redefined in child) | Origin = the most-derived class that declares it; the inspector shows the full chain |
| R4 | Field on a model owned by module X but also re-declared by module Y | `defined_in_module` lists all modules from `ir.model.fields` xmlids; the first-owning module is primary |
| R5 | `_auto=False` / `_table_query` models have no normal table | Node kind `view`; physical uses `pg_views` or skips; drift D7 not applied |
| R6 | `company_dependent` fields are `jsonb`, not a column per company | Special rendering + D10 type check |
| R7 | Translated fields are `jsonb` | Show "translatable (jsonb)" in the physical column |
| R8 | Registry state ≠ DB state during "to upgrade" | Warning banner when any scoped module state ≠ `installed` |
| R9 | Domain → English is wrong and misleads a demo audience | Raw domain always shown next to the English; the English is labelled "summary" |
| R10 | Lifecycle transitions from regex are wrong | Labelled "static guess"; Phase 3 treats it as best-effort |
| R11 | Large field counts make ERD nodes huge (incident has many fields) | Collapse groups inside the node ("+ 62 inherited"), level-of-detail |
| R12 | `reltuples` is -1 or 0 on never-analyzed tables | Show "unknown (not analyzed)" instead of 0 |
| R13 | Library size bloats backend assets | Lazy bundle, loaded only by the client action |
| R14 | EPL-2.0 (elkjs) with LGPL-3 distribution | Default to MIT dagre; ELK only after license review (Q2) |
| R15 | `sudo()` in the service leaks metadata to low-privilege users | Group check **before** any `sudo()`; test in `test_access` |
| R16 | Standalone HTML leaks sensitive info in a client demo | `anonymize` default on, no record data ever, export test in Phase 4 |

## 19. Open questions

| # | Question | Default if not decided |
|---|---|---|
| Q1 | Technical name: `schema_explorer`, `crede_schema_explorer` or other? Publish on the Odoo Apps store? | `schema_explorer`, internal |
| Q2 | Is bundling EPL-2.0 (elkjs) acceptable for distribution? | No; dagre only |
| Q3 | Standalone HTML template engine: Python `string.Template` (no dependency), Jinja2 (in Odoo's requirements), or QWeb `ir.qweb._render` (needs env)? | Jinja2 (portable, already a dependency) |
| Q4 | Should saved diagrams be company-scoped, for multi-tenant hosting? | No |
| Q5 | Should `migrations/` scripts be listed per version (upgrade history view)? | Future (section 20) |
| Q6 | Minimum supported Odoo: 19 only, or backport to 17/18? | 19 only; keep version-specific reads in `registry_reader.py` so a backport is contained |
| Q7 | Include dependency modules' owned models as a second colour when `include_dependencies`? | Yes, Phase 5 |

## 20. Future ideas

- **Database compare:** run the inspector on two databases (e.g. `odoo_hsapp3` vs `odoo_hsapp4`) and show added, removed or changed models, fields and constraints. Directly useful given the version differences measured in section 4.
- **Version compare:** save `graph_snapshot` per module version and view "what changed in 19.0.3.2.0".
- **Migration timeline:** list `migrations/<version>/` scripts on the timeline.
- **CI mode:** `scripts/export.py SE_FORMAT=json` in CI + diff against the committed JSON. A schema change in a PR becomes visible in review.
- **Query helper:** "Show SQL join path" between two selected nodes (e.g. fall incident → building), emitting a read-only `SELECT … JOIN …` string for learning. Never executed by the tool.
- **Studio fields:** `x_` / `state='manual'` fields highlighted as "added through the UI".
- **Views and menus view:** which `ir.ui.view` and `ir.ui.menu` records expose each model.
