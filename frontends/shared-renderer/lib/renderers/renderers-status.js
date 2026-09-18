"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { cn } from "../lib/utils";
/* ── Color maps ── */
const DOT_COLORS = {
    emerald: "bg-emerald-500",
    yellow: "bg-yellow-500",
    red: "bg-red-500",
    blue: "bg-blue-500",
    gray: "bg-gray-500/30",
    "blue-pulse": "bg-blue-500 animate-pulse",
};
const TREND_COLORS = {
    up: { char: "↑", cls: "text-emerald-400" },
    down: { char: "↓", cls: "text-red-400" },
    flat: { char: "→", cls: "text-muted-foreground" },
};
function resolveColor(props) {
    const { value, thresholds, states, state } = props;
    // State-based (e.g. "completed" → "emerald")
    if (state != null && states)
        return DOT_COLORS[states[state] ?? "gray"] ?? DOT_COLORS.gray;
    // Threshold-based
    if (value == null)
        return DOT_COLORS.gray;
    const warn = thresholds?.warning;
    const crit = thresholds?.critical;
    if (warn != null && value >= warn)
        return DOT_COLORS.emerald;
    if (crit != null && value >= crit)
        return DOT_COLORS.yellow;
    if (crit != null && value < crit)
        return DOT_COLORS.red;
    return DOT_COLORS.emerald;
}
export function StatusDotInline(props) {
    return _jsx("span", { className: cn("h-2 w-2 rounded-full shrink-0", resolveColor(props)) });
}
export function StatusDotRenderer({ node }) {
    const p = node.props;
    return _jsx(StatusDotInline, { ...p });
}
export function TrendBadgeInline({ direction, change_pct, positive_is_good = true }) {
    const dir = direction ?? "flat";
    const base = TREND_COLORS[dir] ?? TREND_COLORS.flat;
    // Flip colors when positive_is_good is false
    const flip = !positive_is_good && dir !== "flat";
    const cls = flip
        ? dir === "up" ? "text-red-400" : "text-emerald-400"
        : base.cls;
    return (_jsxs("span", { className: "flex items-center gap-1 shrink-0", children: [_jsx("span", { className: cn("text-xs", cls), children: base.char }), change_pct != null && (_jsxs("span", { className: "text-[10px] text-muted-foreground", children: [change_pct > 0 ? "+" : "", change_pct, "%"] }))] }));
}
export function TrendBadgeRenderer({ node }) {
    const p = node.props;
    return _jsx(TrendBadgeInline, { ...p });
}
