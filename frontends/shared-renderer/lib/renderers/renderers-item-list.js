"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useRef, useMemo } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { useBridge } from "../bridge-adapter-context";
import { useToolData } from "./use-tool-data";
import { FilterBarInline } from "./renderers-filter-bar";
import { ItemRow } from "./renderers-item-row";
import { ViewIcon, resolveIcon, isPictograph } from "./renderers-icon";
import { resolve, extractArray } from "./renderers-item-list-utils";
/* ── Subtitle icon (header) ── */
function HeaderIcon({ name }) {
    return _jsx(ViewIcon, { name: name, className: "h-4 w-4 text-indigo-500" });
}
/* ── Empty state ── */
function EmptyState({ icon, message }) {
    const hasIcon = Boolean(icon && (resolveIcon(icon) || isPictograph(icon)));
    return (_jsxs(motion.div, { initial: { opacity: 0 }, animate: { opacity: 1 }, className: "flex h-full flex-col items-center justify-center gap-3 text-center", children: [hasIcon && (_jsx("div", { className: "flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-500/10", children: _jsx(ViewIcon, { name: icon, className: "h-6 w-6 text-indigo-500/50", textClassName: "text-xl" }) })), _jsx("p", { className: "max-w-lg text-sm text-muted-foreground", children: message ?? "No items found." })] }));
}
/* ── Main component ── */
export function ItemListRenderer({ node }) {
    const p = node.props;
    const { data_tool, data_path, item_key = "id", filters, item_layout, detail } = p;
    const bridge = useBridge();
    const { data: rawData, loading, error } = useToolData(data_tool, {}, { refreshMs: p.refresh_ms });
    const items = useMemo(() => extractArray(rawData, data_path), [rawData, data_path]);
    const { data: statsRaw } = useToolData(p.header?.stats_tool, {}, { refreshMs: p.refresh_ms });
    // Snapshot enrichment
    const [snapshots, setSnapshots] = useState({});
    const snapshotFetched = useRef(false);
    useEffect(() => {
        if (!p.item_snapshot_tool || items.length === 0 || snapshotFetched.current)
            return;
        snapshotFetched.current = true;
        const map = {};
        const fetches = items.map((item) => {
            const args = {};
            if (p.item_snapshot_args) {
                for (const [k, v] of Object.entries(p.item_snapshot_args)) {
                    args[k] = resolve(item, v);
                }
            }
            const key = String(item[item_key] ?? "");
            return bridge.callTool(p.item_snapshot_tool, args)
                .then((r) => { map[key] = (r.result ?? r); })
                .catch(() => { });
        });
        Promise.all(fetches).then(() => setSnapshots({ ...map }));
    }, [items, p.item_snapshot_tool, p.item_snapshot_args, item_key, bridge]);
    const enrichedItems = useMemo(() => {
        if (!p.snapshot_merge_path || Object.keys(snapshots).length === 0)
            return items;
        return items.map((item) => {
            const key = String(item[item_key] ?? "");
            const snap = snapshots[key];
            return snap ? { ...item, [p.snapshot_merge_path]: snap } : item;
        });
    }, [items, snapshots, p.snapshot_merge_path, item_key]);
    // Filter
    const [filterValue, setFilterValue] = useState(null);
    const filtered = useMemo(() => {
        if (!filterValue || !filters?.field)
            return enrichedItems;
        return enrichedItems.filter((item) => item[filters.field] === filterValue);
    }, [enrichedItems, filterValue, filters?.field]);
    const filterCounts = useMemo(() => {
        if (!filters?.field || !filters.show_counts)
            return undefined;
        const counts = {};
        for (const item of enrichedItems) {
            const v = String(item[filters.field] ?? "");
            counts[v] = (counts[v] ?? 0) + 1;
        }
        return counts;
    }, [enrichedItems, filters?.field, filters?.show_counts]);
    const [expandedId, setExpandedId] = useState(null);
    const emptyMessage = useMemo(() => {
        if (enrichedItems.length > 0 && filterValue) {
            return `No runs match ${filterValue}.`;
        }
        return p.empty_message;
    }, [enrichedItems.length, filterValue, p.empty_message]);
    const statsText = useMemo(() => {
        if (!p.header?.stats_map || !statsRaw)
            return "";
        const parts = [];
        for (const [label, path] of Object.entries(p.header.stats_map)) {
            const v = resolve(statsRaw, path);
            if (v != null)
                parts.push(`${v} ${label}`);
        }
        return parts.join(" · ");
    }, [statsRaw, p.header?.stats_map]);
    const badgeColorMap = useMemo(() => {
        if (!item_layout?.badge?.color_map)
            return filters?.colors ?? {};
        if (item_layout.badge.color_map === "filters.colors")
            return filters?.colors ?? {};
        return {};
    }, [item_layout?.badge?.color_map, filters?.colors]);
    return (_jsxs("div", { className: "flex h-full flex-col", children: [_jsxs("div", { className: "flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border/50 bg-card/10 px-4 py-2", children: [_jsx(HeaderIcon, { name: p.header?.icon }), statsText && _jsx("span", { className: "text-xs font-medium text-muted-foreground", children: statsText }), filters && (_jsx("div", { className: "ml-auto max-w-full", children: _jsx(FilterBarInline, { values: filters.values, colors: filters.colors, show_counts: filters.show_counts, counts: filterCounts, onFilter: setFilterValue }) }))] }), _jsx("div", { className: "flex-1 overflow-auto p-4", children: loading ? (_jsx("div", { className: "flex h-full items-center justify-center", children: _jsx(Loader2, { className: "h-5 w-5 animate-spin text-muted-foreground" }) })) : error ? (_jsx("p", { className: "text-sm text-destructive text-center py-8", children: error })) : filtered.length > 0 ? (_jsx("div", { className: "space-y-2", children: filtered.map((item) => {
                        const key = String(item[item_key] ?? "");
                        const isExpanded = expandedId === key;
                        return _jsx(ItemRow, { item: item, itemKey: key, layout: item_layout, detail: detail, badgeColorMap: badgeColorMap, isExpanded: isExpanded, onToggle: () => setExpandedId(isExpanded ? null : key) }, key);
                    }) })) : (_jsx(EmptyState, { icon: p.empty_icon, message: emptyMessage })) })] }));
}
