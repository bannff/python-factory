"use client";
import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import React, { useState } from "react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, } from "../ui/card";
import { Button } from "../ui/button";
import { cn } from "../lib/utils";
import { ViewIcon } from "./renderers-icon";
/* DialogRenderer */
export function DialogRenderer({ node, renderChildren }) {
    const { title, description, open: initialOpen = false, className } = node.props;
    const [open, setOpen] = useState(initialOpen);
    if (!open) {
        return _jsx(Button, { variant: "outline", onClick: () => setOpen(true), children: title ?? "Open Dialog" });
    }
    return (_jsxs(_Fragment, { children: [_jsx("div", { className: "fixed inset-0 z-50 bg-black/80", onClick: () => setOpen(false) }), _jsxs("div", { className: cn("fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-6 shadow-lg", className), children: [title && _jsx("h2", { className: "text-lg font-semibold", children: title }), description && _jsx("p", { className: "mt-1 text-sm text-muted-foreground", children: description }), _jsx("div", { className: "mt-4", children: renderChildren(node.children) }), _jsx("button", { onClick: () => setOpen(false), className: "absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100", "aria-label": "Close", children: "\u2715" })] })] }));
}
/* ToastRenderer */
export function ToastRenderer({ node }) {
    const { message, variant = "default", duration = 4000 } = node.props;
    const [visible, setVisible] = useState(true);
    React.useEffect(() => {
        const timer = setTimeout(() => setVisible(false), duration);
        return () => clearTimeout(timer);
    }, [duration]);
    if (!visible)
        return null;
    return (_jsx("div", { className: cn("fixed bottom-4 right-4 z-50 rounded-md border bg-background px-6 py-4 shadow-lg transition-all", variant === "destructive" && "border-destructive text-destructive"), children: _jsx("p", { className: "text-sm", children: message ?? "Notification" }) }));
}
/* PageRenderer — 3-zone layout */
export function PageRenderer({ node, renderChildren }) {
    const { title, subtitle, icon, gradient = "from-blue-500 to-indigo-600", tooltip, className } = node.props;
    const children = node.children ?? [];
    const infoChildren = children.filter((c) => c.props.zone === "info");
    const controlChildren = children.filter((c) => c.props.zone === "controls");
    const outputChildren = children.filter((c) => !c.props.zone || (c.props.zone !== "info" && c.props.zone !== "controls"));
    return (_jsxs("div", { className: cn("space-y-6", className), children: [_jsx("div", { className: cn("rounded-lg bg-gradient-to-r p-6 text-white", gradient), title: tooltip, children: _jsxs("div", { className: "flex items-center gap-3", children: [_jsx(ViewIcon, { name: icon, className: "h-7 w-7", textClassName: "text-3xl" }), _jsxs("div", { children: [title && _jsx("h1", { className: "text-2xl font-bold", children: title }), subtitle && _jsx("p", { className: "mt-1 text-white/80", children: subtitle })] })] }) }), (infoChildren.length > 0 || controlChildren.length > 0) && (_jsxs("div", { className: "grid gap-4 md:grid-cols-2 lg:grid-cols-4", children: [renderChildren(infoChildren), controlChildren.length > 0 && _jsx("div", { className: "lg:col-span-4", children: renderChildren(controlChildren) })] })), outputChildren.length > 0 && _jsx("div", { className: "space-y-4", children: renderChildren(outputChildren) })] }));
}
function TreeItem({ node, depth = 0 }) {
    const [expanded, setExpanded] = useState(depth < 2);
    const hasChildren = (node.children?.length ?? 0) > 0;
    return (_jsxs("div", { style: { paddingLeft: depth > 0 ? 16 : 0 }, children: [_jsxs("button", { onClick: () => hasChildren && setExpanded(!expanded), className: cn("flex items-center gap-1.5 py-1 text-sm hover:text-foreground", hasChildren ? "text-foreground cursor-pointer" : "text-muted-foreground cursor-default"), children: [hasChildren && _jsx("span", { className: "text-xs", children: expanded ? "▼" : "▶" }), !hasChildren && _jsx("span", { className: "text-xs ml-3", children: "\u2022" }), node.label] }), expanded && node.children?.map((child, i) => _jsx(TreeItem, { node: child, depth: depth + 1 }, i))] }));
}
export function TreeRenderer({ node }) {
    const { nodes = [], className } = node.props;
    return (_jsx("div", { className: cn("rounded-md border p-3", className), children: nodes.map((n, i) => _jsx(TreeItem, { node: n }, i)) }));
}
/* SpacerRenderer / DividerRenderer (bd:python-factory-3hkqx round 3 —
   meta-architect verdict cec79d55, fills missing PascalCase renderers) */
export function SpacerRenderer({ node }) {
    const { height, size, width } = node.props;
    const h = height ?? size ?? 16;
    const w = width;
    return (_jsx("div", { "aria-hidden": "true", style: { height: typeof h === "number" ? `${h}px` : h,
            width: w !== undefined ? (typeof w === "number" ? `${w}px` : w) : undefined } }));
}
export function DividerRenderer({ node }) {
    const { orientation = "horizontal", className } = node.props;
    return (_jsx("div", { role: "separator", "aria-orientation": orientation, className: cn(orientation === "vertical" ? "mx-2 h-full w-px bg-border" : "my-3 h-px w-full bg-border", className) }));
}
/* CustomRenderer */
export function CustomRenderer({ node, renderChildren }) {
    const { className, ...rest } = node.props;
    return (_jsxs(Card, { className: cn("border-dashed", className), children: [_jsxs(CardHeader, { children: [_jsxs(CardTitle, { className: "text-base", children: ["Custom: ", node.originalType] }), _jsx(CardDescription, { children: "Unhandled component type" })] }), _jsxs(CardContent, { children: [_jsx("pre", { className: "text-xs overflow-auto max-h-40", children: JSON.stringify(rest, null, 2) }), renderChildren(node.children)] })] }));
}
/* FallbackComponent */
export function FallbackComponent({ node }) {
    return (_jsxs("div", { className: "rounded-md border border-dashed border-yellow-500/50 bg-yellow-50/50 p-4 dark:bg-yellow-950/20", children: [_jsxs("p", { className: "text-sm font-medium text-yellow-700 dark:text-yellow-400", children: ["Unknown component: ", _jsx("code", { children: node.component })] }), _jsxs("p", { className: "mt-1 text-xs text-muted-foreground", children: ["Original type: ", node.originalType, " | ID: ", node.id] })] }));
}
