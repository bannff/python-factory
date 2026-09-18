import React from "react";
export declare const JUDGE_COLORS: Record<string, string>;
export declare function scoreColor(v: number): string;
export declare function fmtTime(iso: string): string;
export declare function CopyChip({ label, value }: {
    label: string;
    value: string;
}): React.JSX.Element;
export declare function TipChip({ label, short, full }: {
    label: string;
    short: string;
    full: string;
}): React.JSX.Element;
export declare function PromptChip({ label, value }: {
    label: string;
    value: string;
}): React.JSX.Element;
export declare function PillsChip({ label, values }: {
    label: string;
    values: string[];
}): React.JSX.Element;
export declare function ThresholdChip({ label, val }: {
    label: string;
    val: unknown;
}): React.JSX.Element;
//# sourceMappingURL=renderers-metadata-chip-parts.d.ts.map