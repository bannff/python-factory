# M0 Design — OpenRouter Provider Freedom

**Bead:** `python-factory-bp34j.1`  
**Verdicts:** meta-architect `4e37eccb` APPROVE_WITH_NOTES; SDK reviewer `412fcde2` APPROVE_WITH_NOTES

## Goal

A real Companion-X chat turn streams through OpenRouter, invokes one typed MCP tool, and renders through CopilotKit v2 without `kiro-cli` or a Bedrock-only path.

## Current truth

- Companion-X uses LangChain 1.3.17 and LangGraph 1.2.11.
- `build_langchain_chat_model(model_id)` is the single chat-model factory.
- `ollama/` selects `ChatOllama`; every other model currently selects `ChatBedrockConverse`.
- Agent execution already accepts a provider-neutral LangChain `BaseChatModel`, binds tools through `create_agent`, and streams message chunks through the existing AG-UI mapper.
- `llm_gateway.LLMProvider` is a completion/chat value interface, not a LangChain model. Passing it into Agent would lose framework-native streaming and tool binding.
- CopilotKit v2 and API routes consume provider-neutral events and require no M0 change.

## Decisions

### 1. Provider profile authority

Add one pure resolver to `llm_gateway`, exported only through its public `interface.py`:

```python
resolve_chat_profile(model_id: str) -> ChatProfile
```

`ChatProfile` contains only safe configuration:

- provider
- provider-native model id
- base URL when applicable
- API-key environment-variable name, never its value
- optional attribution-header values
- retry count

No new provider registry and no raw secret egress.

### 2. Framework-native construction

Agent imports the resolver through `factory.llm_gateway.interface` and constructs:

- `openrouter/<vendor>/<model>` → `langchain_openai.ChatOpenAI`
- `ollama/<model>` → existing `ChatOllama`
- bare/Bedrock model id → existing `ChatBedrockConverse`

For OpenRouter:

- strip only `openrouter/`, preserving `<vendor>/<model>`
- default base URL: `https://openrouter.ai/api/v1`
- key: `OPENROUTER_API_KEY`
- native LangChain retries and streaming
- optional `HTTP-Referer` and `X-Title` attribution headers

### 3. Existing selectors remain explicit

- `COMPANION_X_CHAT_MODEL=openrouter` selects the interactive Agent provider.
- `OPENROUTER_MODEL=<vendor>/<model>` selects the OpenRouter-native model.
- The existing `openrouter/<vendor>/<model>` combined form remains backward-compatible.
- `FACTORY_LLM_ADAPTER` continues to select non-agentic `llm_gateway` completion/embedding adapters.
- M0 documents this distinction; it does not silently merge unrelated configuration paths.

### 4. No M0 changes to CopilotKit

The current chain remains:

```text
ChatOpenAI → LangChain create_agent/bind_tools → LangGraph message stream
→ ChatStreamEvent → AG-UI → CopilotKit v2
```

### 5. Reasoning display is follow-up work

OpenRouter reasoning may arrive in `AIMessageChunk.additional_kwargs["reasoning"]`. Current LangChain event translation does not emit `reasoning_text`. M0 does not claim Thinking-panel support; create a follow-up Bead rather than expanding the provider-enablement slice.

## File plan

1. `components/llm_gateway/.../runtime/chat_profile.py`
   - frozen profile model/value
   - deterministic prefix resolver
   - no secret lookup
2. `components/llm_gateway/.../interface.py`
   - public resolver export
3. `components/agent/.../runtime/adapters/langchain_model.py`
   - resolve profile
   - build `ChatOpenAI` for OpenRouter
4. `pyproject.toml` and `projects/companion_x/pyproject.toml`
   - exact compatible `langchain-openai` pin
   - retain existing LangChain/LangGraph pins
5. `projects/companion_x/.env.example`
   - safe variable names and model example only
6. Tests in Agent and llm_gateway test trees
7. Correct only stale runtime documentation directly touched by M0

## Boundary rules

- No new brick.
- No chat call through `LLMProvider`.
- No secret in a DTO, log, profile, MCP result, or frontend state.
- M0 uses a process-owned environment key for the local single-user proof only.
- Before multi-user or cloud provider connections, store credentials behind Auth's opaque credential/broker boundary; llm_gateway and Agent receive only an authorized reference or brokered capability, never a user key through MCP.
- No provider-specific branch outside the resolver and model factory.
- Default Bedrock behavior remains byte-compatible when OpenRouter is not selected.
- Ollama behavior remains unchanged.
- Any new MCP surface, if later justified, must use the standard taxonomy, strict brick-local Pydantic ingress, and typed `ToolResult` egress.

## Test plan

### Baseline before implementation

- Existing llm_gateway adapter/runtime tests.
- Existing Agent factory/chat/stream tests.
- Existing API AG-UI streaming tests.

### New deterministic tests

- Resolve OpenRouter, Ollama, and Bedrock profiles.
- Resolver returns environment-variable names, never secret values.
- `openrouter/deepseek/deepseek-chat` preserves `deepseek/deepseek-chat`.
- OpenRouter factory returns `ChatOpenAI` with expected safe configuration without network access.
- Bedrock and Ollama regressions remain unchanged.
- Synthetic tool-call chunks preserve existing AG-UI ordering.

### Live exit gate

With an operator-provided `OPENROUTER_API_KEY`:

1. Start Companion-X on the feature worktree.
2. Select an allowlisted OpenRouter tool-capable model.
3. Send a prompt that requires one safe deterministic MCP tool.
4. Observe streaming assistant output and `TOOL_CALL_*` AG-UI events.
5. Confirm CopilotKit renders the result.
6. Confirm no `kiro-cli`, Bedrock call, secret output, or frontend secret storage.

## Implementation stop conditions

Stop and report once if:

- no `langchain-openai` version is compatible with current pins,
- the selected OpenRouter model cannot complete the typed tool round-trip,
- credentials are unavailable for the live exit gate.

Unit and integration work may continue independently of live credentials.
