import React from "react";
import type { ReactAdapterNode } from "./renderers";
export type { ReactAdapterNode };
interface ComponentRendererProps {
    node: ReactAdapterNode;
}
/**
 * Recursive renderer for ReactAdapter JSON output.
 *
 * Looks up the `component` (or `type`) field via ``getRenderer``, which
 * resolves case- and underscore-insensitively against ``COMPONENT_MAP``
 * (``component-map.ts``). Renders children recursively and wraps with
 * ``AnimationWrapper`` when an animation hint is present.
 *
 * ``renderChildren`` is memoised so layout renderers (PageRenderer
 * etc.) receive a stable prop and don't force their subtree to
 * re-mount on every parent render — which would reset useState in
 * stateful children like ItemListRenderer.
 *
 * bd:python-factory-3hkqx round 3 — pivoted from exact-key
 * ``COMPONENT_MAP[key]`` lookup to ``getRenderer(key)`` so PascalCase
 * (``Card``), lower_snake (``item_list``), and mixed (``Item_List``)
 * all resolve to the same renderer (meta-architect verdict
 * ``cec79d55-7ff3-41c0-b583-781bc5d7d2b7`` Q2(iv)).
 */
export declare function ComponentRenderer({ node }: ComponentRendererProps): React.JSX.Element;
type TreeGroup = {
    kind: "single";
    node: ReactAdapterNode;
} | {
    kind: "metrics";
    nodes: ReactAdapterNode[];
};
export declare function groupMetricRuns(nodes: ReactAdapterNode[]): TreeGroup[];
/**
 * Renders an array of top-level ReactAdapterNodes.
 * Convenience wrapper for rendering a full view's component list.
 */
export declare function ComponentTree({ nodes, onItemSelect }: {
    nodes: ReactAdapterNode[];
    onItemSelect?: (entityId: string) => void;
}): React.JSX.Element;
//# sourceMappingURL=component-renderer.d.ts.map