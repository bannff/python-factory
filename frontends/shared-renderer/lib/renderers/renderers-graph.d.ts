import React from "react";
import type { RendererProps } from "./renderer-types";
/**
 * GraphViewerRenderer — renders a graph_viewer component from brick view JSON.
 * Reads data_tool / neighbors_tool from props, loads via MCP, renders ForceGraph2D.
 * Click a node to expand its neighbors. When a Run filter is selected, switches
 * to left-to-right DAG layout to render the workflow execution path.
 */
export declare function GraphViewerRenderer({ node }: RendererProps): React.JSX.Element;
//# sourceMappingURL=renderers-graph.d.ts.map