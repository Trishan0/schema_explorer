/** @odoo-module **/
/**
 * Thin imperative wrapper around Cytoscape (vendored as plain UMD scripts,
 * so it is referenced through the `cytoscape` global rather than an ES
 * import - see static/lib/ and the manifest's asset bundle). Deliberately
 * has no OWL dependency: the same renderer is meant to back both the OWL
 * client action and, later, the standalone HTML export (PLAN.md, section
 * 11.1) which has no OWL runtime at all.
 */
import { graphToElements } from "./graph_to_elements";
import { buildStylesheet, NODE_KIND_STYLE, EDGE_KIND_STYLE } from "./styles";

/**
 * @param {HTMLElement} container
 * @param {object} [handlers]
 * @param {(nodeId: string) => void} [handlers.onSelectNode]
 * @param {() => void} [handlers.onDeselect]
 */
export function createRenderer(container, handlers = {}) {
    if (typeof cytoscape === "undefined") {
        throw new Error(
            "Schema Explorer: the `cytoscape` library did not load - check the " +
                "web.assets_backend bundle includes static/lib/cytoscape.",
        );
    }

    const cy = cytoscape({
        container,
        style: buildStylesheet(),
        wheelSensitivity: 0.2,
        minZoom: 0.1,
        maxZoom: 3,
    });

    let selectedNodeId = null;
    let currentViewMode = "erd";

    cy.on("tap", "node", (evt) => {
        const id = evt.target.id();
        selectNode(id);
    });
    cy.on("tap", (evt) => {
        if (evt.target === cy) {
            clearSelection();
        }
    });

    function selectNode(id) {
        selectedNodeId = id;
        cy.batch(() => {
            cy.elements().removeClass("se-selected se-dimmed");
            const node = cy.getElementById(id);
            if (node.empty()) {
                return;
            }
            const neighborhood = node.closedNeighborhood();
            cy.elements().difference(neighborhood).addClass("se-dimmed");
            node.addClass("se-selected");
        });
        if (handlers.onSelectNode) {
            handlers.onSelectNode(id);
        }
    }

    function clearSelection() {
        selectedNodeId = null;
        cy.elements().removeClass("se-selected se-dimmed");
        if (handlers.onDeselect) {
            handlers.onDeselect();
        }
    }

    /**
     * Replace the graph entirely. Re-layouts with dagre unless
     * `options.positions` (a saved diagram's stored layout - PLAN.md,
     * section 13) is given, in which case those positions are applied
     * directly and no automatic layout runs, so a saved diagram reopens
     * exactly where its author left it.
     */
    function mount(graph, options = {}) {
        const elements = graphToElements(graph, options);
        cy.elements().remove();
        cy.add([...elements.nodes, ...elements.edges]);
        if (options.positions && Object.keys(options.positions).length) {
            setPositions(options.positions);
            cy.fit(undefined, 30);
        } else {
            runLayout();
        }
        if (selectedNodeId && !cy.getElementById(selectedNodeId).empty()) {
            selectNode(selectedNodeId);
        } else {
            selectedNodeId = null;
        }
        if (currentViewMode) {
            applyViewMode(currentViewMode, graph);
        }
    }

    /**
     * Style-only overlay for the Company/Physical views (PLAN.md, section
     * 9.3) - these never re-fetch or re-layout, just toggle classes on the
     * nodes already on the canvas.
     */
    function applyViewMode(mode, graph) {
        currentViewMode = mode;
        cy.batch(() => {
            cy.nodes().removeClass("se-company-scoped se-company-global se-has-drift se-no-acl se-has-lifecycle");
            if (mode === "company" && graph.company) {
                const scoped = new Set([
                    ...graph.company.company_models.map((m) => m.model),
                    ...graph.company.inherits_company.map((m) => m.model),
                ]);
                const global = new Set(graph.company.global_models);
                cy.nodes().forEach((n) => {
                    if (scoped.has(n.id())) {
                        n.addClass("se-company-scoped");
                    } else if (global.has(n.id())) {
                        n.addClass("se-company-global");
                    }
                });
            } else if (mode === "physical" && graph.drift) {
                const driftModels = new Set(graph.drift.map((d) => d.model).filter(Boolean));
                cy.nodes().forEach((n) => {
                    if (driftModels.has(n.id())) {
                        n.addClass("se-has-drift");
                    }
                });
            } else if (mode === "security" && graph.security) {
                const noAcl = new Set(graph.security.models_without_access);
                cy.nodes().forEach((n) => {
                    if (noAcl.has(n.id())) {
                        n.addClass("se-no-acl");
                    }
                });
            } else if (mode === "lifecycle" && graph.lifecycle) {
                const withLifecycle = new Set(graph.lifecycle.models.map((m) => m.model));
                cy.nodes().forEach((n) => {
                    if (withLifecycle.has(n.id())) {
                        n.addClass("se-has-lifecycle");
                    }
                });
            }
        });
    }

    function runLayout() {
        // `cytoscape(type, name)` (2-arg form) is the extension-registry
        // getter - it returns the registered layout or undefined, without
        // throwing, unlike `cy.layout({name: 'unregistered'})`.
        const dagreRegistered = typeof cytoscape("layout", "dagre") === "function";
        cy.layout({
            name: dagreRegistered ? "dagre" : "cose",
            rankDir: "TB",
            nodeSep: 40,
            rankSep: 90,
            animate: false,
            fit: true,
            padding: 30,
        }).run();
    }

    function fit() {
        cy.fit(undefined, 30);
    }

    function focus(nodeId) {
        const node = cy.getElementById(nodeId);
        if (node.empty()) {
            return;
        }
        selectNode(nodeId);
        cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1) }, { duration: 300 });
    }

    /** Fuzzy-ish substring search across model id/table/label; dims non-matches. */
    function search(term) {
        const normalized = (term || "").trim().toLowerCase();
        if (!normalized) {
            cy.elements().removeClass("se-dimmed se-hidden");
            return [];
        }
        const matches = [];
        cy.nodes().forEach((n) => {
            const hay = [n.id(), n.data("table"), n.data("label")].join(" ").toLowerCase();
            if (hay.includes(normalized)) {
                matches.push(n.id());
            }
        });
        const matchSet = new Set(matches);
        cy.batch(() => {
            cy.nodes().forEach((n) => {
                n.toggleClass("se-dimmed", !matchSet.has(n.id()));
            });
            cy.edges().forEach((e) => {
                const visible = matchSet.has(e.source().id()) && matchSet.has(e.target().id());
                e.toggleClass("se-dimmed", !visible);
            });
        });
        return matches;
    }

    /** Current node positions, e.g. to persist on a saved diagram
     * (PLAN.md, section 13: `layout: {node_id: {x, y}}`). */
    function getPositions() {
        const positions = {};
        cy.nodes().forEach((n) => {
            positions[n.id()] = n.position();
        });
        return positions;
    }

    /** Restore positions saved by `getPositions` - nodes missing from
     * `positions` (e.g. added since the diagram was last saved) keep
     * wherever the last layout put them. */
    function setPositions(positions) {
        if (!positions) {
            return;
        }
        cy.batch(() => {
            cy.nodes().forEach((n) => {
                const pos = positions[n.id()];
                if (pos) {
                    n.position(pos);
                }
            });
        });
    }

    /** Current camera, in the shape a story step stores it (PLAN.md,
     * section 9.7: "a camera (zoom + pan)"). */
    function getViewport() {
        return { zoom: cy.zoom(), pan: cy.pan() };
    }

    function setViewport(viewport, opts = {}) {
        if (!viewport || !viewport.pan || typeof viewport.zoom !== "number") {
            return;
        }
        if (opts.animate) {
            cy.animate({ zoom: viewport.zoom, pan: viewport.pan }, { duration: 300 });
        } else {
            cy.zoom(viewport.zoom);
            cy.pan(viewport.pan);
        }
    }

    /** Highlight a story step's `focus_nodes`/`highlight_edges`, dimming
     * everything else - shared by the in-app presentation mode and the
     * standalone HTML export's story player (both load the same
     * `se-story-focus`/`se-story-dim` classes from styles.js). */
    function setHighlight(nodeIds = [], edgeIds = []) {
        cy.batch(() => {
            cy.elements().removeClass("se-story-focus se-story-dim");
            const ids = [...nodeIds, ...edgeIds];
            if (!ids.length) {
                return;
            }
            let eles = cy.collection();
            for (const id of ids) {
                eles = eles.union(cy.getElementById(id));
            }
            cy.elements().difference(eles).addClass("se-story-dim");
            eles.addClass("se-story-focus");
        });
    }

    function clearHighlight() {
        cy.elements().removeClass("se-story-focus se-story-dim");
    }

    /** A PNG data URL of the current canvas (PLAN.md, section 11, "PNG /
     * SVG... Produced by Cytoscape (browser)") - native to Cytoscape core,
     * no extra library needed. */
    function exportPNG(opts = {}) {
        return cy.png({ full: true, scale: 2, bg: "#ffffff", ...opts });
    }

    /**
     * A hand-rolled SVG snapshot of the current canvas.
     *
     * PLAN.md, section 10 originally proposed the `cytoscape-svg` extension
     * for this, listed there as MIT-licensed - it is actually GPLv3
     * (confirmed against its published package metadata while building
     * this export). The same reasoning the plan already applies to
     * `elkjs`/EPL-2.0 (section 18, R14; section 19, Q2: "no; dagre only"
     * pending a license review) applies here too, so rather than bundling
     * a GPLv3 dependency into an LGPL-3 module without that review, this
     * draws a plain rect-and-line SVG directly from Cytoscape's own node/
     * edge geometry. It is not pixel-identical to the on-screen canvas
     * (no curves, no arrowheads) but is perfectly usable for a slide.
     */
    function exportSVG() {
        const bb = cy.elements().boundingBox();
        const pad = 30;
        const width = Math.max(1, bb.w + pad * 2);
        const height = Math.max(1, bb.h + pad * 2);
        const toX = (x) => x - bb.x1 + pad;
        const toY = (y) => y - bb.y1 + pad;

        const parts = [
            `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" ` +
                `viewBox="0 0 ${width} ${height}" font-family="sans-serif" font-size="10">`,
            `<rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff"/>`,
        ];

        cy.edges().forEach((e) => {
            const src = e.source().position();
            const dst = e.target().position();
            const style = EDGE_KIND_STYLE[e.data("kind")] || { color: "#4a5568", style: "solid", width: 1.5 };
            const dash = style.style === "dashed" ? ' stroke-dasharray="6,4"'
                : style.style === "dotted" ? ' stroke-dasharray="2,3"' : "";
            parts.push(
                `<line x1="${toX(src.x)}" y1="${toY(src.y)}" x2="${toX(dst.x)}" y2="${toY(dst.y)}" ` +
                    `stroke="${style.color}" stroke-width="${style.width}"${dash}/>`,
            );
        });

        cy.nodes().forEach((n) => {
            const pos = n.position();
            const w = n.outerWidth();
            const h = n.outerHeight();
            const kindStyle = NODE_KIND_STYLE[n.data("kind")] || { border: "#718096", bg: "#f7fafc" };
            parts.push(
                `<rect x="${toX(pos.x) - w / 2}" y="${toY(pos.y) - h / 2}" width="${w}" height="${h}" ` +
                    `rx="6" fill="${kindStyle.bg}" stroke="${kindStyle.border}" stroke-width="2"/>`,
            );
            const label = String(n.data("label") || "").split("\n");
            label.forEach((line, i) => {
                const y = toY(pos.y) + (i - (label.length - 1) / 2) * 12 + 4;
                parts.push(`<text x="${toX(pos.x)}" y="${y}" text-anchor="middle">${escapeXml(line)}</text>`);
            });
        });

        parts.push("</svg>");
        return parts.join("\n");
    }

    function escapeXml(value) {
        return String(value).replace(/[&<>"']/g, (c) => (
            { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[c]
        ));
    }

    function destroy() {
        cy.destroy();
    }

    return {
        cy, mount, fit, focus, search, selectNode, clearSelection, applyViewMode,
        getPositions, setPositions, getViewport, setViewport, setHighlight, clearHighlight,
        exportPNG, exportSVG, destroy,
    };
}
