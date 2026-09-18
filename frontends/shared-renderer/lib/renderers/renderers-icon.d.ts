import React from "react";
/** Normalize a declared icon name for map lookup (case/underscore tolerant). */
export declare function normalizeIconName(name: string): string;
/**
 * True when the string is its own glyph — an emoji or symbol literal.
 * Pictographs carry no ASCII letters and are a couple of code points
 * long (``⚠️``, ``🗑️``, ``🔭``, ``▶️``); identifiers and prose do.
 */
export declare function isPictograph(name: string): boolean;
/** Resolve a declared icon name to a Lucide component, or ``null``. */
export declare function resolveIcon(name?: string): import("lucide-react").LucideIcon | null;
export interface ViewIconProps {
    /** Icon name from a brick view payload — token or pictograph. */
    name?: string;
    /** Tailwind classes for the glyph (sizing/colour). */
    className?: string;
    /** Tailwind classes for the pictograph text span. */
    textClassName?: string;
}
/**
 * Renders a brick-declared icon, or nothing. NEVER renders a raw
 * token as text.
 */
export declare function ViewIcon({ name, className, textClassName }: ViewIconProps): React.JSX.Element | null;
//# sourceMappingURL=renderers-icon.d.ts.map