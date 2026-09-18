import React from "react";
import type { RendererProps } from "./renderer-types";
export type FilterBarProps = {
    field?: string;
    values?: string[];
    colors?: Record<string, string>;
    show_counts?: boolean;
    counts?: Record<string, number>;
    onFilter?: (value: string | null) => void;
};
export declare function FilterBarInline({ values, colors, show_counts, counts, onFilter }: FilterBarProps): React.JSX.Element | null;
export declare function FilterBarRenderer({ node }: RendererProps): React.JSX.Element;
//# sourceMappingURL=renderers-filter-bar.d.ts.map