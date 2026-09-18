import React from "react";
import type { RendererProps } from "./renderer-types";
type LineageNode = {
    node_id: string;
    entity_id?: string | null;
    entity_type?: string;
    source?: string;
    source_ref?: string;
    evidence?: string;
};
type LineageEdge = {
    source: string;
    target: string;
    relation?: string;
    verified?: boolean;
};
type LineageData = {
    nodes: LineageNode[];
    edges: LineageEdge[];
    missing_links: Array<{
        node_id?: string;
        kinds?: string[];
    }>;
    truncated: boolean;
    dropped_edges: number;
};
export declare function normalizeLineageData(raw: unknown): LineageData;
export declare function LineageRenderer({ node }: RendererProps): React.JSX.Element;
export {};
//# sourceMappingURL=renderers-lineage.d.ts.map