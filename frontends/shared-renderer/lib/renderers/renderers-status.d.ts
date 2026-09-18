import React from "react";
import type { RendererProps } from "./renderer-types";
type StatusDotProps = {
    value?: number | null;
    thresholds?: {
        warning?: number;
        critical?: number;
    };
    states?: Record<string, string>;
    state?: string;
};
export declare function StatusDotInline(props: StatusDotProps): React.JSX.Element;
export declare function StatusDotRenderer({ node }: RendererProps): React.JSX.Element;
type TrendBadgeProps = {
    direction?: string;
    change_pct?: number | null;
    positive_is_good?: boolean;
};
export declare function TrendBadgeInline({ direction, change_pct, positive_is_good }: TrendBadgeProps): React.JSX.Element;
export declare function TrendBadgeRenderer({ node }: RendererProps): React.JSX.Element;
export {};
//# sourceMappingURL=renderers-status.d.ts.map