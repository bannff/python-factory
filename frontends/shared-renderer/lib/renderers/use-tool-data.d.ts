type ToolDataResult = {
    data: unknown;
    loading: boolean;
    error: string | null;
    refetch: () => void;
};
type UseToolDataOptions = {
    refreshMs?: number;
};
export declare function useToolData(toolName?: string, args?: Record<string, unknown>, options?: UseToolDataOptions): ToolDataResult;
export {};
//# sourceMappingURL=use-tool-data.d.ts.map