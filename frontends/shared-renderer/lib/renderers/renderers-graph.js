"use client";
import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
import React, { useState, useCallback, useRef, useEffect, Suspense } from "react";
import { useGraphData } from "../lib/use-graph-data";
// React.lazy replaces next/dynamic(..., { ssr: false }). GraphViewer only
// renders under "use client" (no SSR pass), so a client-only lazy import is
// behaviour-equivalent to the old dynamic({ ssr: false }) (Track 6,
// bd:python-factory-ons71). react-force-graph-2d's default export is the
// component; cast keeps the permissive prop surface next/dynamic gave us.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph2D = React.lazy(() => import("react-force-graph-2d"));
/**
 * GraphViewerRenderer — renders a graph_viewer component from brick view JSON.
 * Reads data_tool / neighbors_tool from props, loads via MCP, renders ForceGraph2D.
 * Click a node to expand its neighbors. When a Run filter is selected, switches
 * to left-to-right DAG layout to render the workflow execution path.
 */
export function GraphViewerRenderer({ node }) {
    const { max_nodes = 100 } = node.props;
    const { data, loading, error, loadTopology, expandNode, reset, loadRunTopology, listRecentRuns, } = useGraphData();
    const [selected, setSelected] = useState(null);
    const [recentRuns, setRecentRuns] = useState([]);
    const [activeRunId, setActiveRunId] = useState("");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const graphRef = useRef(null);
    /* Auto-load on mount */
    useEffect(() => { loadTopology(); }, [loadTopology]);
    useEffect(() => {
        if (data.nodes.length > 0)
            setTimeout(() => graphRef.current?.zoomToFit(400, 40), 300);
    }, [data.nodes.length]);
    /* Refresh the run dropdown whenever the topology view is re-loaded */
    useEffect(() => {
        listRecentRuns(20).then(setRecentRuns).catch(() => { });
    }, [listRecentRuns]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handleClick = useCallback((n) => {
        setSelected(n);
        if (!activeRunId && data.nodes.length < max_nodes)
            expandNode(n.id);
    }, [expandNode, data.nodes.length, max_nodes, activeRunId]);
    const handleRunChange = useCallback((runId) => {
        setActiveRunId(runId);
        if (runId) {
            loadRunTopology(runId);
        }
        else {
            reset();
            loadTopology();
        }
    }, [loadRunTopology, loadTopology, reset]);
    return (_jsxs("div", { className: "rounded-lg border bg-card/30 overflow-hidden", style: { height: 480 }, children: [_jsxs("div", { className: "flex items-center justify-between border-b border-border/50 px-3 py-1.5", children: [_jsxs("span", { className: "text-xs font-medium text-muted-foreground", children: [data.nodes.length, " nodes \u00B7 ", data.links.length, " edges", loading && " · loading…", activeRunId && ` · run ${activeRunId.slice(0, 8)}`] }), _jsxs("div", { className: "flex gap-1 items-center", children: [_jsxs("select", { value: activeRunId, onChange: (e) => handleRunChange(e.target.value), className: "rounded border border-border/50 bg-background px-2 py-0.5 text-xs text-muted-foreground", title: "Filter by workflow run", children: [_jsx("option", { value: "", children: "All" }), recentRuns.map((r) => (_jsxs("option", { value: r.run_id, children: [r.run_id.slice(0, 8), " \u00B7 ", r.status] }, r.run_id)))] }), _jsx("button", { onClick: () => graphRef.current?.zoomToFit(400, 40), className: "rounded px-2 py-0.5 text-xs text-muted-foreground hover:bg-accent/50", children: "Fit" }), _jsx("button", { onClick: () => { setActiveRunId(""); reset(); loadTopology(); }, className: "rounded px-2 py-0.5 text-xs text-muted-foreground hover:bg-accent/50", children: "Reset" })] })] }), error && _jsx("div", { className: "px-3 py-1 text-xs text-destructive", children: error }), _jsxs("div", { className: "flex", style: { height: 440 }, children: [_jsx("div", { className: "flex-1", children: _jsx(Suspense, { fallback: null, children: _jsx(ForceGraph2D, { ref: graphRef, graphData: data, nodeLabel: "name", nodeColor: "color", nodeVal: "val", nodeRelSize: 5, linkDirectionalArrowLength: 3, linkDirectionalArrowRelPos: 1, linkLabel: "label", linkColor: () => "rgba(148,163,184,0.3)", onNodeClick: handleClick, backgroundColor: "rgba(0,0,0,0)", dagMode: activeRunId ? "lr" : undefined, dagLevelDistance: activeRunId ? 120 : undefined, d3VelocityDecay: activeRunId ? 0.4 : 0.4 }) }) }), selected && (_jsxs("div", { className: "w-52 border-l border-border/50 p-2 overflow-y-auto text-xs", children: [_jsxs("div", { className: "flex justify-between mb-1", children: [_jsx("span", { className: "font-semibold truncate", children: selected.name }), _jsx("button", { onClick: () => setSelected(null), className: "text-muted-foreground", children: "\u2715" })] }), _jsxs("div", { className: "text-muted-foreground space-y-0.5", children: [_jsxs("div", { children: ["Type: ", selected.type] }), _jsxs("div", { children: ["ID: ", selected.id] })] })] }))] })] }));
}
