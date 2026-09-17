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
import { buildStylesheet } from "./styles";

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

    /** Replace the graph entirely and re-layout. */
    function mount(graph, options = {}) {
        const elements = graphToElements(graph, options);
        cy.elements().remove();
        cy.add([...elements.nodes, ...elements.edges]);
        runLayout();
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
            cy.nodes().removeClass("se-company-scoped se-company-global se-has-drift");
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

    function destroy() {
        cy.destroy();
    }

    return { cy, mount, fit, focus, search, selectNode, clearSelection, applyViewMode, destroy };
}
