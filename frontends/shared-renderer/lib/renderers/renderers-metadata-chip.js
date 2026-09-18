"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { cn } from "../lib/utils";
import { CopyChip, TipChip, PromptChip, PillsChip, ThresholdChip, scoreColor, fmtTime, } from "./renderers-metadata-chip-parts";
/* ── Main MetadataChip ── */
export function MetadataChip({ entry, val }) {
    const strVal = val != null ? String(val) : "";
    const renderAs = entry.render_as ?? "default";
    if (renderAs === "copy_id")
        return _jsx(CopyChip, { label: entry.label, value: strVal });
    if (renderAs === "model_chip") {
        const short = strVal.includes(".") ? strVal.split(".").slice(-2).join(".") : strVal;
        return _jsx(TipChip, { label: entry.label, short: short, full: strVal });
    }
    if (renderAs === "popover")
        return _jsx(PromptChip, { label: entry.label, value: strVal });
    if (renderAs === "pills") {
        const arr = Array.isArray(val) ? val.map(String) : [strVal];
        return _jsx(PillsChip, { label: entry.label, values: arr });
    }
    if (renderAs === "relative_time")
        return _jsx(TipChip, { label: entry.label, short: fmtTime(strVal), full: strVal });
    if (renderAs === "score") {
        const num = parseFloat(strVal);
        const display = isNaN(num) ? strVal : `${Math.round(num * 100)}%`;
        return (_jsxs("span", { className: "flex items-center gap-1", children: [_jsxs("span", { className: "text-muted-foreground/50", children: [entry.label, ":"] }), _jsx("span", { className: cn("font-semibold text-[11px]", !isNaN(num) && scoreColor(num)), children: display })] }));
    }
    if (renderAs === "threshold")
        return _jsx(ThresholdChip, { label: entry.label, val: val });
    return (_jsxs("span", { className: "flex items-center gap-1", children: [_jsxs("span", { className: "text-muted-foreground/50", children: [entry.label, ":"] }), _jsx("span", { className: "text-foreground/70", children: strVal })] }));
}
