import React from "react";
type AnimationHint = {
    effect: string;
    library: string;
};
interface AnimationWrapperProps {
    animation: AnimationHint;
    children: React.ReactNode;
}
export declare function AnimationWrapper({ animation, children }: AnimationWrapperProps): React.JSX.Element;
export {};
//# sourceMappingURL=animation-wrapper.d.ts.map