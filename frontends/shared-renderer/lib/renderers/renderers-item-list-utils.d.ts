import type { FilterBarProps } from "./renderers-filter-bar";
export declare function resolve(obj: Record<string, unknown>, path: unknown): unknown;
export declare function resolveStr(obj: Record<string, unknown>, path?: string): string | undefined;
export declare function resolveNum(obj: Record<string, unknown>, path?: string): number | undefined;
export declare const BADGE_COLORS: Record<string, string>;
export type ItemLayoutSpec = {
    status_dot?: {
        value_path?: string;
        thresholds?: Record<string, string>;
        states?: Record<string, string>;
    };
    title?: string;
    subtitle?: string;
    subtitle_icon?: string;
    badge?: {
        field?: string;
        color_map?: string;
        suffix?: string;
    };
    value?: {
        path?: string;
        format?: string;
    };
    trend?: {
        direction?: string;
        change_pct?: string;
        positive_is_good?: boolean;
    };
};
export type DetailSpec = {
    sparkline?: {
        data_path?: string;
        color?: string;
        height?: number;
        max_points?: number;
        variant?: "bar" | "line";
    };
    metadata?: {
        label: string;
        path?: string;
        render_as?: string;
        zone?: "config" | "identity";
    }[];
    tabs?: {
        id: string;
        label: string;
        tool?: string;
        args?: Record<string, string>;
    }[];
};
export type ItemListProps = {
    data_tool?: string;
    refresh_ms?: number;
    data_path?: string;
    item_key?: string;
    empty_icon?: string;
    empty_message?: string;
    header?: {
        icon?: string;
        stats_tool?: string;
        stats_map?: Record<string, string>;
    };
    filters?: FilterBarProps & {
        field?: string;
        values?: string[];
        colors?: Record<string, string>;
    };
    item_layout?: ItemLayoutSpec;
    item_snapshot_tool?: string;
    item_snapshot_args?: Record<string, string>;
    snapshot_merge_path?: string;
    detail?: DetailSpec;
};
export declare function extractArray(raw: unknown, dataPath?: string): Record<string, unknown>[];
//# sourceMappingURL=renderers-item-list-utils.d.ts.map