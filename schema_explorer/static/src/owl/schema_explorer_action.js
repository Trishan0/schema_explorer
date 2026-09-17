/** @odoo-module **/
import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { loadBundle } from "@web/core/assets";
import { createRenderer } from "@schema_explorer/renderer/renderer";
import { LEGEND_NODE_KINDS, LEGEND_EDGE_KINDS, MIXIN_DESCRIPTIONS } from "@schema_explorer/renderer/legend";

const DEPTH_CHOICES = [0, 1, 2];
const MODULE_SEARCH_DEBOUNCE_MS = 250;

export class SchemaExplorerAction extends Component {
    static template = "schema_explorer.Action";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.canvasRef = useRef("canvas");
        this.renderer = null;
        this._moduleSearchTimeout = null;

        const initialModules = (this.props.action && this.props.action.params &&
            this.props.action.params.modules) || [];

        this.state = useState({
            selectedModules: initialModules.map((name) => ({ name, label: name })),
            moduleSearchTerm: "",
            moduleSearchResults: [],
            depth: 0,
            includeWizards: false,
            includeTechnicalFields: false,
            canvasSearchTerm: "",
            graph: null,
            loading: false,
            error: null,
            selectedNodeId: null,
            hiddenNodeIds: new Set(),
            showLegend: false,
            // 'erd' | 'company' | 'physical' (PLAN.md, section 9.3). Only
            // 'physical' changes what is *fetched* (row counts, sizes, the
            // drift report); 'company' is a pure style overlay on data the
            // graph already carries.
            view: 'erd',
        });

        onWillStart(async () => {
            // Cytoscape (~450KB) and cytoscape-dagre are a separate, lazily
            // loaded bundle (PLAN.md, section 10): every other backend page
            // stays fast, and only opening this action pays for them.
            const tasks = [loadBundle("schema_explorer.assets_canvas")];
            if (this.state.selectedModules.length) {
                tasks.push(this.reload());
            }
            await Promise.all(tasks);
        });

        onMounted(() => {
            this.renderer = createRenderer(this.canvasRef.el, {
                onSelectNode: (nodeId) => {
                    this.state.selectedNodeId = nodeId;
                },
                onDeselect: () => {
                    this.state.selectedNodeId = null;
                },
            });
            if (this.state.graph) {
                this.renderer.mount(this.state.graph, { hiddenNodeIds: this.state.hiddenNodeIds });
            }
        });

        onWillUnmount(() => {
            if (this.renderer) {
                this.renderer.destroy();
            }
            clearTimeout(this._moduleSearchTimeout);
        });
    }

    // -- data loading ---------------------------------------------------

    get optionsPayload() {
        return {
            modules: this.state.selectedModules.map((m) => m.name),
            depth: this.state.depth,
            include_wizards: this.state.includeWizards,
            include_technical_fields: this.state.includeTechnicalFields,
            // Row counts/sizes/drift are only worth fetching for the
            // Physical view - everywhere else this stays false, so a user
            // without the physical group never even asks for it.
            physical: this.state.view === 'physical',
        };
    }

    async reload() {
        if (!this.state.selectedModules.length) {
            this.state.graph = null;
            return;
        }
        this.state.loading = true;
        this.state.error = null;
        try {
            const graph = await this.orm.call("schema.explorer.service", "get_graph", [
                this.optionsPayload,
            ]);
            this.state.graph = graph;
            this.state.hiddenNodeIds = new Set();
            if (this.renderer) {
                this.renderer.mount(graph, { hiddenNodeIds: this.state.hiddenNodeIds });
                this.renderer.applyViewMode(this.state.view, graph);
            }
        } catch (error) {
            this.state.error = (error && error.data && error.data.message) || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    // -- module picker ----------------------------------------------------

    onModuleSearchInput(ev) {
        this.state.moduleSearchTerm = ev.target.value;
        clearTimeout(this._moduleSearchTimeout);
        const term = this.state.moduleSearchTerm.trim();
        if (!term) {
            this.state.moduleSearchResults = [];
            return;
        }
        this._moduleSearchTimeout = setTimeout(async () => {
            const results = await this.orm.call("schema.explorer.service", "get_module_choices", [
                term,
                20,
            ]);
            const selectedNames = new Set(this.state.selectedModules.map((m) => m.name));
            this.state.moduleSearchResults = results.filter((r) => !selectedNames.has(r.name));
        }, MODULE_SEARCH_DEBOUNCE_MS);
    }

    async addModule(mod) {
        if (this.state.selectedModules.some((m) => m.name === mod.name)) {
            return;
        }
        this.state.selectedModules.push(mod);
        this.state.moduleSearchTerm = "";
        this.state.moduleSearchResults = [];
        await this.reload();
    }

    async removeModule(name) {
        this.state.selectedModules = this.state.selectedModules.filter((m) => m.name !== name);
        await this.reload();
    }

    // -- toolbar ----------------------------------------------------------

    get depthChoices() {
        return DEPTH_CHOICES;
    }

    async setDepth(depth) {
        this.state.depth = depth;
        await this.reload();
    }

    async toggleWizards() {
        this.state.includeWizards = !this.state.includeWizards;
        await this.reload();
    }

    async toggleTechnicalFields() {
        this.state.includeTechnicalFields = !this.state.includeTechnicalFields;
        await this.reload();
    }

    toggleLegend() {
        this.state.showLegend = !this.state.showLegend;
    }

    async setView(view) {
        const needsPhysicalFetch = view === 'physical' && !(this.state.graph && this.state.graph.drift);
        this.state.view = view;
        if (needsPhysicalFetch) {
            await this.reload();
        } else if (this.renderer && this.state.graph) {
            this.renderer.applyViewMode(view, this.state.graph);
        }
    }

    get viewChoices() {
        return [
            { id: 'erd', label: 'ERD' },
            { id: 'company', label: 'Company' },
            { id: 'physical', label: 'Physical' },
        ];
    }

    onCanvasSearchInput(ev) {
        this.state.canvasSearchTerm = ev.target.value;
        if (this.renderer) {
            this.renderer.search(this.state.canvasSearchTerm);
        }
    }

    onFit() {
        if (this.renderer) {
            this.renderer.fit();
        }
    }

    // -- sidebar / inspector ----------------------------------------------

    get nodesByKind() {
        const groups = { owned: [], extended: [], boundary: [], wizard: [], view: [] };
        if (!this.state.graph) {
            return groups;
        }
        for (const node of this.state.graph.nodes) {
            if (this.state.hiddenNodeIds.has(node.id)) {
                continue;
            }
            (groups[node.kind] || groups.boundary).push(node);
        }
        for (const kind of Object.keys(groups)) {
            groups[kind].sort((a, b) => a.id.localeCompare(b.id));
        }
        return groups;
    }

    get selectedNode() {
        if (!this.state.graph || !this.state.selectedNodeId) {
            return null;
        }
        return this.state.graph.nodes.find((n) => n.id === this.state.selectedNodeId) || null;
    }

    get selectedNodeEdges() {
        if (!this.state.graph || !this.state.selectedNodeId) {
            return { outgoing: [], incoming: [] };
        }
        const id = this.state.selectedNodeId;
        return {
            outgoing: this.state.graph.edges.filter((e) => e.from === id),
            incoming: this.state.graph.edges.filter((e) => e.to === id && e.from !== id),
        };
    }

    mixinDescription(mixinName) {
        return MIXIN_DESCRIPTIONS[mixinName] || null;
    }

    /** Company-scoping summary for the inspector panel (PLAN.md, section
     * 9.5 point 4): is this model scoped, via which field, what rules
     * apply in English, and any C1/C4 findings that mention it. */
    get selectedNodeCompanyInfo() {
        const node = this.selectedNode;
        const company = this.state.graph && this.state.graph.company;
        if (!node || !company) {
            return null;
        }
        const ownEntry = company.company_models.find((m) => m.model === node.id);
        const inheritedEntry = company.inherits_company.find((m) => m.model === node.id);
        const isGlobal = company.global_models.includes(node.id);
        return {
            ownEntry,
            inheritedEntry,
            isGlobal,
            rules: company.rules_plain.filter((r) => r.model === node.id),
            leaks: company.leaks.filter((l) => l.from === node.id || l.to === node.id),
        };
    }

    /** Drift findings for the selected node (PLAN.md, section 9.5 point 6). */
    get selectedNodeDrift() {
        const node = this.selectedNode;
        const drift = this.state.graph && this.state.graph.drift;
        if (!node || !drift) {
            return [];
        }
        return drift.filter((d) => d.model === node.id);
    }

    get driftSummary() {
        const drift = this.state.graph && this.state.graph.drift;
        if (!drift) {
            return null;
        }
        return {
            total: drift.length,
            items: drift,
        };
    }

    focusNode(nodeId) {
        this.state.selectedNodeId = nodeId;
        if (this.renderer) {
            this.renderer.focus(nodeId);
        }
    }

    hideSelectedNode() {
        if (!this.state.selectedNodeId) {
            return;
        }
        this.state.hiddenNodeIds.add(this.state.selectedNodeId);
        this.state.selectedNodeId = null;
        if (this.renderer) {
            this.renderer.mount(this.state.graph, { hiddenNodeIds: this.state.hiddenNodeIds });
        }
    }

    async expandOneMoreHop() {
        // Phase 1 simplification: "expand this boundary node" bumps the
        // global depth by one hop rather than scoping to just that node's
        // neighbours - see PLAN.md phase 1 vs. the per-node "Expand
        // neighbours" interaction planned for a later pass (section 9.6).
        if (this.state.depth < 2) {
            await this.setDepth(this.state.depth + 1);
        }
    }

    get legendNodeKinds() {
        return LEGEND_NODE_KINDS;
    }

    get legendEdgeKinds() {
        return LEGEND_EDGE_KINDS;
    }

    get statusText() {
        if (!this.state.graph) {
            return "";
        }
        const shown = this.state.graph.nodes.length - this.state.hiddenNodeIds.size;
        const total = this.state.graph.stats.db_tables_total;
        const totalText = total ? ` of ${total} tables in the database` : "";
        return `${shown} tables shown${totalText} · ${this.state.graph.edges.length} relations · schema v${this.state.graph.schema_version}`;
    }
}

registry.category("actions").add("schema_explorer.action", SchemaExplorerAction);
