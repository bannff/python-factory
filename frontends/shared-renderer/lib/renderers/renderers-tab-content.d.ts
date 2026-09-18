import React from "react";
export type ChartProps = {
    chart_type?: "line";
    x_key?: string;
    y_key?: string;
    color?: string;
    height?: number;
    empty_message?: string;
};
export type AlertProps = {
    intent_field?: string;
    intent_map?: Record<string, string>;
};
export type TabSpec = {
    id: string;
    label: string;
    tool?: string;
    args?: Record<string, unknown>;
    data_path?: string;
    empty_message?: string;
    render_as?: string;
    chart_props?: ChartProps;
    alert_props?: AlertProps;
};
export declare function ChartTabContent({ tab }: {
    tab: TabSpec;
}): React.JSX.Element;
export declare function AlertTabContent({ tab }: {
    tab: TabSpec;
}): React.JSX.Element;
export declare function ListTabContent({ tab }: {
    tab: TabSpec;
}): React.JSX.Element;
//# sourceMappingURL=renderers-tab-content.d.ts.map