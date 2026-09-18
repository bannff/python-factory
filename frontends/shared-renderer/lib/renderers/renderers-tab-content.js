"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Loader2 } from "lucide-react";
import { cn } from "../lib/utils";
import { useToolData } from "./use-tool-data";
import { resolve } from "./renderers-item-list-utils";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, } from "recharts";
function InlineLoading() {
    return (_jsxs("span", { className: "inline-flex items-center gap-1.5 text-[10px] text-muted-foreground/75", children: [_jsx(Loader2, { className: "h-3 w-3 animate-spin" }), "Loading"] }));
}
/* ── Chart tab ── */
export function ChartTabContent({ tab }) {
    const { data, loading, error } = useToolData(tab.tool, tab.args);
    if (loading)
        return _jsx(InlineLoading, {});
    if (error)
        return _jsx("span", { className: "text-[10px] text-destructive", children: error });
    const cp = tab.chart_props ?? {};
    const raw = data;
    const buckets = Array.isArray(raw?.buckets)
        ? raw.buckets
        : [];
    if (buckets.length === 0 && cp.empty_message) {
        return _jsx("p", { className: "text-[10px] text-muted-foreground/60 italic py-1", children: cp.empty_message });
    }
    return (_jsx(ResponsiveContainer, { width: "100%", height: cp.height ?? 120, children: _jsxs(LineChart, { data: buckets, children: [_jsx(XAxis, { dataKey: cp.x_key ?? "start", tick: { fontSize: 9 }, tickFormatter: (v) => {
                        const ms = typeof v === "number" && v < 1e12 ? v * 1000 : v;
                        return new Date(ms).toLocaleDateString(undefined, { month: "short", day: "numeric" });
                    } }), _jsx(YAxis, { tick: { fontSize: 9 }, width: 28 }), _jsx(Tooltip, { contentStyle: { fontSize: 10 } }), _jsx(Line, { type: "monotone", dataKey: cp.y_key ?? "value", stroke: cp.color ?? "#6366f1", dot: false, strokeWidth: 1.5 })] }) }));
}
/* ── Alert tab ── */
const INTENT_STYLES = {
    warning: "bg-yellow-500/10 border border-yellow-500/30 text-yellow-400",
    success: "bg-emerald-500/10 border border-emerald-500/30 text-emerald-400",
};
const INTENT_MESSAGES = {
    warning: "Drift detected — metric has shifted significantly",
    success: "No drift detected — metric is stable",
};
export function AlertTabContent({ tab }) {
    const { data, loading, error } = useToolData(tab.tool, tab.args);
    if (loading)
        return _jsx(InlineLoading, {});
    if (error)
        return _jsx("span", { className: "text-[10px] text-destructive", children: error });
    const ap = tab.alert_props ?? {};
    const raw = data;
    const boolVal = raw && ap.intent_field ? Boolean(raw[ap.intent_field]) : false;
    const intentKey = boolVal ? "true" : "false";
    const intent = ap.intent_map?.[intentKey] ?? (boolVal ? "warning" : "success");
    const message = INTENT_MESSAGES[intent] ?? intent;
    return (_jsx("div", { className: cn("rounded px-2 py-1 text-[10px]", INTENT_STYLES[intent] ?? INTENT_STYLES.success), children: message }));
}
/* ── List tab ── */
export function ListTabContent({ tab }) {
    const { data, loading, error } = useToolData(tab.tool, tab.args);
    if (loading)
        return _jsx(InlineLoading, {});
    if (error)
        return _jsx("span", { className: "text-[10px] text-destructive", children: error });
    const raw = data;
    const pathData = tab.data_path && raw ? resolve(raw, tab.data_path) : undefined;
    const arr = Array.isArray(pathData) ? pathData
        : Array.isArray(raw) ? raw
            : Array.isArray(raw?.runs) ? raw.runs
                : Array.isArray(raw?.case_results) ? raw.case_results
                    : Array.isArray(raw?.moves) ? raw.moves
                        : Array.isArray(raw?.transactions) ? raw.transactions
                            : Array.isArray(raw?.bounties) ? raw.bounties
                                : Array.isArray(raw?.items) ? raw.items
                                    : null;
    if (!arr || arr.length === 0) {
        return _jsx("p", { className: "text-[10px] text-muted-foreground italic", children: tab.empty_message ?? "No items" });
    }
    return (_jsx("div", { className: "space-y-0.5", children: arr.map((item, i) => {
            const r = item;
            const label = String(r.case_name
                ?? r.name
                ?? r.id
                ?? r.filename
                ?? r.tx_id
                ?? r.bounty_id
                ?? (r.action ? `${r.player != null ? `P${r.player} · ` : ""}${String(r.action).replaceAll("_", " ")}` : undefined)
                ?? (r.step != null ? `Step ${r.step}` : undefined)
                ?? `item-${i}`);
            const score = r.score != null ? `${Math.round(Number(r.score) * 100)}%` : "";
            const reason = typeof r.reason === "string"
                ? r.reason
                : typeof r.evidence === "string"
                    ? r.evidence
                    : typeof r.memo === "string"
                        ? r.memo
                        : "";
            const isError = reason.includes("Exception") || reason.includes("error:") || reason.includes("Error");
            const verdict = isError ? "⚠" : r.passed === true ? "✓" : r.passed === false ? "✗" : "";
            const verdictColor = isError
                ? "text-orange-400"
                : r.passed === true ? "text-emerald-400" : r.passed === false ? "text-red-400" : "";
            const sub = score
                || (r.status ?? r.phase ?? (r.column != null ? `column ${r.column}` : ""));
            return (_jsxs("div", { className: "py-1 border-b border-border/10 last:border-0", children: [_jsxs("div", { className: "flex items-center gap-2 text-[10px] text-muted-foreground", children: [_jsx("span", { className: cn("shrink-0 font-medium", verdictColor), children: verdict }), _jsx("span", { className: "text-foreground/70 font-mono flex-1 truncate", children: label }), sub && _jsx("span", { className: "text-muted-foreground/60 shrink-0", children: String(sub) })] }), reason && (_jsx("p", { className: "mt-0.5 ml-4 text-[10px] text-muted-foreground/70 line-clamp-2 border-l-2 border-indigo-500/20 pl-2", children: reason }))] }, i));
        }) }));
}
