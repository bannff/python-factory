"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useCallback } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { Select } from "../ui/select";
import { cn } from "../lib/utils";
import { LazyTabContent } from "./renderers-lazy-tab";
import { asActionRef } from "../actions/action-ref";
import { useAction } from "../actions/use-action";
/**
 * bd:372an — this used to raw-`fetch("/api/tools/${tool}")` with `formData` as
 * the body, bypassing the BridgeAdapter seam and carrying no envelope, no
 * thread/run correlation and no transcript entry. It now dispatches through
 * `useAction`. The `action` prop carries an `ActionRef`; the server normalizes
 * legacy `props.tool` into it at ingestion, so the 18 live brick-declared
 * forms keep working with no brick edit.
 */
export function FormRenderer({ node }) {
    const { action, action_error, fields = [], submit_label = "Submit", className } = node.props;
    const ref = asActionRef(action);
    const [formData, setFormData] = useState(() => {
        const init = {};
        for (const f of fields)
            init[f.name] = f.value ?? (f.type === "number" || f.type === "range" ? 0 : "");
        return init;
    });
    const { dispatch, pending, error: dispatchError, result } = useAction();
    const [confirming, setConfirming] = useState(false);
    const error = action_error ?? dispatchError;
    const handleChange = useCallback((name, value) => {
        setFormData((prev) => ({ ...prev, [name]: value }));
    }, []);
    const handleSubmit = useCallback(async (e) => {
        e.preventDefault();
        if (!ref)
            return;
        if (ref.confirm && !confirming) {
            setConfirming(true);
            return;
        }
        setConfirming(false);
        await dispatch(ref, formData, formData);
    }, [ref, confirming, dispatch, formData]);
    const renderField = (field) => {
        const val = formData[field.name];
        const lbl = field.label ?? field.name;
        switch (field.type) {
            case "textarea":
                return (_jsxs("div", { className: "space-y-2", children: [_jsx("label", { className: "text-sm font-medium", children: lbl }), _jsx(Textarea, { placeholder: field.placeholder, value: String(val ?? ""), onChange: (e) => handleChange(field.name, e.target.value) })] }, field.name));
            case "select":
                return (_jsxs("div", { className: "space-y-2", children: [_jsx("label", { className: "text-sm font-medium", children: lbl }), _jsx(Select, { options: field.options ?? [], value: String(val ?? ""), onChange: (e) => handleChange(field.name, e.target.value) })] }, field.name));
            case "range":
                return (_jsxs("div", { className: "space-y-2", children: [_jsxs("label", { className: "text-sm font-medium", children: [lbl, ": ", String(val)] }), _jsx("input", { type: "range", min: field.min ?? 0, max: field.max ?? 100, value: Number(val ?? 0), onChange: (e) => handleChange(field.name, Number(e.target.value)), className: "w-full accent-primary" })] }, field.name));
            case "number":
                return (_jsxs("div", { className: "space-y-2", children: [_jsx("label", { className: "text-sm font-medium", children: lbl }), _jsx(Input, { type: "number", placeholder: field.placeholder, min: field.min, max: field.max, value: String(val ?? ""), onChange: (e) => handleChange(field.name, Number(e.target.value)) })] }, field.name));
            default:
                return (_jsxs("div", { className: "space-y-2", children: [_jsx("label", { className: "text-sm font-medium", children: lbl }), _jsx(Input, { type: "text", placeholder: field.placeholder, value: String(val ?? ""), onChange: (e) => handleChange(field.name, e.target.value) })] }, field.name));
        }
    };
    return (_jsxs("form", { onSubmit: handleSubmit, className: cn("space-y-4", className), children: [fields.map(renderField), _jsx(Button, { type: "submit", variant: confirming ? "destructive" : "default", disabled: pending || !ref, "aria-busy": pending || undefined, children: pending ? "Submitting…" : confirming ? `Confirm: ${submit_label}` : submit_label }), error && (_jsx("div", { role: "alert", className: "rounded-md border border-destructive/50 p-3 text-sm text-destructive", children: error })), result !== null && result !== undefined && (_jsx("pre", { className: "mt-2 max-h-64 overflow-auto rounded-md bg-muted p-4 text-sm", children: typeof result === "string" ? result : JSON.stringify(result, null, 2) }))] }));
}
/* TabsRenderer */
export function TabsRenderer({ node, renderChildren }) {
    const { tabs = [], className } = node.props;
    const [active, setActive] = useState(tabs[0]?.id ?? "");
    const activeTab = tabs.find((t) => t.id === active);
    const matchedChild = node.children?.find((c) => c.id === active);
    return (_jsxs("div", { className: cn("space-y-2", className), children: [_jsx("div", { className: "inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground", children: tabs.map((tab) => (_jsx("button", { onClick: () => setActive(tab.id), className: cn("inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all", active === tab.id && "bg-background text-foreground shadow-sm"), children: tab.label }, tab.id))) }), _jsx("div", { className: "rounded-md border p-4", children: matchedChild
                    ? renderChildren(node.children.filter((c) => c.id === active))
                    : activeTab?.lazy_tool
                        ? _jsx(LazyTabContent, { tab: activeTab }, active)
                        : _jsxs("p", { className: "text-sm text-muted-foreground", children: ["Tab: ", active] }) })] }));
}
/* BreadcrumbRenderer */
export function BreadcrumbRenderer({ node }) {
    const { items = [], className } = node.props;
    return (_jsx("nav", { "aria-label": "Breadcrumb", className: className, children: _jsx("ol", { className: "flex items-center gap-1.5 text-sm text-muted-foreground", children: items.map((item, i) => (_jsxs("li", { className: "flex items-center gap-1.5", children: [i > 0 && _jsx("span", { className: "text-muted-foreground/50", children: "/" }), item.href
                        ? _jsx("a", { href: item.href, className: "hover:text-foreground transition-colors", children: item.label })
                        : _jsx("span", { className: i === items.length - 1 ? "text-foreground font-medium" : "", children: item.label })] }, i))) }) }));
}
