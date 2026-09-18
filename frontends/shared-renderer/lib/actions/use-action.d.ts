import { type ActionRef, type DispatchOutcome } from "./action-ref";
/**
 * useAction — THE frontend action dispatcher (bd:3jcls.3 / bd:372an).
 *
 * `ButtonRenderer` and `FormRenderer` both go through here. Neither one
 * touches `fetch` any more: before this hook they POSTed straight at
 * `/api/tools/${tool}`, bypassing the {@link BridgeAdapter} seam that every
 * other renderer hook honours, discarding the result and swallowing errors.
 * A grep canary test now fails the build if that pattern reappears.
 *
 * Everything routes through `bridge.callTool(DISPATCH_TOOL, ...)` — one
 * server-side chokepoint, which is also where the human provenance hint and
 * (later) the policy gate live.
 *
 * ## Delivery guarantee
 * When `ActionRef.idempotency_arg` is set AND the target tool's JSON schema
 * declares that param, the server receives a per-gesture UUID and the call is
 * genuinely idempotent for that gesture.
 *
 * Otherwise the guarantee is **at-most-once-per-gesture, not idempotent**:
 * an in-flight dedupe on `(tool, resolved args)` plus a `pending` flag the
 * caller uses to disable the control. A double-click cannot start two runs.
 * A reload, a second tab, or a repeat gesture with the same args CAN.
 */
export interface ActionState {
    pending: boolean;
    error: string | null;
    result: unknown;
    /** True once a dispatch has completed successfully at least once. */
    succeeded: boolean;
}
export interface UseActionResult extends ActionState {
    /**
     * Fire the action.
     *
     * @param action The validated {@link ActionRef} from `props.action`.
     * @param extra Caller-supplied arguments (form field values).
     * @param scope Row/form object that `arg_bindings` `$.` paths resolve against.
     */
    dispatch: (action: ActionRef, extra?: Record<string, unknown>, scope?: Record<string, unknown>) => Promise<DispatchOutcome>;
    reset: () => void;
}
export declare function useAction(threadId?: string): UseActionResult;
//# sourceMappingURL=use-action.d.ts.map