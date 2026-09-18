import React from "react";
export type TabDef = {
    id: string;
    label: string;
    lazy_tool?: string;
    result_hints?: {
        prefer?: string;
        columns?: {
            key: string;
            label: string;
        }[];
        searchable?: boolean;
        sortable?: boolean;
        group_by?: string;
    };
};
export declare function LazyTabContent({ tab }: {
    tab: TabDef;
}): React.JSX.Element;
//# sourceMappingURL=renderers-lazy-tab.d.ts.map