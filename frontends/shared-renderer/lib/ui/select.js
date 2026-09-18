import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import * as React from "react";
import { cn } from "../lib/utils";
const Select = React.forwardRef(({ className, options = [], children, ...props }, ref) => (_jsxs("select", { className: cn("flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50", className), ref: ref, ...props, children: [options.map((opt) => (_jsx("option", { value: opt.value, children: opt.label }, opt.value))), children] })));
Select.displayName = "Select";
export { Select };
