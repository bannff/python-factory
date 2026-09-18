import React from "react";
import type { RendererProps } from "./renderer-types";
export declare function TypographyRenderer({ node }: RendererProps): React.JSX.Element;
/**
 * bd:372an — this used to `fetch("/api/tools/${tool}", {method:"POST"})`:
 * no body, result discarded, errors swallowed, BridgeAdapter bypassed. It now
 * goes through `useAction`, which routes every call through the one bridge
 * seam and surfaces pending/error state. The `action` prop carries an
 * `ActionRef`; the server normalizes legacy `props.tool` into it at view
 * ingestion, so there is no back-compat branch here.
 */
export declare function ButtonRenderer({ node }: RendererProps): React.JSX.Element;
export declare function CardRenderer({ node, renderChildren }: RendererProps): React.JSX.Element;
export declare function AlertRenderer({ node }: RendererProps): React.JSX.Element;
export declare function ProgressRenderer({ node }: RendererProps): React.JSX.Element;
export declare function ListRenderer({ node }: RendererProps): React.JSX.Element;
//# sourceMappingURL=renderers-basic.d.ts.map