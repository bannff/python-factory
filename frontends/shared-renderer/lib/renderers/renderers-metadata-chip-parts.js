"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "../lib/utils";
import * as Tooltip from "@radix-ui/react-tooltip";
import * as Collapsible from "@radix-ui/react-collapsible";
export const JUDGE_COLORS = {
    output: "bg-purple-500/15 text-purple-300",
    helpfulness: "bg-blue-500/15 text-blue-300",
    faithfulness: "bg-blue-500/15 text-blue-300",
    coherence: "bg-blue-500/15 text-blue-300",
    conciseness: "bg-blue-500/15 text-blue-300",
    harmfulness: "bg-blue-500/15 text-blue-300",
    response_relevance: "bg-blue-500/15 text-blue-300",
    tool_selection: "bg-blue-500/15 text-blue-300",
    tool_parameter: "bg-blue-500/15 text-blue-300",
    trajectory: "bg-emerald-500/15 text-emerald-300",
    interactions: "bg-emerald-500/15 text-emerald-300",
    goal_success: "bg-emerald-500/15 text-emerald-300",
};
export function scoreColor(v) {
    if (v >= 0.8)
        return "text-emerald-400";
    if (v >= 0.5)
        return "text-amber-400";
    return "text-red-400";
}
export function fmtTime(iso) {
    try {
        return new Date(iso).toLocaleString(undefined, {
            month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        });
    }
    catch {
        return iso;
    }
}
export function CopyChip({ label, value }) {
    const [copied, setCopied] = useState(false);
    const copy = () => {
        navigator.clipboard.writeText(value).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        });
    };
    return (_jsxs("span", { className: "flex items-center gap-1 group", children: [_jsxs("span", { className: "text-muted-foreground/50", children: [label, ":"] }), _jsx("span", { className: "font-mono text-foreground/70", children: value.slice(0, 12) }), _jsx("button", { onClick: copy, className: "opacity-0 group-hover:opacity-100 transition-opacity", children: copied ? _jsx(Check, { className: "h-2.5 w-2.5 text-emerald-400" }) : _jsx(Copy, { className: "h-2.5 w-2.5 text-muted-foreground/60 hover:text-foreground" }) })] }));
}
export function TipChip({ label, short, full }) {
    return (_jsx(Tooltip.Provider, { delayDuration: 300, children: _jsxs(Tooltip.Root, { children: [_jsx(Tooltip.Trigger, { asChild: true, children: _jsxs("span", { className: "flex items-center gap-1 cursor-default", children: [_jsxs("span", { className: "text-muted-foreground/50", children: [label, ":"] }), _jsx("span", { className: "font-mono bg-muted/40 rounded px-1 text-foreground/70 truncate max-w-[120px]", children: short })] }) }), _jsx(Tooltip.Portal, { children: _jsxs(Tooltip.Content, { className: "z-50 max-w-xs rounded bg-popover border border-border px-2 py-1 text-[10px] text-popover-foreground shadow-md break-all", sideOffset: 4, children: [full, _jsx(Tooltip.Arrow, { className: "fill-border" })] }) })] }) }));
}
export function PromptChip({ label, value }) {
    const [open, setOpen] = useState(false);
    const short = value.length > 55 ? value.slice(0, 55) + "…" : value;
    return (_jsx(Collapsible.Root, { open: open, onOpenChange: setOpen, children: _jsx(Collapsible.Trigger, { asChild: true, children: _jsxs("button", { className: "flex items-center gap-1 text-left group", children: [_jsxs("span", { className: "text-muted-foreground/50", children: [label, ":"] }), _jsx("span", { className: "text-foreground/70 group-hover:text-foreground transition-colors", children: open ? value : short })] }) }) }));
}
export function PillsChip({ label, values }) {
    return (_jsxs("span", { className: "flex items-center gap-1 flex-wrap", children: [_jsxs("span", { className: "text-muted-foreground/50", children: [label, ":"] }), values.map((v) => (_jsx("span", { className: cn("rounded-full px-1.5 py-0.5 text-[9px] font-medium", JUDGE_COLORS[v] ?? "bg-muted/40 text-muted-foreground"), children: v }, v)))] }));
}
export function ThresholdChip({ label, val }) {
    const obj = val && typeof val === "object" ? val : null;
    const warn = obj ? obj.warning : null;
    const crit = obj ? obj.critical : null;
    if (warn == null && crit == null) {
        return _jsxs("span", { className: "flex items-center gap-1", children: [_jsxs("span", { className: "text-muted-foreground/50", children: [label, ":"] }), _jsx("span", { className: "text-foreground/70", children: String(val) })] });
    }
    return (_jsxs("span", { className: "flex items-center gap-1", children: [_jsxs("span", { className: "text-muted-foreground/50", children: [label, ":"] }), warn != null && _jsxs("span", { className: "flex items-center gap-0.5 text-amber-400 font-semibold", children: [_jsx("span", { className: "text-[9px]", children: "\u26A0" }), String(warn)] }), warn != null && crit != null && _jsx("span", { className: "text-muted-foreground/30", children: "/" }), crit != null && _jsxs("span", { className: "flex items-center gap-0.5 text-red-400 font-semibold", children: [_jsx("span", { className: "text-[9px]", children: "\u2717" }), String(crit)] })] }));
}
