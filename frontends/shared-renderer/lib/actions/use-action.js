"use client";
import { useCallback, useRef, useState } from "react";
import { useBridgeOptional } from "../bridge-adapter-context";
import { useInvalidation } from "./invalidation-context";
import { useTranscriptSink } from "./transcript-context";
import { DISPATCH_TOOL, dedupeKey, gestureId, resolveArgs, } from "./action-ref";
const IDLE = { pending: false, error: null, result: null, succeeded: false };
export function useAction(threadId) {
    // Optional at render time, required at click time — a Button must still
    // paint in a host that mounted no provider (see `useBridgeOptional`).
    const bridge = useBridgeOptional();
    const invalidation = useInvalidation();
    const transcript = useTranscriptSink();
    const [state, setState] = useState(IDLE);
    // Shared across renders: collapses concurrent identical gestures.
    const inFlight = useRef(new Map());
    const reset = useCallback(() => setState(IDLE), []);
    const dispatch = useCallback(async (action, extra = {}, scope = {}) => {
        if (!bridge) {
            const error = "No BridgeAdapter mounted — wrap the tree in <BridgeAdapterProvider> " +
                "to dispatch actions.";
            setState({ pending: false, error, result: null, succeeded: false });
            return { ok: false, error };
        }
        const args = resolveArgs(action, scope, extra);
        const gesture = gestureId();
        if (action.idempotency_arg)
            args[action.idempotency_arg] = gesture;
        const key = dedupeKey(action, args);
        const existing = inFlight.current.get(key);
        if (existing)
            return existing;
        setState({ pending: true, error: null, result: null, succeeded: false });
        const run = (async () => {
            try {
                const raw = await bridge.callTool(DISPATCH_TOOL, {
                    action,
                    args,
                    thread_id: threadId,
                });
                // The adapter is a pass-through; hooks own the envelope unwrap.
                const outcome = (raw.result ?? raw);
                if (!outcome || typeof outcome !== "object") {
                    throw new Error("Dispatcher returned an unreadable response");
                }
                if (!outcome.ok) {
                    // Visible, never swallowed — the defect bd:372an closed.
                    setState({
                        pending: false,
                        error: outcome.error ?? "Action failed",
                        result: null,
                        succeeded: false,
                    });
                }
                else {
                    setState({
                        pending: false, error: null, result: outcome.result, succeeded: true,
                    });
                    const keys = outcome.invalidates ?? action.invalidates ?? [];
                    if (keys.length)
                        invalidation?.invalidate(keys);
                }
                transcript?.({
                    toolCallId: gesture,
                    toolName: outcome.tool ?? action.tool,
                    args,
                    result: outcome.ok ? outcome.result : { error: outcome.error },
                    ok: Boolean(outcome.ok),
                });
                return outcome;
            }
            catch (err) {
                const message = err instanceof Error ? err.message : "Action failed";
                setState({ pending: false, error: message, result: null, succeeded: false });
                transcript?.({
                    toolCallId: gesture,
                    toolName: action.tool,
                    args,
                    result: { error: message },
                    ok: false,
                });
                return { ok: false, error: message };
            }
            finally {
                inFlight.current.delete(key);
            }
        })();
        inFlight.current.set(key, run);
        return run;
    }, [bridge, invalidation, transcript, threadId]);
    return { ...state, dispatch, reset };
}
