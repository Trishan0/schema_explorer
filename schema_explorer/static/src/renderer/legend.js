/** @odoo-module **/
/**
 * Plain-language legend content (PLAN.md, section 9.4 / goal G3: "every
 * visual style has a plain-language legend entry, written for someone who
 * has never seen Odoo"). Pure data so it can be reused by the standalone
 * HTML export later (PLAN.md, section 11.1) without pulling in OWL.
 */

export const LEGEND_NODE_KINDS = [
    {
        kind: "owned",
        title: "Owned",
        description: "This module defines this table.",
    },
    {
        kind: "extended",
        title: "Extended",
        description:
            "A different module (often Odoo itself) created this table; this module only adds a few fields to it.",
    },
    {
        kind: "boundary",
        title: "Boundary",
        description:
            "Outside the selected module(s), shown because something in scope points at it. Click it to see its own fields.",
    },
    {
        kind: "wizard",
        title: "Wizard",
        description:
            "A temporary form (Odoo calls it transient) used for one-off actions - its rows get cleaned up automatically and are not permanent data.",
    },
    {
        kind: "view",
        title: "SQL view",
        description:
            "Not a real table - PostgreSQL computes this on the fly from a query. There is nothing to insert into directly.",
    },
];

export const LEGEND_EDGE_KINDS = [
    {
        kind: "many2one",
        title: "Many-to-one",
        description:
            "A real foreign-key column. Many rows here can point at one row over there.",
    },
    {
        kind: "one2many",
        title: "One-to-many",
        description:
            "Not a real column - this is just the reverse view of a many-to-one field defined on the other model.",
    },
    {
        kind: "many2many",
        title: "Many-to-many",
        description:
            "Backed by a separate join table with one column for each side - shown as the field's own line here.",
    },
    {
        kind: "inherits",
        title: "Delegates to (_inherits)",
        description:
            "This model has almost no columns of its own - nearly all of its data actually lives in the row it delegates to.",
    },
    {
        kind: "related",
        title: "Derived from",
        description:
            "This field's value is copied/looked up from a field on the other model, following the arrow shown.",
    },
];

export const MIXIN_DESCRIPTIONS = {
    "mail.thread": "Adds the chatter (messages + activity log) to this record.",
    "mail.activity.mixin": "Adds scheduled activities (reminders, to-dos) to this record.",
    "mail.thread.blacklist": "Adds email-blacklist checking on top of the chatter.",
    "mail.thread.phone": "Adds phone-number formatting/validation on top of the chatter.",
    "bus.listener.mixin": "Lets this model push live updates over the realtime bus.",
    "avatar.mixin": "Adds an auto-generated avatar image.",
    "image.mixin": "Adds the standard set of resized image fields.",
};
