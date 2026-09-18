"use client";
import { jsx as _jsx } from "react/jsx-runtime";
import { createContext, useContext } from "react";
const TranscriptContext = createContext(null);
export function TranscriptSinkProvider({ sink, children, }) {
    return _jsx(TranscriptContext.Provider, { value: sink, children: children });
}
/** Read the host-supplied sink, or `null` when none is mounted. */
export function useTranscriptSink() {
    return useContext(TranscriptContext);
}
