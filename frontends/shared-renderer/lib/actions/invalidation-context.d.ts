import React from "react";
/**
 * Refetch registry — authoritative client re-fetch after an action
 * (bd:3jcls.3, design decision 3).
 *
 * The action response deliberately does NOT carry a view payload; that would
 * fork view production between `*_get_views` and every operational tool. So
 * on success the dispatcher re-fetches. `useToolData` registers its `refetch`
 * here keyed by tool name; `ActionRef.invalidates` names the keys to fire.
 *
 * Optional by design: with no provider mounted, `invalidate` is a no-op and
 * the dispatch still works. That keeps the renderer usable in hosts (and
 * tests) that do not care about refresh.
 */
type RefetchFn = () => void;
interface InvalidationValue {
    register: (key: string, fn: RefetchFn) => () => void;
    invalidate: (keys: string[]) => void;
}
export declare function InvalidationProvider({ children }: {
    children: React.ReactNode;
}): React.JSX.Element;
/** Read the registry, or `null` when no provider is mounted. */
export declare function useInvalidation(): InvalidationValue | null;
/**
 * Register a refetch under `key` for the component's lifetime. Called by
 * `useToolData` so `ActionRef.invalidates: ["cache_cache_stats"]` refreshes
 * every card reading that tool.
 */
export declare function useRegisterRefetch(key: string | undefined, refetch: RefetchFn): void;
export {};
//# sourceMappingURL=invalidation-context.d.ts.map