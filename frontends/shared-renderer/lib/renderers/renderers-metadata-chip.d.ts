import React from "react";
export type MetadataRenderAs = "copy_id" | "popover" | "pills" | "relative_time" | "score" | "model_chip" | "threshold" | "default";
export type MetadataChipEntry = {
    label: string;
    value?: unknown;
    path?: string;
    render_as?: MetadataRenderAs;
    zone?: "config" | "identity";
};
export declare function MetadataChip({ entry, val }: {
    entry: MetadataChipEntry;
    val: unknown;
}): React.JSX.Element;
//# sourceMappingURL=renderers-metadata-chip.d.ts.map