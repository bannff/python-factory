"use client";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useCallback, useState } from "react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter, } from "../ui/card";
import { Button } from "../ui/button";
import { Progress } from "../ui/progress";
import { cn } from "../lib/utils";
import { asActionRef } from "../actions/action-ref";
import { useAction } from "../actions/use-action";
/* TypographyRenderer */
const TYPOGRAPHY_VARIANTS = {
    h1: "scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl",
    h2: "scroll-m-20 text-3xl font-semibold tracking-tight",
    h3: "scroll-m-20 text-2xl font-semibold tracking-tight",
    h4: "scroll-m-20 text-xl font-semibold tracking-tight",
    p: "leading-7",
    lead: "text-xl text-muted-foreground",
    large: "text-lg font-semibold",
    small: "text-sm font-medium leading-none",
    muted: "text-sm text-muted-foreground",
};
export function TypographyRenderer({ node }) {
    // bd:python-factory-3hkqx round 4 — accept all three prop aliases
    // for the Text type. Catalog docstring lists `content`; LLM agents
    // commonly emit `value`; the legacy renderer read `text`. The wire
    // is permissive at this layer (qa-tester memory `487b3ec5`).
    const props = node.props;
    const { variant = "p", className } = props;
    const body = props.text ?? props.content ?? props.value ?? "";
    const Tag = (variant.startsWith("h") && /^h[1-4]$/.test(variant)
        ? variant : "p");
    return (_jsx(Tag, { className: cn(TYPOGRAPHY_VARIANTS[variant] ?? TYPOGRAPHY_VARIANTS.p, className), children: body }));
}
/* ButtonRenderer */
/**
 * bd:372an — this used to `fetch("/api/tools/${tool}", {method:"POST"})`:
 * no body, result discarded, errors swallowed, BridgeAdapter bypassed. It now
 * goes through `useAction`, which routes every call through the one bridge
 * seam and surfaces pending/error state. The `action` prop carries an
 * `ActionRef`; the server normalizes legacy `props.tool` into it at view
 * ingestion, so there is no back-compat branch here.
 */
export function ButtonRenderer({ node }) {
    const { label, variant = "default", size, disabled, action, action_error, className } = node.props;
    const ref = asActionRef(action);
    const { dispatch, pending, error } = useAction();
    const [confirming, setConfirming] = useState(false);
    const handleClick = useCallback(() => {
        if (!ref)
            return;
        if (ref.confirm && !confirming) {
            setConfirming(true);
            return;
        }
        setConfirming(false);
        void dispatch(ref);
    }, [ref, confirming, dispatch]);
    const verb = label ?? ref?.label ?? "Button";
    const shown = action_error ?? error;
    const button = (_jsx(Button, { variant: confirming ? "destructive" : variant, size: size, disabled: disabled || pending || !ref, onClick: handleClick, className: className, "aria-busy": pending || undefined, children: pending ? "Working…" : confirming ? `Confirm: ${verb}` : verb }));
    if (!shown)
        return button;
    return (_jsxs("div", { className: "space-y-1", children: [button, _jsx("div", { role: "alert", className: "rounded-md border border-destructive/50 p-2 text-xs text-destructive", children: shown })] }));
}
/* CardRenderer */
export function CardRenderer({ node, renderChildren }) {
    const { title, description, footer, className } = node.props;
    return (_jsxs(Card, { className: className, children: [(title || description) && (_jsxs(CardHeader, { children: [title && _jsx(CardTitle, { children: title }), description && _jsx(CardDescription, { children: description })] })), _jsx(CardContent, { children: renderChildren(node.children) }), footer && (_jsx(CardFooter, { children: _jsx("p", { className: "text-sm text-muted-foreground", children: footer }) }))] }));
}
/* AlertRenderer */
const ALERT_VARIANTS = {
    default: "bg-background text-foreground",
    destructive: "border-destructive/50 text-destructive [&>svg]:text-destructive",
    warning: "border-yellow-500/50 text-yellow-700 [&>svg]:text-yellow-600",
};
export function AlertRenderer({ node }) {
    // bd:python-factory-3hkqx round 4 — accept catalog alias `message`
    // alongside the legacy renderer's `title`+`description`. The
    // catalog spec says required_props=["message"]; the LLM follows
    // the catalog. qa-tester memory `487b3ec5`.
    const props = node.props;
    const { title, description, message, variant = "default", className } = props;
    const heading = title ?? message;
    const body = description ?? (title ? message : undefined);
    return (_jsxs("div", { role: "alert", className: cn("relative w-full rounded-lg border p-4 [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4", ALERT_VARIANTS[variant] ?? ALERT_VARIANTS.default, className), children: [heading && _jsx("h5", { className: "mb-1 font-medium leading-none tracking-tight", children: heading }), body && _jsx("div", { className: "text-sm [&_p]:leading-relaxed", children: body })] }));
}
/* ProgressRenderer */
export function ProgressRenderer({ node }) {
    const { value = 0, max = 100, label, className } = node.props;
    return (_jsxs("div", { className: cn("space-y-1", className), children: [label && (_jsxs("div", { className: "flex justify-between text-sm", children: [_jsx("span", { children: label }), _jsxs("span", { className: "text-muted-foreground", children: [Math.round((value / max) * 100), "%"] })] })), _jsx(Progress, { value: value, max: max })] }));
}
/* ListRenderer */
export function ListRenderer({ node }) {
    const { items = [], ordered = false, className } = node.props;
    const Tag = ordered ? "ol" : "ul";
    return (_jsx(Tag, { className: cn("my-2 ml-6 list-disc [&>li]:mt-2", ordered && "list-decimal", className), children: items.map((item, i) => _jsx("li", { children: item }, i)) }));
}
