/** @odoo-module **/
/**
 * Pure conversion: Schema Explorer graph JSON (PLAN.md, section 6) ->
 * Cytoscape elements. No OWL, no Odoo services - this file only knows
 * about the graph contract and Cytoscape's element format, so the same
 * code renders both the in-app canvas and the standalone HTML export
 * (PLAN.md, decision D1 / section 11.1).
 */

/** Field rows are not drawn on the canvas itself (PLAN.md, section 17,
 * phase 1 "spike: field rows inside nodes"): after trying it, a compact
 * node (kind badge + field count) reads far better than one row per field
 * once a model has 60+ inherited fields (patient.safety.fall.incident has
 * ~80) - full field detail lives in the inspector panel instead. This
 * keeps the canvas fast and legible at 50-150 nodes without pulling in an
 * HTML-label library on top of Cytoscape. */
export function graphToElements(graph, options) {
    const { hiddenNodeIds = new Set() } = options || {};
    const nodes = [];
    const edges = [];

    for (const node of graph.nodes) {
        if (hiddenNodeIds.has(node.id)) {
            continue;
        }
        const ownFieldCount = node.fields.filter((f) => f.origin !== "inherits").length;
        const inheritedFieldCount = node.fields.length - ownFieldCount;
        nodes.push({
            group: "nodes",
            data: {
                id: node.id,
                label: shortLabel(node),
                kind: node.kind,
                table: node.table,
                module: node.module,
                mixins: node.mixins,
                ownFieldCount,
                inheritedFieldCount,
            },
            classes: `se-node se-node-${node.kind}`,
        });
    }

    const visibleIds = new Set(nodes.map((n) => n.data.id));
    for (const edge of graph.edges) {
        if (!visibleIds.has(edge.from) || !visibleIds.has(edge.to)) {
            continue;
        }
        edges.push({
            group: "edges",
            data: {
                id: edge.id,
                source: edge.from,
                target: edge.to,
                label: edge.field,
                kind: edge.kind,
                required: !!edge.required,
                ondelete: edge.ondelete || null,
            },
            classes: edgeClasses(edge),
        });
    }

    return { nodes, edges };
}

function shortLabel(node) {
    // The model's own label (_description) is usually more meaningful for
    // a demo audience than the raw table name, but keep the table name
    // visible too - it's the thing a developer will actually go look up in
    // pgAdmin/DBeaver next.
    if (node.label && node.label !== node.table) {
        return `${node.label}\n${node.table}`;
    }
    return node.table || node.id;
}

function edgeClasses(edge) {
    const classes = [`se-edge se-edge-${edge.kind}`];
    if (edge.kind === "many2one" && !edge.required) {
        classes.push("se-edge-optional");
    }
    if (edge.kind === "one2many") {
        classes.push("se-edge-nonphysical");
    }
    return classes.join(" ");
}
