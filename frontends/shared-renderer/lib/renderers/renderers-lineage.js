"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { AlertTriangle, Link2 } from "lucide-react";
import { cn } from "../lib/utils";
import { resolve } from "./renderers-item-list-utils";
import { useToolData } from "./use-tool-data";
const MAX_NODES = 100;
export function normalizeLineageData(raw) {
    const input = raw && typeof raw === "object" ? raw : {};
    const sourceNodes = Array.isArray(input.nodes) ? input.nodes : [];
    const nodes = [...sourceNodes]
        .filter((node) => typeof node?.node_id === "string")
        .sort((a, b) => a.node_id.localeCompare(b.node_id))
        .slice(0, MAX_NODES);
    const ids = new Set(nodes.map((node) => node.node_id));
    const sourceEdges = Array.isArray(input.edges) ? input.edges : [];
    const edges = sourceEdges
        .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
        .sort((a, b) => `${a.source}:${a.target}`.localeCompare(`${b.source}:${b.target}`));
    return {
        nodes,
        edges,
        missing_links: Array.isArray(input.missing_links)
            ? input.missing_links : [],
        truncated: input.truncated === true || sourceNodes.length > MAX_NODES,
        dropped_edges: sourceEdges.length - edges.length,
    };
}
function layersFor(data) {
    const byId = new Map(data.nodes.map((node) => [node.node_id, node]));
    const incoming = new Map(data.nodes.map((node) => [node.node_id, 0]));
    const outgoing = new Map(data.nodes.map((node) => [node.node_id, []]));
    data.edges.forEach((edge) => {
        incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
        outgoing.get(edge.source)?.push(edge.target);
    });
    const depth = new Map();
    const queue = [...byId.keys()].filter((id) => incoming.get(id) === 0).sort();
    queue.forEach((id) => depth.set(id, 0));
    while (queue.length) {
        const id = queue.shift();
        for (const target of (outgoing.get(id) ?? []).sort()) {
            depth.set(target, Math.max(depth.get(target) ?? 0, (depth.get(id) ?? 0) + 1));
            incoming.set(target, (incoming.get(target) ?? 1) - 1);
            if (incoming.get(target) === 0)
                queue.push(target);
        }
        queue.sort();
    }
    [...byId.keys()].filter((id) => !depth.has(id)).sort().forEach((id) => depth.set(id, 0));
    const layers = [];
    [...byId.values()].forEach((node) => {
        const index = depth.get(node.node_id) ?? 0;
        (layers[index] ?? (layers[index] = [])).push(node);
    });
    layers.forEach((layer) => layer.sort((a, b) => a.node_id.localeCompare(b.node_id)));
    return layers;
}
export function LineageRenderer({ node }) {
    const { data: staticData, data_tool, data_path, empty_message, className, } = node.props;
    const { data: toolData, loading, error } = useToolData(data_tool);
    const raw = data_tool ? toolData : staticData ?? node.props;
    const selected = data_path && raw && typeof raw === "object"
        ? resolve(raw, data_path) : raw;
    const data = normalizeLineageData(selected);
    const layers = layersFor(data);
    if (loading)
        return _jsx("div", { className: "h-48 animate-pulse rounded-lg border bg-muted/40" });
    if (error)
        return _jsx("p", { className: "rounded-lg border border-destructive/30 p-4 text-sm text-destructive", children: error });
    if (data.nodes.length === 0) {
        return _jsx("p", { className: "rounded-lg border border-dashed p-6 text-sm text-muted-foreground", children: empty_message ?? "No lineage evidence available." });
    }
    return (_jsxs("section", { className: cn("space-y-3 rounded-lg border p-4", className), children: [(data.truncated || data.dropped_edges > 0) && (_jsxs("div", { className: "flex items-center gap-2 text-xs text-amber-500", children: [_jsx(AlertTriangle, { className: "h-4 w-4" }), "Showing at most ", MAX_NODES, " nodes; ", data.dropped_edges, " dangling or truncated edges omitted."] })), _jsx("div", { className: "flex min-w-max items-start gap-6 overflow-x-auto", "data-testid": "lineage-layers", children: layers.map((layer, index) => (_jsx("div", { className: "w-56 shrink-0 space-y-2", "data-layer": index, children: layer.map((item) => (_jsxs("article", { className: "rounded-md border bg-card p-3", children: [_jsx("p", { className: "text-xs font-medium uppercase tracking-wide text-muted-foreground", children: item.entity_type ?? "Entity" }), _jsx("p", { className: "truncate text-sm font-semibold", title: item.source_ref, children: item.entity_id ?? item.source_ref ?? item.node_id }), _jsx("p", { className: "mt-1 text-xs text-muted-foreground", children: item.source }), item.evidence && _jsx("p", { className: "mt-2 text-xs", children: item.evidence })] }, item.node_id))) }, index))) }), _jsx("div", { className: "flex flex-wrap gap-2", children: data.edges.map((edge) => (_jsxs("span", { className: "inline-flex items-center gap-1 rounded bg-muted px-2 py-1 text-xs", children: [_jsx(Link2, { className: "h-3 w-3" }), edge.relation ?? "RELATED"] }, `${edge.source}:${edge.target}:${edge.relation}`))) }), data.missing_links.length > 0 && (_jsxs("div", { className: "text-xs text-muted-foreground", children: ["Missing links: ", data.missing_links.flatMap((item) => item.kinds ?? []).join(", ")] }))] }));
}
