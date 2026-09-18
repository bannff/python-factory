import React from "react";
import type { RendererProps } from "./renderer-types";
/**
 * bd:372an — this used to raw-`fetch("/api/tools/${tool}")` with `formData` as
 * the body, bypassing the BridgeAdapter seam and carrying no envelope, no
 * thread/run correlation and no transcript entry. It now dispatches through
 * `useAction`. The `action` prop carries an `ActionRef`; the server normalizes
 * legacy `props.tool` into it at ingestion, so the 18 live brick-declared
 * forms keep working with no brick edit.
 */
export declare function FormRenderer({ node }: RendererProps): React.JSX.Element;
export declare function TabsRenderer({ node, renderChildren }: RendererProps): React.JSX.Element;
export declare function BreadcrumbRenderer({ node }: RendererProps): React.JSX.Element;
//# sourceMappingURL=renderers-interactive.d.ts.map