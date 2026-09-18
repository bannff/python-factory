/* Shared types and utilities for item_list frame components. */
/* ── JSONPath-lite resolver ── */
export function resolve(obj, path) {
    if (typeof path !== "string" || !path.startsWith("$."))
        return path;
    const keys = path.slice(2).split(".");
    let current = obj;
    for (const key of keys) {
        if (current == null || typeof current !== "object")
            return undefined;
        current = current[key];
    }
    return current;
}
export function resolveStr(obj, path) {
    if (!path)
        return undefined;
    const v = resolve(obj, path);
    return v != null ? String(v) : undefined;
}
export function resolveNum(obj, path) {
    if (!path)
        return undefined;
    const v = resolve(obj, path);
    return typeof v === "number" ? v : undefined;
}
/* ── Badge color map ── */
export const BADGE_COLORS = {
    blue: "bg-blue-500/10 text-blue-400",
    orange: "bg-orange-500/10 text-orange-400",
    emerald: "bg-emerald-500/10 text-emerald-400",
    purple: "bg-purple-500/10 text-purple-400",
    red: "bg-red-500/10 text-red-400",
    yellow: "bg-yellow-500/10 text-yellow-400",
    gray: "bg-gray-500/10 text-gray-400",
};
/* ── Helpers ── */
export function extractArray(raw, dataPath) {
    if (dataPath && raw && typeof raw === "object") {
        const extracted = resolve(raw, dataPath);
        if (Array.isArray(extracted))
            return extracted;
    }
    if (Array.isArray(raw))
        return raw;
    return [];
}
