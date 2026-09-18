import React from "react";
import type { RendererProps } from "./renderer-types";
/**
 * Compact single-line stat tile (bd:python-factory-3jcls.2).
 *
 * Was a full-width ~98px block (label above a text-2xl value), so seven
 * integers needed a scrollbar. Now it borrows the density idiom the
 * Experiments sub-tab already uses — one ``border-border/50 bg-card/30``
 * row, glyph + label + right-aligned value — and ``ComponentTree``
 * tiles consecutive metrics into a responsive grid. Same surface, same
 * palette, ~40px tall.
 */
export declare function MetricCardRenderer({ node }: RendererProps): React.JSX.Element;
//# sourceMappingURL=renderers-metric.d.ts.map