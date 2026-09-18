"use client";
import { jsx as _jsx } from "react/jsx-runtime";
import React, { createContext, useCallback, useContext, useMemo, useRef } from "react";
const InvalidationContext = createContext(null);
export function InvalidationProvider({ children }) {
    // Multiple components can share a data_tool, so each key holds a Set.
    const registry = useRef(new Map());
    const register = useCallback((key, fn) => {
        const map = registry.current;
        const existing = map.get(key) ?? new Set();
        existing.add(fn);
        map.set(key, existing);
        return () => {
            const current = map.get(key);
            if (!current)
                return;
            current.delete(fn);
            if (current.size === 0)
                map.delete(key);
        };
    }, []);
    const invalidate = useCallback((keys) => {
        for (const key of keys) {
            for (const fn of registry.current.get(key) ?? [])
                fn();
        }
    }, []);
    const value = useMemo(() => ({ register, invalidate }), [register, invalidate]);
    return (_jsx(InvalidationContext.Provider, { value: value, children: children }));
}
/** Read the registry, or `null` when no provider is mounted. */
export function useInvalidation() {
    return useContext(InvalidationContext);
}
/**
 * Register a refetch under `key` for the component's lifetime. Called by
 * `useToolData` so `ActionRef.invalidates: ["cache_cache_stats"]` refreshes
 * every card reading that tool.
 */
export function useRegisterRefetch(key, refetch) {
    const invalidation = useInvalidation();
    const latest = useRef(refetch);
    latest.current = refetch;
    React.useEffect(() => {
        if (!key || !invalidation)
            return;
        return invalidation.register(key, () => latest.current());
    }, [key, invalidation]);
}
