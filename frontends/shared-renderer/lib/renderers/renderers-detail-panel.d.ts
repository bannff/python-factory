import React from "react";
import type { RendererProps } from "./renderer-types";
import { type SparklineProps } from "./renderers-sparkline";
import { type TabSpec } from "./renderers-tab-content";
type MetadataEntry = {
    label: string;
    value?: unknown;
    path?: string;
    render_as?: string;
    zone?: "config" | "identity";
};
type DetailPanelProps = {
    sparkline?: SparklineProps & {
        data_path?: string;
    };
    metadata?: MetadataEntry[];
    tabs?: TabSpec[];
    item?: Record<string, unknown>;
    resolveFn?: (obj: Record<string, unknown>, path: string) => unknown;
};
export declare function DetailPanelInline({ sparkline, metadata, tabs, item, resolveFn }: DetailPanelProps): React.JSX.Element;
export declare function DetailPanelRenderer({ node }: RendererProps): React.JSX.Element;
export {};
//# sourceMappingURL=renderers-detail-panel.d.ts.map