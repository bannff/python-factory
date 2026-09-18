import React from "react";
import type { BridgeAdapter } from "./bridge-adapter";
interface BridgeAdapterProviderProps {
    adapter: BridgeAdapter;
    children: React.ReactNode;
}
/**
 * Supplies a {@link BridgeAdapter} to the renderer subtree. Mount once
 * at the host's client root; every renderer hook that needs MCP data
 * (`useToolData`, `useGraphData`, `ItemListRenderer`, `LazyTabContent`,
 * `GraphViewerRenderer`) reads `callTool` from here via {@link useBridge}.
 */
export declare function BridgeAdapterProvider({ adapter, children }: BridgeAdapterProviderProps): React.JSX.Element;
/**
 * Read the host-supplied {@link BridgeAdapter}. Throws if no provider is
 * mounted — a loud failure beats silently swallowed tool calls.
 */
export declare function useBridge(): BridgeAdapter;
/**
 * Read the adapter without throwing. For hooks that only need transport at
 * INTERACTION time (`useAction`), not at render time — a Button must still
 * paint in a host that mounted no provider, and report the missing seam when
 * it is actually clicked. Data hooks keep using {@link useBridge}, which
 * fails at render because they cannot do their job at all without it.
 */
export declare function useBridgeOptional(): BridgeAdapter | null;
export {};
//# sourceMappingURL=bridge-adapter-context.d.ts.map