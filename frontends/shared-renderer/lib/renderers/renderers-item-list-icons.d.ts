import { type LucideIcon } from "lucide-react";
/**
 * Maps icon name tokens (from brick view declarations) to Lucide icons.
 *
 * Consumed exclusively through ``ViewIcon`` (``renderers-icon.tsx``),
 * which looks keys up case- and underscore-insensitively and renders
 * NOTHING for an unmapped token rather than leaking the identifier
 * (bd:python-factory-3jcls.1). Keys are the heroicons-style kebab-case
 * names bricks emit; add a mapping here when a brick declares a new one.
 */
export declare const ICON_MAP: Record<string, LucideIcon>;
//# sourceMappingURL=renderers-item-list-icons.d.ts.map