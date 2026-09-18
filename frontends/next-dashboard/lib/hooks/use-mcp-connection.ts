"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import {
  getMcpClient,
  getMcpConnectionSnapshot,
  retryMcpConnection,
  subscribeMcpConnection,
} from "@/lib/mcp-client";

export function useMcpConnection() {
  const status = useSyncExternalStore(
    subscribeMcpConnection,
    getMcpConnectionSnapshot,
    getMcpConnectionSnapshot,
  );

  useEffect(() => {
    if (status === "idle") void getMcpClient().catch(() => undefined);
  }, [status]);

  const retry = useCallback(() => {
    void retryMcpConnection().catch(() => undefined);
  }, []);

  return { status, ready: status === "connected", retry };
}
