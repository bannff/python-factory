"use client";
import { jsx as _jsx } from "react/jsx-runtime";
import { createContext, useContext } from "react";
const BridgeAdapterContext = createContext(null);
/**
 * Supplies a {@link BridgeAdapter} to the renderer subtree. Mount once
 * at the host's client root; every renderer hook that needs MCP data
 * (`useToolData`, `useGraphData`, `ItemListRenderer`, `LazyTabContent`,
 * `GraphViewerRenderer`) reads `callTool` from here via {@link useBridge}.
 */
export function BridgeAdapterProvider({ adapter, children }) {
    return (_jsx(BridgeAdapterContext.Provider, { value: adapter, children: children }));
}
/**
 * Read the host-supplied {@link BridgeAdapter}. Throws if no provider is
 * mounted — a loud failure beats silently swallowed tool calls.
 */
export function useBridge() {
    const adapter = useContext(BridgeAdapterContext);
    if (!adapter) {
        throw new Error("useBridge must be used within a <BridgeAdapterProvider>. " +
            "Mount the provider at your app's client root and pass a BridgeAdapter.");
    }
    return adapter;
}
/**
 * Read the adapter without throwing. For hooks that only need transport at
 * INTERACTION time (`useAction`), not at render time — a Button must still
 * paint in a host that mounted no provider, and report the missing seam when
 * it is actually clicked. Data hooks keep using {@link useBridge}, which
 * fails at render because they cannot do their job at all without it.
 */
export function useBridgeOptional() {
    return useContext(BridgeAdapterContext);
}
