"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { cn } from "../lib/utils";
import { SparklineInline } from "./renderers-sparkline";
import { useToolData } from "./use-tool-data";
import { MetadataChip } from "./renderers-metadata-chip";
import { ChartTabContent, AlertTabContent, ListTabContent, } from "./renderers-tab-content";
/* ── Tab content dispatcher ── */
function TabContent({ tab }) {
    if (tab.render_as === "chart" && tab.chart_props?.chart_type === "line") {
        return _jsx(ChartTabContent, { tab: tab }, tab.id);
    }
    if (tab.render_as === "alert") {
        return _jsx(AlertTabContent, { tab: tab }, tab.id);
    }
    if (tab.render_as === "list") {
        return _jsx(ListTabContent, { tab: tab }, tab.id);
    }
    return _jsx(RawJsonTabContent, { tab: tab }, tab.id);
}
function RawJsonTabContent({ tab }) {
    const { data, loading, error } = useToolData(tab.tool, tab.args);
    if (loading) {
        return (_jsxs("span", { className: "inline-flex items-center gap-1.5 text-[10px] text-muted-foreground/75", children: [_jsx(Loader2, { className: "h-3 w-3 animate-spin" }), "Loading"] }));
    }
    if (error)
        return _jsx("span", { className: "text-[10px] text-destructive", children: error });
    return (_jsx("pre", { className: "text-[10px] text-muted-foreground whitespace-pre-wrap", children: JSON.stringify(data, null, 2) }));
}
/* ── DetailPanel ── */
export function DetailPanelInline({ sparkline, metadata, tabs, item, resolveFn }) {
    const [activeTab, setActiveTab] = useState(null);
    const resolve = resolveFn ?? ((_o, p) => p);
    const activeTabSpec = tabs?.find((tab) => tab.id === activeTab) ?? null;
    const sparkData = sparkline?.data ??
        (sparkline?.data_path && item ? resolve(item, sparkline.data_path) : undefined);
    return (_jsx(motion.div, { initial: { height: 0, opacity: 0 }, animate: { height: "auto", opacity: 1 }, exit: { height: 0, opacity: 0 }, className: "overflow-hidden", children: _jsxs("div", { className: "px-3 pb-2 pt-1 space-y-2", children: [sparkline && (Array.isArray(sparkData) && sparkData.length > 0 ? (_jsx(SparklineInline, { data: sparkData, variant: sparkline?.variant, color: sparkline?.color, height: sparkline?.height, max_points: sparkline?.max_points })) : (_jsx("p", { className: "text-[10px] text-muted-foreground italic", children: "No data yet" }))), metadata && metadata.length > 0 && (() => {
                    const entries = metadata.map((m) => ({
                        ...m,
                        _val: m.value ?? (m.path && item ? resolve(item, m.path) : undefined),
                    })).filter((m) => m._val != null);
                    const config = entries.filter((m) => m.zone === "config" || (!m.zone && ["Model", "System Prompt", "Judges"].includes(m.label)));
                    const identity = entries.filter((m) => m.zone === "identity" || (!m.zone && !["Model", "System Prompt", "Judges"].includes(m.label)));
                    const hasZones = config.length > 0 && identity.length > 0;
                    return (_jsxs("div", { className: cn("flex gap-3 text-[11px] border-t border-border/30 pt-2", hasZones && "justify-between"), children: [_jsx("div", { className: "flex flex-wrap gap-x-3 gap-y-1 min-w-0", children: (hasZones ? config : entries).map((m) => (_jsx(MetadataChip, { entry: m, val: m._val }, m.label))) }), hasZones && identity.length > 0 && (_jsx("div", { className: "flex flex-wrap gap-x-3 gap-y-1 shrink-0 pl-3 border-l border-border/30", children: identity.map((m) => (_jsx(MetadataChip, { entry: m, val: m._val }, m.label))) }))] }));
                })(), tabs && tabs.length > 0 && (_jsxs("div", { className: "space-y-1", children: [_jsx("div", { className: "flex gap-1", children: tabs.map((t) => (_jsx("button", { onClick: () => setActiveTab(activeTab === t.id ? null : t.id), className: cn("rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors", activeTab === t.id
                                    ? "bg-muted text-foreground"
                                    : "text-muted-foreground hover:text-foreground"), children: t.label }, t.id))) }), activeTabSpec?.tool && (_jsx(TabContent, { tab: activeTabSpec }, activeTabSpec.id))] }))] }) }));
}
export function DetailPanelRenderer({ node }) {
    const p = node.props;
    return _jsx(DetailPanelInline, { ...p });
}
