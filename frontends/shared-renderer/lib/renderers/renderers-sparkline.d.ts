import React from "react";
import type { RendererProps } from "./renderer-types";
export type SparklineProps = {
    data?: number[];
    variant?: "bar" | "line";
    color?: string;
    height?: number;
    max_points?: number;
};
export declare function SparklineInline({ data, variant, color, height, max_points }: SparklineProps): React.JSX.Element | null;
export declare function SparklineRenderer({ node }: RendererProps): React.JSX.Element;
//# sourceMappingURL=renderers-sparkline.d.ts.map