import React from "react";
import { FallbackComponent, type ReactAdapterNode } from "./renderers";
type RendererComponent = React.ComponentType<{
    node: ReactAdapterNode;
    renderChildren: (children?: ReactAdapterNode[]) => React.ReactNode;
}>;
/**
 * Component-name → renderer registry.
 *
 * Entries are case- and underscore-insensitive at lookup time via
 * ``getRenderer`` and ``_norm`` (mirrors the BE allowlist normalization
 * in ``components/ui/src/factory/ui/mcp/paint_canvas.py``). Both
 * PascalCase (`Card`) and lower_snake (`item_list`) variants resolve
 * to the same renderer. Adding a new renderer = adding ONE entry under
 * its canonical key (PascalCase preferred); the normalizer handles the
 * casing variants for free.
 *
 * Covers the full A2UI ``COMPONENT_CATALOG`` (23 types) plus internal
 * brick aliases (`page`, `composed_page`, `hero`, `stat_grid`,
 * `live_feed`, `action_pane`, etc.) emitted by the Python ReactAdapter.
 *
 * bd:python-factory-3hkqx round 3 — meta-architect verdict
 * ``cec79d55-7ff3-41c0-b583-781bc5d7d2b7`` Q2(iv): single normalization
 * rule for type-set parity by construction.
 */
export declare const COMPONENT_MAP: Record<string, RendererComponent>;
/**
 * Normalize a key for case+underscore-insensitive lookup. Mirrors the
 * BE rule in ``paint_canvas.py:_norm``.
 */
export declare function normalizeComponentName(s: string): string;
/**
 * Resolve a component name to its renderer with case+underscore-
 * insensitive lookup. Returns `null` if no renderer matches so the
 * caller can fall back to ``FallbackComponent`` and surface a helpful
 * error in the DOM.
 */
export declare function getRenderer(name: string | undefined): RendererComponent | null;
export { FallbackComponent };
export type { RendererComponent };
//# sourceMappingURL=component-map.d.ts.map