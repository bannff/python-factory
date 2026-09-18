"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useCallback, useEffect, useMemo } from "react";
import { cn } from "../lib/utils";
/* ── Color map: token → tailwind classes ── */
const PILL_COLORS = {
    blue: "bg-blue-500/10 text-blue-400",
    orange: "bg-orange-500/10 text-orange-400",
    emerald: "bg-emerald-500/10 text-emerald-400",
    purple: "bg-purple-500/10 text-purple-400",
    red: "bg-red-500/10 text-red-400",
    yellow: "bg-yellow-500/10 text-yellow-400",
    gray: "bg-gray-500/10 text-gray-400",
    indigo: "bg-indigo-500/10 text-indigo-400",
};
export function FilterBarInline({ values, colors, show_counts, counts, onFilter }) {
    const [active, setActive] = useState(null);
    const visibleValues = useMemo(() => {
        if (!values || values.length === 0)
            return [];
        if (!show_counts || !counts)
            return values;
        return values.filter((val) => (counts[val] ?? 0) > 0);
    }, [values, show_counts, counts]);
    useEffect(() => {
        if (!active)
            return;
        if (visibleValues.includes(active))
            return;
        setActive(null);
        onFilter?.(null);
    }, [active, onFilter, visibleValues]);
    const handleClick = useCallback((val) => {
        const next = active === val ? null : val;
        setActive(next);
        onFilter?.(next);
    }, [active, onFilter]);
    if (visibleValues.length <= 1)
        return null;
    return (_jsxs("div", { className: "flex flex-wrap items-center gap-3 text-[11px]", children: [_jsx("button", { onClick: () => handleClick(null), className: cn("border-b pb-0.5 font-medium tracking-[0.01em] transition-colors", active === null ? "border-foreground/30 text-foreground" : "border-transparent text-muted-foreground hover:text-foreground/80"), children: "All" }), visibleValues.map((val) => {
                const colorToken = colors?.[val] ?? "gray";
                const pillCls = PILL_COLORS[colorToken] ?? PILL_COLORS.gray;
                return (_jsxs("button", { onClick: () => handleClick(val), className: cn("inline-flex items-center gap-1.5 border-b pb-0.5 font-medium tracking-[0.01em] transition-colors", active === val ? "border-foreground/30 text-foreground" : "border-transparent text-muted-foreground hover:text-foreground/80"), children: [_jsx("span", { className: cn("h-1.5 w-1.5 rounded-full", pillCls.split(" ")[0].replace("text", "bg")) }), _jsx("span", { className: "capitalize", children: val }), show_counts && counts?.[val] != null ? _jsx("span", { className: "text-[10px] text-muted-foreground/70", children: counts[val] }) : null] }, val));
            })] }));
}
export function FilterBarRenderer({ node }) {
    const p = node.props;
    return _jsx(FilterBarInline, { ...p });
}
