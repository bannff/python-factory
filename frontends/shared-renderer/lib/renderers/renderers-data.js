"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Card, CardHeader, CardTitle, CardContent, } from "../ui/card";
import { Badge } from "../ui/badge";
import { cn } from "../lib/utils";
import { useToolData } from "./use-tool-data";
/* TableRenderer */
export function TableRenderer({ node }) {
    const { columns = [], rows = [], className } = node.props;
    return (_jsx("div", { className: cn("w-full overflow-auto", className), children: _jsxs("table", { className: "w-full caption-bottom text-sm", children: [_jsx("thead", { className: "[&_tr]:border-b", children: _jsx("tr", { className: "border-b transition-colors hover:bg-muted/50", children: columns.map((col) => (_jsx("th", { className: "h-12 px-4 text-left align-middle font-medium text-muted-foreground", children: col.label }, col.key))) }) }), _jsx("tbody", { className: "[&_tr:last-child]:border-0", children: rows.map((row, i) => (_jsx("tr", { className: "border-b transition-colors hover:bg-muted/50", children: columns.map((col) => (_jsx("td", { className: "p-4 align-middle", children: String(row[col.key] ?? "") }, col.key))) }, i))) })] }) }));
}
/* ChartRenderer */
function extractChartData(raw) {
    if (Array.isArray(raw))
        return raw;
    if (typeof raw === "object" && raw != null) {
        const obj = raw;
        for (const key of ["buckets", "data", "result", "items", "series"]) {
            if (Array.isArray(obj[key]))
                return obj[key];
        }
    }
    return [];
}
export function ChartRenderer({ node }) {
    const { data: staticData = [], data_tool, xKey = "name", yKey = "value", title, empty_state, className, } = node.props;
    const { data: toolResult, loading, error } = useToolData(data_tool);
    // bd:python-factory-lbvkh — defensive: if the agent emits a malformed
    // Chart payload (e.g. ``data: "not-an-array"``) or ``data_tool``
    // extraction returns a non-array shape we don't recognize, render the
    // empty state instead of letting ``.filter`` throw and nuke the whole
    // chat panel through React's error boundary. Combined with the
    // <InlineView> ErrorBoundary added in the same bd, a single bad
    // producer can no longer require a full page reload.
    const rawData = data_tool ? extractChartData(toolResult) : staticData;
    const dataArr = Array.isArray(rawData) ? rawData : [];
    if (!Array.isArray(rawData) && rawData != null) {
        // Soft warn — surface in devtools without crashing the panel.
        // eslint-disable-next-line no-console
        console.warn("[ChartRenderer] expected array data; got", typeof rawData, "— rendering empty state");
    }
    // Filter out null-value buckets (metrics trend API returns many)
    const data = dataArr.filter((d) => d != null && d[yKey] != null);
    const maxVal = Math.max(1, ...data.map((d) => Number(d[yKey] ?? 0)));
    if (loading) {
        return (_jsxs(Card, { className: className, children: [title && _jsx(CardHeader, { children: _jsx(CardTitle, { className: "text-base", children: title }) }), _jsx(CardContent, { children: _jsx("div", { className: "flex items-end gap-2 h-40 animate-pulse", children: Array.from({ length: 6 }).map((_, i) => (_jsx("div", { className: "flex-1 rounded-t bg-muted", style: { height: `${20 + Math.random() * 60}%` } }, i))) }) })] }));
    }
    return (_jsxs(Card, { className: className, children: [title && _jsx(CardHeader, { children: _jsx(CardTitle, { className: "text-base", children: title }) }), _jsxs(CardContent, { children: [error && _jsx("p", { className: "text-sm text-destructive mb-2", children: error }), data.length === 0 ? (_jsx("p", { className: "text-sm text-muted-foreground", children: empty_state ?? "No chart data" })) : (_jsx("div", { className: "flex items-end gap-2 h-40", children: data.map((d, i) => {
                            const val = Number(d[yKey] ?? 0);
                            return (_jsxs("div", { className: "flex flex-col items-center flex-1 gap-1", children: [_jsx("span", { className: "text-xs text-muted-foreground", children: val }), _jsx("div", { className: "w-full rounded-t bg-primary transition-all", style: { height: `${(val / maxVal) * 100}%` } }), _jsx("span", { className: "text-xs text-muted-foreground truncate max-w-full", children: String(d[xKey] ?? "") })] }, i));
                        }) }))] })] }));
}
/* ImageRenderer */
export function ImageRenderer({ node }) {
    // bd:python-factory-3hkqx — agent emits arbitrary external/data: URLs
    // (picsum, dicebear, base64, etc.). next/image needs every host
    // pre-configured in next.config.js, so we use a plain <img> here to
    // accept any source the agent produces. Lazy-load + decode async to
    // keep the perf hit minimal. Renderer canary in
    // ``__tests__/renderers-prop-aliases.test.tsx`` pins the contract.
    const { src, alt = "", width = 400, height = 300, className } = node.props;
    if (!src) {
        return (_jsx("div", { className: "flex h-32 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground", children: "No image source" }));
    }
    // eslint-disable-next-line @next/next/no-img-element
    return (_jsx("img", { src: src, alt: alt, width: width, height: height, loading: "lazy", decoding: "async", className: cn("rounded-md", className) }));
}
/* CodeRenderer */
export function CodeRenderer({ node }) {
    const { code = "", language = "", title, className } = node.props;
    return (_jsxs("div", { className: cn("rounded-md border", className), children: [(title || language) && (_jsxs("div", { className: "flex items-center justify-between border-b bg-muted px-4 py-2", children: [title && _jsx("span", { className: "text-sm font-medium", children: title }), language && _jsx(Badge, { variant: "secondary", children: language })] })), _jsx("pre", { className: "overflow-auto p-4", children: _jsx("code", { className: "text-sm", children: code }) })] }));
}
/* TimelineRenderer */
export function TimelineRenderer({ node }) {
    const { items = [], className } = node.props;
    return (_jsx("div", { className: cn("relative ml-3 border-l border-border pl-6 space-y-6", className), children: items.map((item, i) => (_jsxs("div", { className: "relative", children: [_jsx("div", { className: "absolute -left-[31px] top-1 h-3 w-3 rounded-full border-2 border-primary bg-background" }), _jsxs("div", { className: "space-y-1", children: [_jsxs("div", { className: "flex items-center gap-2", children: [_jsx("span", { className: "font-medium text-sm", children: item.title }), item.status && _jsx(Badge, { variant: "outline", children: item.status })] }), item.description && _jsx("p", { className: "text-sm text-muted-foreground", children: item.description }), item.time && _jsx("p", { className: "text-xs text-muted-foreground", children: item.time })] })] }, i))) }));
}
