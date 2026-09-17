/** @odoo-module **/
/**
 * Cytoscape stylesheet for Schema Explorer (PLAN.md, section 9.4).
 *
 * Every node kind and edge kind is distinguishable by shape/line-style, not
 * colour alone (PLAN.md, section 9.4, "Accessibility"). Colours are also
 * chosen to hold up in Cytoscape's canvas rendering under both the light
 * and dark Odoo backend themes (a mid-saturation palette on a pale/near-
 * black fill, rather than pure black-on-white).
 */

const NODE_KIND_STYLE = {
    owned: { border: "#2b6cb0", bg: "#ebf4ff", borderStyle: "solid", shape: "round-rectangle" },
    extended: { border: "#b7791f", bg: "#fffaf0", borderStyle: "dashed", shape: "round-rectangle" },
    boundary: { border: "#718096", bg: "#f7fafc", borderStyle: "solid", shape: "round-rectangle" },
    wizard: { border: "#6b46c1", bg: "#faf5ff", borderStyle: "dotted", shape: "round-rectangle" },
    view: { border: "#2c7a7b", bg: "#e6fffa", borderStyle: "double", shape: "round-rectangle" },
};

const EDGE_KIND_STYLE = {
    many2one: { color: "#2d3748", style: "solid", width: 2, arrow: "triangle" },
    one2many: { color: "#a0aec0", style: "dashed", width: 1.5, arrow: "triangle-backcurve" },
    many2many: { color: "#805ad5", style: "solid", width: 2, arrow: "diamond" },
    inherits: { color: "#c53030", style: "solid", width: 4, arrow: "triangle-tee" },
    related: { color: "#319795", style: "dotted", width: 1.5, arrow: "none" },
};

export function buildStylesheet() {
    const rules = [
        {
            selector: "core",
            style: { "active-bg-opacity": 0 },
        },
        {
            selector: "node.se-node",
            style: {
                label: "data(label)",
                "text-wrap": "wrap",
                "text-max-width": "150px",
                "font-size": "10px",
                "text-valign": "center",
                "text-halign": "center",
                width: "label",
                height: "label",
                padding: "10px",
                shape: "round-rectangle",
                "border-width": 2,
                color: "#1a202c",
            },
        },
    ];

    for (const [kind, s] of Object.entries(NODE_KIND_STYLE)) {
        rules.push({
            selector: `node.se-node-${kind}`,
            style: {
                "background-color": s.bg,
                "border-color": s.border,
                "border-style": s.borderStyle,
                shape: s.shape,
            },
        });
    }

    // boundary nodes are meant to read as "collapsed, click to learn more" -
    // smaller and lighter than the module's own models.
    rules.push({
        selector: "node.se-node-boundary",
        style: { "font-size": "9px", opacity: 0.85 },
    });

    rules.push(
        {
            selector: "node.se-selected",
            style: { "border-width": 4, "border-color": "#dd6b20", "z-index": 999 },
        },
        {
            selector: "node.se-dimmed",
            style: { opacity: 0.25 },
        },
        {
            selector: "node.se-hidden",
            style: { display: "none" },
        },
    );

    // -- Company view (PLAN.md, section 9.3) - overlaid on top of the kind
    // colours above (a thicker solid border = company-scoped, a grey
    // dashed one = shared/global data), not a replacement for them.
    rules.push(
        {
            selector: "node.se-company-scoped",
            style: { "border-width": 5, "border-color": "#2f855a" },
        },
        {
            selector: "node.se-company-global",
            style: { "border-color": "#a0aec0", "border-style": "dashed" },
        },
    );

    // -- Physical view: nodes with at least one drift finding get a hard
    // red outline regardless of their kind colour, so they stand out.
    rules.push({
        selector: "node.se-has-drift",
        style: { "border-color": "#c53030", "border-width": 4, "border-style": "solid" },
    });

    // -- Security view: a model with zero ir.model.access rows is only
    // reachable by the superuser - worth a loud highlight.
    rules.push({
        selector: "node.se-no-acl",
        style: { "border-color": "#c53030", "border-width": 4, "border-style": "dashed" },
    });

    // -- Lifecycle view: a subtle highlight for models that have a
    // workflow/state field at all, so they stand out from pure lookup
    // tables without redrawing the whole canvas.
    rules.push({
        selector: "node.se-has-lifecycle",
        style: { "border-color": "#6b46c1", "border-width": 4 },
    });

    rules.push({
        selector: "edge.se-edge",
        style: {
            "curve-style": "bezier",
            "font-size": "8px",
            label: "data(label)",
            color: "#4a5568",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.85,
            "text-background-padding": "1px",
        },
    });

    for (const [kind, s] of Object.entries(EDGE_KIND_STYLE)) {
        rules.push({
            selector: `edge.se-edge-${kind}`,
            style: {
                "line-color": s.color,
                "target-arrow-color": s.color,
                "line-style": s.style,
                width: s.width,
                "target-arrow-shape": s.arrow,
                "arrow-scale": 1,
            },
        });
    }

    rules.push(
        {
            selector: "edge.se-edge-optional",
            style: { "line-opacity": 0.7 },
        },
        {
            selector: "edge.se-dimmed",
            style: { opacity: 0.15 },
        },
        {
            selector: "edge.se-hidden",
            style: { display: "none" },
        },
    );

    // -- Presentation mode / story player (PLAN.md, section 9.7): a step's
    // `focus_nodes`/`highlight_edges` get a bright highlight, everything
    // else dims - shared by the in-app story player and the standalone
    // HTML export's vanilla one, since both load this same stylesheet.
    rules.push(
        {
            selector: "node.se-story-focus",
            style: { "border-width": 5, "border-color": "#dd6b20", "z-index": 998 },
        },
        {
            selector: "edge.se-story-focus",
            style: { "line-color": "#dd6b20", "target-arrow-color": "#dd6b20", width: 3, "z-index": 998 },
        },
        {
            selector: ".se-story-dim",
            style: { opacity: 0.15 },
        },
    );

    return rules;
}

export { NODE_KIND_STYLE, EDGE_KIND_STYLE };
