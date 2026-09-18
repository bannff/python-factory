"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import React, { useRef } from "react";
import { unwrapToolResult } from "../tool-result";
import { useBridge } from "../bridge-adapter-context";
function extractRows(data) {
    if (Array.isArray(data))
        return data;
    if (typeof data === "object" && data != null) {
        const obj = data;
        for (const key of ["items", "rows", "definitions", "results", "data", "entries"]) {
            if (Array.isArray(obj[key]))
                return obj[key];
        }
    }
    return [];
}
function formatCell(v) {
    if (v == null)
        return "—";
    if (typeof v === "boolean")
        return v ? "✓" : "✗";
    if (typeof v === "object")
        return JSON.stringify(v);
    return String(v);
}
export function LazyTabContent({ tab }) {
    const [data, setData] = React.useState(null);
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState(null);
    const fetched = useRef(false);
    const bridge = useBridge();
    React.useEffect(() => {
        if (!tab.lazy_tool || fetched.current)
            return;
        fetched.current = true;
        setLoading(true);
        bridge.callTool(tab.lazy_tool, {})
            .then((res) => {
            setData(unwrapToolResult(res));
        })
            .catch((err) => setError(err instanceof Error ? err.message : "Failed"))
            .finally(() => setLoading(false));
    }, [tab.lazy_tool, bridge]);
    if (loading) {
        return (_jsx("div", { className: "flex items-center justify-center py-8", children: _jsx("div", { className: "h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" }) }));
    }
    if (error)
        return _jsx("p", { className: "text-sm text-destructive", children: error });
    if (data == null)
        return _jsx("p", { className: "text-sm text-muted-foreground", children: "No data" });
    const hints = tab.result_hints;
    const prefer = hints?.prefer;
    const columns = hints?.columns;
    if ((prefer === "grouped_table" || prefer === "table") && columns?.length) {
        const rows = extractRows(data);
        return (_jsxs("div", { className: "w-full overflow-auto", children: [_jsxs("table", { className: "w-full caption-bottom text-sm", children: [_jsx("thead", { className: "[&_tr]:border-b", children: _jsx("tr", { children: columns.map((c) => (_jsx("th", { className: "h-10 px-4 text-left align-middle font-medium text-muted-foreground", children: c.label }, c.key))) }) }), _jsx("tbody", { className: "[&_tr:last-child]:border-0", children: rows.map((row, i) => (_jsx("tr", { className: "border-b transition-colors hover:bg-muted/50", children: columns.map((c) => (_jsx("td", { className: "p-4 align-middle", children: formatCell(row[c.key]) }, c.key))) }, i))) })] }), rows.length === 0 && _jsx("p", { className: "py-4 text-center text-sm text-muted-foreground", children: "No rows" })] }));
    }
    if (prefer === "stat_grid") {
        const entries = Object.entries(data);
        return (_jsx("div", { className: "grid grid-cols-2 gap-3 md:grid-cols-4", children: entries.map(([k, v]) => (_jsxs("div", { className: "rounded-lg border bg-card p-3", children: [_jsx("p", { className: "text-xs text-muted-foreground", children: k }), _jsx("p", { className: "text-lg font-semibold", children: formatCell(v) })] }, k))) }));
    }
    return (_jsx("pre", { className: "max-h-96 overflow-auto rounded-md bg-muted p-4 text-sm", children: typeof data === "string" ? data : JSON.stringify(data, null, 2) }));
}
