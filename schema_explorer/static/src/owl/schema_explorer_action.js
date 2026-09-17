/** @odoo-module **/
import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { loadBundle } from "@web/core/assets";
import { download } from "@web/core/network/download";
import { _t } from "@web/core/l10n/translation";
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
        // Positions from a saved diagram's layout, applied on the *next*
        // mount only - any later reload() (depth/toggle change) goes back
        // to an automatic layout, since the node set has likely changed.
        this._pendingPositions = null;
        this._onKeyDown = (ev) => this.onKeyDown(ev);

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
            records: null,
            // 'erd' | 'company' | 'security' | 'lifecycle' | 'physical'
            // (PLAN.md, section 9.3). Only 'physical' changes what is
            // *fetched* (row counts, sizes, the drift report); the others
            // are pure style overlays on data the graph already carries.
            view: 'erd',

            // -- saved diagrams (PLAN.md, section 13) --------------------
            diagramId: null,
            diagramName: null,
            diagramShared: false,

            // -- stories / presentation mode (PLAN.md, section 9.7) ------
            stories: [],
            activeStoryIndex: null,
            showStoryPanel: false,
            presenting: false,
            presentStepIndex: 0,
        });

        onWillStart(async () => {
            // Cytoscape (~450KB) and cytoscape-dagre are a separate, lazily
            // loaded bundle (PLAN.md, section 10): every other backend page
            // stays fast, and only opening this action pays for them.
            const tasks = [loadBundle("schema_explorer.assets_canvas")];
            const diagramId = this.props.action && this.props.action.params &&
                this.props.action.params.diagram_id;
            if (diagramId) {
                tasks.push(this.openDiagram(diagramId));
            } else if (this.state.selectedModules.length) {
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
                this.renderer.mount(this.state.graph, {
                    hiddenNodeIds: this.state.hiddenNodeIds,
                    positions: this._pendingPositions || undefined,
                });
                this._pendingPositions = null;
            }
            window.addEventListener("keydown", this._onKeyDown);
        });

        onWillUnmount(() => {
            if (this.renderer) {
                this.renderer.destroy();
            }
            clearTimeout(this._moduleSearchTimeout);
            window.removeEventListener("keydown", this._onKeyDown);
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
                this.renderer.mount(graph, {
                    hiddenNodeIds: this.state.hiddenNodeIds,
                    positions: this._pendingPositions || undefined,
                });
                this._pendingPositions = null;
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
            { id: 'security', label: 'Security' },
            { id: 'lifecycle', label: 'Lifecycle' },
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

    // -- saved diagrams (PLAN.md, section 13) ------------------------------

    async _resolveModuleIds() {
        const names = this.state.selectedModules.map((m) => m.name);
        if (!names.length) {
            return [];
        }
        const modules = await this.orm.searchRead("ir.module.module", [["name", "in", names]], ["id"]);
        return modules.map((m) => m.id);
    }

    /** Load a saved diagram's scope/options/view/layout and its stories
     * (PLAN.md, section 9.1: "A saved diagram record opens the explorer
     * with stored options, layout and story."). */
    async openDiagram(diagramId) {
        const [diagram] = await this.orm.read(
            "schema.explorer.diagram", [diagramId],
            ["name", "module_ids", "options", "view", "layout", "shared"],
        );
        const modules = diagram.module_ids.length
            ? await this.orm.read("ir.module.module", diagram.module_ids, ["name", "shortdesc"])
            : [];

        this.state.diagramId = diagram.id;
        this.state.diagramName = diagram.name;
        this.state.diagramShared = diagram.shared;
        this.state.selectedModules = modules.map((m) => ({ name: m.name, label: m.shortdesc || m.name }));

        const options = diagram.options || {};
        this.state.depth = options.depth ?? 0;
        this.state.includeWizards = !!options.include_wizards;
        this.state.includeTechnicalFields = !!options.include_technical_fields;
        this.state.view = diagram.view || 'erd';

        const layout = diagram.layout || {};
        this._pendingPositions = layout.positions || null;

        await this.reload();
        await this._loadStories(diagram.id);
    }

    /** Create a new diagram (prompting for a name) or update the one
     * already loaded - either way capturing the current scope, options,
     * view and node layout (PLAN.md, section 9.6: "Drag nodes; Save stores
     * positions on the diagram record."). */
    async saveDiagram() {
        if (!this.state.selectedModules.length) {
            this.notification.add(_t("Add at least one module before saving."), { type: "warning" });
            return;
        }
        const moduleIds = await this._resolveModuleIds();
        const vals = {
            module_ids: [[6, 0, moduleIds]],
            options: {
                depth: this.state.depth,
                include_wizards: this.state.includeWizards,
                include_technical_fields: this.state.includeTechnicalFields,
            },
            view: this.state.view,
            layout: { positions: this.renderer ? this.renderer.getPositions() : {} },
        };

        if (this.state.diagramId) {
            await this.orm.write("schema.explorer.diagram", [this.state.diagramId], vals);
        } else {
            const defaultName = this.state.selectedModules.map((m) => m.name).join(", ");
            const name = window.prompt(_t("Save diagram as:"), defaultName);
            if (!name) {
                return;
            }
            vals.name = name;
            const created = await this.orm.create("schema.explorer.diagram", [vals]);
            this.state.diagramId = created[0];
            this.state.diagramName = name;
        }
        this.notification.add(_t("Diagram saved."), { type: "success" });
    }

    // -- stories: author mode + presentation mode (PLAN.md, section 9.7) --

    async _loadStories(diagramId) {
        const stories = await this.orm.searchRead(
            "schema.explorer.story", [["diagram_id", "=", diagramId]], ["name", "sequence"],
            { order: "sequence, id" },
        );
        for (const story of stories) {
            story.steps = await this.orm.searchRead(
                "schema.explorer.story.step", [["story_id", "=", story.id]],
                ["sequence", "title", "narration", "view", "focus_nodes", "highlight_edges", "camera", "inspector_section"],
                { order: "sequence, id" },
            );
        }
        this.state.stories = stories;
        this.state.activeStoryIndex = stories.length ? 0 : null;
    }

    get activeStory() {
        if (this.state.activeStoryIndex === null) {
            return null;
        }
        return this.state.stories[this.state.activeStoryIndex] || null;
    }

    toggleStoryPanel() {
        this.state.showStoryPanel = !this.state.showStoryPanel;
    }

    async newStory() {
        if (!this.state.diagramId) {
            this.notification.add(_t("Save the diagram before adding a story."), { type: "warning" });
            return;
        }
        const name = window.prompt(_t("New story name:"), _t("Walkthrough"));
        if (!name) {
            return;
        }
        await this.orm.create("schema.explorer.story", [{ name, diagram_id: this.state.diagramId }]);
        await this._loadStories(this.state.diagramId);
        this.state.activeStoryIndex = this.state.stories.length - 1;
    }

    async deleteStory(storyId) {
        await this.orm.unlink("schema.explorer.story", [storyId]);
        await this._loadStories(this.state.diagramId);
    }

    /** "+ Add step from current view" (PLAN.md, section 9.7, "Author
     * mode"): captures the view, the selected node as the step's focus,
     * and the current camera - exactly what a story step replays later. */
    async addStepFromCurrentView() {
        if (!this.state.diagramId) {
            this.notification.add(_t("Save the diagram before adding a story."), { type: "warning" });
            return;
        }
        let story = this.activeStory;
        if (!story) {
            const name = window.prompt(_t("New story name:"), _t("Walkthrough"));
            if (!name) {
                return;
            }
            const created = await this.orm.create("schema.explorer.story", [{ name, diagram_id: this.state.diagramId }]);
            await this._loadStories(this.state.diagramId);
            this.state.activeStoryIndex = this.state.stories.findIndex((s) => s.id === created[0]);
            story = this.activeStory;
        }

        const title = window.prompt(_t("Step title:"), "") || "";
        const narration = window.prompt(_t("Narration (1-3 lines):"), "") || "";
        const camera = this.renderer ? this.renderer.getViewport() : {};
        const focusNodes = this.state.selectedNodeId ? [this.state.selectedNodeId] : [];

        await this.orm.create("schema.explorer.story.step", [{
            story_id: story.id,
            sequence: (story.steps.length + 1) * 10,
            title,
            narration,
            view: this.state.view,
            focus_nodes: focusNodes,
            highlight_edges: [],
            camera,
        }]);
        await this._loadStories(this.state.diagramId);
    }

    async deleteStep(stepId) {
        await this.orm.unlink("schema.explorer.story.step", [stepId]);
        await this._loadStories(this.state.diagramId);
    }

    get canPresent() {
        return !!(this.activeStory && this.activeStory.steps.length);
    }

    /** Fullscreen, sidebar/inspector/toolbar hidden, larger fonts, arrow
     * keys step through (PLAN.md, section 9.7). */
    startPresentation() {
        if (!this.canPresent) {
            return;
        }
        this.state.presenting = true;
        this.state.presentStepIndex = 0;
        this._applyStoryStep(0);
    }

    exitPresentation() {
        this.state.presenting = false;
        if (this.renderer) {
            this.renderer.clearHighlight();
        }
    }

    presentNext() {
        const story = this.activeStory;
        if (!story) {
            return;
        }
        this.state.presentStepIndex = Math.min(story.steps.length - 1, this.state.presentStepIndex + 1);
        this._applyStoryStep(this.state.presentStepIndex);
    }

    presentPrev() {
        this.state.presentStepIndex = Math.max(0, this.state.presentStepIndex - 1);
        this._applyStoryStep(this.state.presentStepIndex);
    }

    get presentStep() {
        const story = this.activeStory;
        if (!story) {
            return null;
        }
        return story.steps[this.state.presentStepIndex] || null;
    }

    _applyStoryStep(index) {
        const story = this.activeStory;
        const step = story && story.steps[index];
        if (!step || !this.renderer || !this.state.graph) {
            return;
        }
        this.state.view = step.view || 'erd';
        this.renderer.applyViewMode(this.state.view, this.state.graph);
        this.renderer.setHighlight(step.focus_nodes || [], step.highlight_edges || []);
        if (step.camera && step.camera.pan) {
            this.renderer.setViewport(step.camera, { animate: true });
        } else if ((step.focus_nodes || []).length === 1) {
            this.renderer.focus(step.focus_nodes[0]);
        }
        if ((step.focus_nodes || []).length === 1) {
            this.state.selectedNodeId = step.focus_nodes[0];
        }
    }

    onKeyDown(ev) {
        if (!this.state.presenting) {
            return;
        }
        if (ev.key === "ArrowRight") {
            this.presentNext();
        } else if (ev.key === "ArrowLeft") {
            this.presentPrev();
        } else if (ev.key === "Escape") {
            this.exitPresentation();
        }
    }

    // -- exports (PLAN.md, section 11) -------------------------------------

    async exportGraph(fmt) {
        if (!this.state.graph) {
            return;
        }
        if (fmt === 'png') {
            this._downloadDataUrl(this.renderer.exportPNG(), 'schema_explorer.png');
            return;
        }
        if (fmt === 'svg') {
            this._downloadBlob(new Blob([this.renderer.exportSVG()], { type: 'image/svg+xml' }), 'schema_explorer.svg');
            return;
        }
        const data = { options: JSON.stringify(this.optionsPayload) };
        if (fmt === 'html') {
            data.stories = JSON.stringify(this.state.stories.map((s) => ({ name: s.name, steps: s.steps })));
        }
        await download({ url: `/schema_explorer/export/${fmt}`, data });
    }

    get exportChoices() {
        return [
            { id: 'json', label: 'JSON' },
            { id: 'mermaid', label: 'Mermaid' },
            { id: 'dbml', label: 'DBML' },
            { id: 'markdown', label: 'Markdown' },
            { id: 'html', label: 'Standalone HTML' },
            { id: 'png', label: 'PNG' },
            { id: 'svg', label: 'SVG' },
        ];
    }

    _downloadDataUrl(dataUrl, filename) {
        const a = document.createElement('a');
        a.href = dataUrl;
        a.download = filename;
        a.click();
    }

    _downloadBlob(blob, filename) {
        const url = URL.createObjectURL(blob);
        this._downloadDataUrl(url, filename);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
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

    /** Access matrix + rules + field-level restrictions for the selected
     * node (PLAN.md, section 9.5 point 5). */
    get selectedNodeSecurity() {
        const node = this.selectedNode;
        const security = this.state.graph && this.state.graph.security;
        if (!node || !security) {
            return null;
        }
        return {
            access: security.access[node.id] || [],
            hasNoAccess: security.models_without_access.includes(node.id),
            rules: security.rules[node.id] || [],
            fieldGroups: security.field_groups.filter((fg) => fg.model === node.id),
        };
    }

    /** State/stage field values + best-effort transition guesses for the
     * selected node (PLAN.md, section 9.5 point 6 / section 8.4). */
    get selectedNodeLifecycle() {
        const node = this.selectedNode;
        const lifecycle = this.state.graph && this.state.graph.lifecycle;
        if (!node || !lifecycle) {
            return null;
        }
        return lifecycle.models.find((m) => m.model === node.id) || null;
    }

    // -- records panel (PLAN.md, section 9.5 point 8) ----------------------

    async loadSampleRecords() {
        const node = this.selectedNode;
        if (!node) {
            return;
        }
        this.state.records = { loading: true, error: null, data: null, forModel: node.id };
        try {
            const result = await this.orm.call("schema.explorer.service", "get_sample_records", [node.id]);
            this.state.records = { loading: false, error: null, data: result, forModel: node.id };
        } catch (error) {
            const message = (error && error.data && error.data.message) || String(error);
            this.state.records = { loading: false, error: message, data: null, forModel: node.id };
        }
    }

    get sampleRecords() {
        const node = this.selectedNode;
        if (!node || !this.state.records || this.state.records.forModel !== node.id) {
            return null;
        }
        return this.state.records;
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
