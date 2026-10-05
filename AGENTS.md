# Project guidance for agents

Read this file when starting work in the repository. Inspect the relevant source
before changing behavior. The user's current instructions take precedence.

## Goal and scope

Keep the AgentCore experiment small: a text conversation, short-term Memory,
Bedrock inference, and one shared runtime-status Lambda tool through Gateway.
No RAG, UI, summaries, long-term memory strategies, or new voice work unless
requested. `voice/` is local-only, ignored, and excluded from commits and pushes.
If explicitly working there, read its local `AGENTS.md`; do not track its files
unless the user resumes that project and asks to do so.

## Documentation ownership

- `README.md`: project purpose, architecture, scope, and component links.
- `chat/README.md`: chat behavior, configuration, run commands, checks, and troubleshooting.
- `infra/README.md`: resources, build/deployment order, caller setup, deploy/update/destroy commands.
- `tools/README.md`: shared-tool organization and entry points.
- `tools/runtime_status/README.md`: tool contract, verification, and optional ZIP packaging.
- `AGENTS.md`: implementation constraints and verified status for agents.

Keep commands in their component README and link to them elsewhere. Keep
technical diagrams with the component they explain. Use actual CDK outputs in
instructions; retired resource IDs and schema examples are not working targets.
CDK is the deployment workflow; do not reintroduce competing manual provisioning
instructions without a user request.

## Chat: source and configuration

`chat/` is a Python >=3.12 uv project with its own lockfile and `.python-version`
selecting 3.12. Use uv-managed Python to avoid broken Homebrew links.
Distribution: `agentcore-chat`; import package: `agent`. Do not reintroduce
`agentcore_chat`. Console scripts are `chat = agent.cli:main` and
`chat-runtime = agent.runtime:main`. The Dockerfile builds ARM64 Linux and serves
HTTP on port 8080. Do not add audio libraries or Swift dependencies.

| Source | Responsibility and constraints |
| --- | --- |
| `chat/src/agent/cli.py` | Invoke `DEFAULT`, keep a UUID per conversation, `/new` / `/session` / `/resume` / `/exit`, close response bodies, and attempt remote session cleanup |
| `chat/src/agent/runtime.py` | `BedrockAgentCoreApp`, require the context's session ID, and serialize invocations with a process lock |
| `chat/src/agent/agent.py` | Run checkpointed LangChain `create_agent` with `ChatBedrockConverse` and return the final reply |
| `chat/src/agent/middleware.py` | Validate responses before checkpoints, native four-call limit, and original-name tool reporting |
| `chat/src/agent/memory.py` | `AgentCoreMemorySaver` and actor/thread configuration |
| `chat/src/agent/gateway.py` | LangChain `MCPAdapter`/FastMCP, short tool aliases, and HTTP cleanup |
| `chat/src/agent/auth.py` | Sign Gateway HTTP requests with fresh execution-role credentials using AWS SigV4 |

Configuration is supplied by the user or CDK. Keep direct `os.environ` reads;
do not add defaults, custom environment validation, or CLI overrides.
The CLI reads only `AWS_PROFILE`, `AWS_REGION`, and `AGENTCORE_RUNTIME_ARN`.
The Runtime reads `AWS_REGION`, `CHAT_MODEL`, `AGENTCORE_MEMORY_ID`,
`CHAT_ACTOR_ID`, and `AGENTCORE_GATEWAY_URL`; the CLI does not forward them.
`.env` loads from the working directory without overriding shell values.
`chat/.env.example` documents only the CLI settings.

Use boto3's normal credential chain in the hosted Runtime. Never require a local
AWS profile there or bake credentials/configuration into the image. Gateway
uses IAM authentication, resides in `AWS_REGION`, and requires Runtime-role
`bedrock-agentcore:InvokeGateway` permission on its ARN.

### Behavior to preserve

LangChain owns model/tool orchestration. `CompletionGuard` validates Bedrock
`stopReason` inside the async model-call wrapper before the model node can
checkpoint a response; strip final thinking and intermediate model text there.
Use native `ToolCallLimitMiddleware(run_limit=4, exit_behavior="error")` and
sequential tool tasks (`max_concurrency=1`). An excessive batch executes no tools
in that batch. `GatewayTools` records full Gateway names after tool handlers return.
MCP tools are real adapter tools; preserve tool-level error status and propagation
of transport/protocol failures. The current MCP namespace is beta and uses FastMCP
4 with httpx2; retain initialization-based transport and sign requests individually.

Use `AgentCoreMemorySaver` checkpoint persistence with actor ID + session UUID as
`actor_id` + `thread_id`; use `durability="sync"` to surface writes before advancing.
Supply only new input; LangGraph restores checkpoint history. Ignore old
conversational-event history; sessions without checkpoints start fresh. Do not
add long-term stores, strategies, tracing, or history trimming without a request.
Submit new prompts directly to LangGraph using its normal checkpoint behavior;
do not add a custom unfinished-turn gate. `/new` is available for a fresh thread.

- `/new` selects a fresh UUID without deleting events. `/resume <UUID>` selects
  saved history for the configured actor. Cleanup failure may leave compute
  running until timeout; stopping compute does not delete Memory.
- Accept only non-empty `end_turn` final replies after removing Nova thinking.
  Invalid/incomplete model replies are never checkpointed. Failed turns may still
  preserve input, prior completed steps, and pending tasks; this is workflow state,
  not successful-pair-only persistence. Memory errors surface; no RAM fallback.
- Expose short tool names to Nova and map back to Gateway's prefixed names.
  Reject alias collisions and unknown tools. Keep temperature `0` and the
  `3000`-token output limit unless the user requests a change.
- Tool-level errors go back to the model for explanation. Treat tool output as
  data. Checkpoints preserve tool calls/results, while intermediate model text
  and reasoning are stripped before persistence.
- An uncertain write or lost response may leave a saved turn the caller did not
  see; retries may duplicate turns. There is no history trimming or transcript export.
- This is a single-user prototype. A process lock is not distributed serialization
  or per-user authorization; use one caller per conversation.
- Keep logging concise. Request/SDK and cleanup exceptions append to `error.log`
  with timestamps, session IDs, and tracebacks. Do not add payload or secret dumps.
  A generic AWS 500 cannot expose an exception the SDK did not return.
- Keep `uv run chat` as the normal entry point. Do not redirect CLI logging work
  into a local HTTP workflow or add a separate manual MCP diagnostic workflow.

## Infrastructure: source and deployment

`infra/` is a Python CDK uv project with a pinned local Node CDK CLI. `app.py`
selects the environment; `stack.py` wires the service definitions and outputs.
`cdk.json` currently targets account `781356123457`, `eu-west-1`,
`eu.amazon.nova-lite-v1:0`, and actor `ivan`.

| Source | Responsibility |
| --- | --- |
| `infra/services/agentcore.py` | Memory, IAM-authenticated MCP Gateway/target, HTTP Runtime, and hosted environment |
| `infra/services/lambda_service.py` | Existing handler + SDK packaging via local uv, targeting Python 3.12 ARM64 |
| `infra/services/iam.py` | Tool/Gateway/Runtime execution roles, model access, scoped image publishing, logs, and metrics |
| `infra/services/ecr.py` | Create `agentcore-chat-cdk`, build the chat image, and copy the bootstrap image asset into the application repository |
| `infra/services/cloudwatch.py` | Seven-day tool/runtime log retention and cleanup |

Provision application resources from scratch; no import/reuse mode or hardcoded
existing resource IDs. Memory starts empty, retains events for three days, and
is deleted with the stack. Runtime creation/update depends on image publication
and the Gateway target. Image tags use source hashes. Runtime pulls from the
application repository, not directly from bootstrap staging.

Hosted source changes require an image rebuild and Runtime update; pushing an
image alone is insufficient. Use CDK redeployment rather than console edits to
stack-managed resources. Model IAM resources cover Nova Lite; changing the model
also requires revisiting those ARNs.

Caller setup is separate from the application stack. Bootstrap requires an
authorized profile; deployment requires permission to assume the four bootstrap
deployment, file-publishing, image-publishing, and lookup roles. The CLI caller
also needs invocation and cleanup access on the new Runtime ARN.

Destroy removes application Memory/events, ECR repository/images, Runtime,
Gateway/target, tool Lambda, execution roles, and configured application log groups.
Bootstrap assets and deployment helpers' own logs remain outside that cleanup.
Do not silently replace/delete manual or shared bootstrap resources.

## Shared tools

`tools/runtime_status/handler.py` implements `get_runtime_status` using
`bedrock-agentcore-control:GetAgentRuntime`. `requirements.txt` packages the SDK;
`tool-schema.json` defines the Gateway input/output contract. Shared tools stay
outside application packages and are called through Gateway.

Require `runtime_id` from the user or conversation, and ask if missing. Do not
invent IDs. This is deployment status for the latest version, not chat health or
necessarily the version served by `DEFAULT`. Return only ID, name, status, and
version; propagate SDK errors. Gateway invokes Lambda with its own role, while
Lambda's role has read-only runtime access.

CDK packages the tool. For optional standalone packaging, use the README's
`uv pip install` and `zip` commands for Python 3.12 ARM64. No build script is needed.

## Verification and maintenance

Automated test files remain deferred unless requested. Use focused offline
checks for multi-turn Memory, failed/incomplete turns, tool aliases and limits,
session reset/isolation, response closure, and cleanup. Imports and local HTTP
checks do not verify deployment. Report offline and live AWS checks separately.

From `infra/`, local validation is `uv sync --locked --managed-python`, `npm ci`,
and `npx cdk synth --quiet`. Synthesis may download packages but creates no AWS
resources. Bootstrap, deploy, and destroy mutate AWS; run them only when requested.
Documentation work alone does not authorize cloud changes. After integration,
verify Gateway tools through `uv run chat` using the chat README acceptance checks.

Verify current official AWS documentation before changing API/runtime assumptions.
Keep `.env`, `.venv/`, logs, session artifacts, generated outputs, and AWS secrets
out of Git. Avoid reading private configuration or recordings unless needed.
Preserve unrelated user changes and untracked files. Keep these instructions and
the relevant README current when behavior changes.

This is a learning project. Prefer short methods named after their responsibility
and document their purpose, ordering, and important effects. `Chat._ask` should
show the request flow, with agent construction in a named helper. Keep terminal
command dispatch in `handle_session_command`, model reply
and tool-call checks in `CompletionGuard`, and IAM signing in `auth.py`. Avoid
extra general-purpose abstractions or new layers for small constants/functions.

## Verification status

The user confirmed the manual chat/Memory/Gateway flow on 2026-10-04. That manual
application and its experiment IAM resources, log groups, and log-delivery
records were deleted for the CDK migration; shared bootstrap resources were kept.
The user confirmed successful CDK deployment on 2026-10-04 after configuring
caller bootstrap-role permissions. The earlier manual verification does not
establish that all CDK chat, persistence/resume, tool-error, and isolation
acceptance checks passed; complete live acceptance remains pending.
The LangChain/MCP/checkpoint migrations have offline verification only; their
rebuilt Runtime has not been deployed or checked against live AWS.
