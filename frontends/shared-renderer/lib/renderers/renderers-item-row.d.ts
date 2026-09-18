import React from "react";
import { type ItemLayoutSpec, type DetailSpec } from "./renderers-item-list-utils";
export declare function ItemRow({ item, itemKey, layout, detail, badgeColorMap, isExpanded, onToggle }: {
    item: Record<string, unknown>;
    itemKey: string;
    layout?: ItemLayoutSpec;
    detail?: DetailSpec;
    badgeColorMap: Record<string, string>;
    isExpanded: boolean;
    onToggle: () => void;
}): React.JSX.Element;
//# sourceMappingURL=renderers-item-row.d.ts.map