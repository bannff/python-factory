import {
  Client,
  SdkErrorCode,
  SdkHttpError,
  StreamableHTTPClientTransport,
  UnauthorizedError,
  type ElicitRequest,
  type ElicitResult,
} from "@modelcontextprotocol/client";

import {
  cancelAllConfirmations,
  requestConfirmation,
} from "./mcp-confirmation";
import { cancelAllQuestions, requestQuestion } from "./mcp-question";

/**
 * Singleton browser-side MCP v2 client.
 *
 * SDK-first pin: @modelcontextprotocol/client@2.0.0. The browser connects to
 * the same-origin local BFF and never owns the backend bearer; the BFF adds it
 * only after loopback/origin admission. CopilotKit/AG-UI and mcp-ui remain
 * independent consumers.
 */

let clientPromise: Promise<Client> | null = null;
let clientInstance: Client | null = null;

export type McpConnectionStatus = "idle" | "connecting" | "connected" | "error";
let connectionStatus: McpConnectionStatus = "idle";
const connectionListeners = new Set<() => void>();

function setConnectionStatus(status: McpConnectionStatus): void {
  if (connectionStatus === status) return;
  connectionStatus = status;
  connectionListeners.forEach((listener) => listener());
}

export function getMcpConnectionSnapshot(): McpConnectionStatus {
  return connectionStatus;
}

export function subscribeMcpConnection(listener: () => void): () => void {
  connectionListeners.add(listener);
  return () => connectionListeners.delete(listener);
}

export class McpAuthenticationError extends Error {
  constructor() {
    super("Local MCP authentication failed. Restart Companion X with a configured local token.");
    this.name = "McpAuthenticationError";
  }
}

export function normalizeMcpConnectionError(error: unknown): unknown {
  if (UnauthorizedError.isInstance(error)
      || (SdkHttpError.isInstance(error)
          && error.code === SdkErrorCode.ClientHttpAuthentication)) {
    return new McpAuthenticationError();
  }
  return error;
}

function mcpUrl(): URL {
  if (typeof window === "undefined") {
    const base = process.env.API_URL || "http://localhost:8000";
    return new URL(`${base}/mcp/`);
  }
  return new URL("/mcp", window.location.origin);
}

function isBooleanConfirmation(schema: unknown): string | null {
  if (!schema || typeof schema !== "object") return null;
  const value = schema as {
    type?: unknown;
    properties?: Record<string, { type?: unknown; anyOf?: Array<{ type?: unknown }> }>;
    required?: unknown;
    additionalProperties?: unknown;
  };
  if (value.type !== "object" || value.additionalProperties !== false) return null;
  const entries = Object.entries(value.properties ?? {});
  if (entries.length !== 1) return null;
  const [field, fieldSchema] = entries[0];
  const types = fieldSchema.anyOf?.map((item) => item.type) ?? [fieldSchema.type];
  const nonNull = types.filter((type) => type !== "null");
  const required = Array.isArray(value.required) && value.required.includes(field);
  return required && nonNull.length === 1 && nonNull[0] === "boolean" ? field : null;
}

interface EnumChoice {
  field: string;
  options: string[];
}

/** Detect a single required string field with a fixed `enum` — a multiple-choice question. */
function isEnumChoice(schema: unknown): EnumChoice | null {
  if (!schema || typeof schema !== "object") return null;
  const value = schema as {
    type?: unknown;
    properties?: Record<string, { type?: unknown; enum?: unknown }>;
    required?: unknown;
    additionalProperties?: unknown;
  };
  if (value.type !== "object" || value.additionalProperties !== false) return null;
  const entries = Object.entries(value.properties ?? {});
  if (entries.length !== 1) return null;
  const [field, fieldSchema] = entries[0];
  const required = Array.isArray(value.required) && value.required.includes(field);
  if (!required || fieldSchema.type !== "string" || !Array.isArray(fieldSchema.enum)) return null;
  const options = fieldSchema.enum.filter((item): item is string => typeof item === "string");
  return options.length >= 2 ? { field, options } : null;
}

async function handleElicitation(request: ElicitRequest): Promise<ElicitResult> {
  if (typeof window === "undefined") return { action: "cancel" };
  const params = request.params;
  if (params.mode !== undefined && params.mode !== "form") return { action: "cancel" };
  const choice = isEnumChoice(params.requestedSchema);
  if (choice) {
    const decision = await requestQuestion(params.message, choice.field, choice.options);
    return decision.action === "answer"
      ? { action: "accept", content: { [choice.field]: decision.value } }
      : { action: "cancel" };
  }
  const field = isBooleanConfirmation(params.requestedSchema);
  if (!field) return { action: "cancel" };
  const decision = await requestConfirmation(params.message, field);
  return decision === "accept"
    ? { action: "accept", content: { [field]: true } }
    : { action: decision };
}

async function connect(): Promise<Client> {
  const client = new Client(
    { name: "companion-x-next-dashboard", version: "1.0.0" },
    {
      versionNegotiation: { mode: "auto", probe: { maxRetries: 0 } },
      capabilities: { elicitation: { form: {} } },
      inputRequired: { autoFulfill: true, maxRounds: 1 },
    },
  );
  client.setRequestHandler("elicitation/create", handleElicitation);
  await client.connect(new StreamableHTTPClientTransport(mcpUrl(), {
    requestInit: { headers: { "x-companion-x-local": "1" } },
  }));
  clientInstance = client;
  return client;
}

/** Get the shared MCP client, connecting on first use. */
export async function getMcpClient(): Promise<Client> {
  if (!clientPromise) {
    setConnectionStatus("connecting");
    clientPromise = connect().then((client) => {
      setConnectionStatus("connected");
      return client;
    }).catch((error) => {
      clientPromise = null;
      clientInstance = null;
      cancelAllConfirmations();
      cancelAllQuestions();
      setConnectionStatus("error");
      throw normalizeMcpConnectionError(error);
    });
  }
  return clientPromise;
}

/** Reset the singleton and cancel pending confirmation and question prompts. */
export function resetMcpClient(): void {
  cancelAllConfirmations();
  cancelAllQuestions();
  void clientInstance?.close();
  clientInstance = null;
  clientPromise = null;
  setConnectionStatus("idle");
}

export function retryMcpConnection(): Promise<Client> {
  resetMcpClient();
  return getMcpClient();
}
