import React from "react";
import type { RendererProps } from "./renderer-types";
export declare function DialogRenderer({ node, renderChildren }: RendererProps): React.JSX.Element;
export declare function ToastRenderer({ node }: RendererProps): React.JSX.Element | null;
export declare function PageRenderer({ node, renderChildren }: RendererProps): React.JSX.Element;
export declare function TreeRenderer({ node }: RendererProps): React.JSX.Element;
export declare function SpacerRenderer({ node }: RendererProps): React.JSX.Element;
export declare function DividerRenderer({ node }: RendererProps): React.JSX.Element;
export declare function CustomRenderer({ node, renderChildren }: RendererProps): React.JSX.Element;
export declare function FallbackComponent({ node }: RendererProps): React.JSX.Element;
//# sourceMappingURL=renderers-layout.d.ts.map