# Project guidance for agents

Read this file at the start of conversations in this repository. Inspect the
relevant source before changing behavior and keep this guidance current.
The user's current instructions take precedence.

## Goal and scope

Experiment with Amazon Bedrock AgentCore using a minimal text conversation:
the user asks, the agent replies, and follow-ups reuse short-term agent memory.
Keep the implementation small. One shared runtime-status Lambda tool is exposed
through AgentCore Gateway. No RAG, UI, summaries, long-term
memory strategies, or new voice work is needed unless the user changes the scope.

The active project is `chat/`. The preserved voice prototype is local-only in
`voice/`, ignored by Git and excluded from pushes. If present, read its local
`voice/AGENTS.md` when working there. Do not include voice files in a commit
unless the user explicitly resumes that project and asks to track it.

## Layout and entry points

- `infra/`: Python CDK project with uv lockfile and a pinned local Node CDK CLI.
  `stack.py` wires service definitions in `services/`: `agentcore.py` contains
  Memory, Runtime, and Gateway; other files contain Lambda, IAM, ECR assets,
  and CloudWatch. It provisions all application resources
  from scratch, packages existing source, and wires IAM/environment settings.
  `cdk.json` targets account `781356123457`, `eu-west-1`. Memory starts empty with
  three-day event retention and is deleted with the stack; no existing resource
  IDs or import/reuse mode.
  Follow `infra/README.md`; do not silently replace or delete manual resources.

- `tools/runtime_status/`: shared Lambda source, SDK requirements, and Gateway
  tool schema for `get_runtime_status`. It takes a required `runtime_id` tool
  argument supplied by the user and reads that runtime's deployment
  status, not chat health. The user confirmed the deployed chat → Gateway → Lambda
  flow working through `uv run chat` on 2026-10-04.
- Package the shared Lambda with the terminal commands in its README using
  `uv pip install` and `zip` (Python 3.12 ARM64 target). No build script is needed.
- Shared tools live outside `chat/` and `voice/` so either agent can call them
  through Gateway without importing the other's application code.
- `chat/src/agent/agent.py`: boto3 Bedrock Converse call and one conversation's
  retrieved history, Gateway tool schemas, and a loop capped at four tool calls.
  Save only the user message and valid final reply; tool exchanges are not saved.
  Expose short tool names to Nova and map them back to Gateway's prefixed names.
  Reject alias collisions and remove Nova thinking blocks from final replies.
- `chat/src/agent/gateway.py`: MCP initialization, paginated tool discovery,
  and calls signed with the runtime's normal credentials. Close HTTP on exit.
- `chat/src/agent/memory.py`: AgentCore short-term event reads/writes; paginate
  history and store each user/assistant pair in one event.
- `chat/src/agent/cli.py`: local terminal UI calling the deployed AgentCore
  `DEFAULT` endpoint, with `/new`, `/exit`, and remote session cleanup.
- `chat/src/agent/runtime.py`: `BedrockAgentCoreApp`, conversations keyed by
  session ID passed to memory, and a process lock serializing invocations.
- `chat/pyproject.toml`: distribution `agentcore-chat`, Python package `agent`,
  console scripts `chat = agent.cli:main` and `chat-runtime = agent.runtime:main`.
- `chat/Dockerfile`: ARM64 runtime container, port 8080, installed `chat-runtime`.
- `chat/`: Python >=3.12 uv project with its own lockfile. The local-only `voice/`
  project has separate dependencies; do not add audio libraries or Swift to chat.
- `chat/.python-version`: selects Python 3.12, matching Docker. Use uv-managed
  Python for the local environment to avoid broken Homebrew interpreter links.
- [README.md](README.md): orientation; [chat/README.md](chat/README.md): setup,
  deployment, and troubleshooting; [docs/chat-flow.md](docs/chat-flow.md): diagram.

## Commands and configuration

From the repository root:

```bash
uv python install 3.12
uv sync --project chat --locked --managed-python
uv run --directory chat chat
# Only if the ignored local voice project is present:
uv run --directory voice brainstorm
```

Inside `chat/`, use `uv run chat`. This invokes AWS, so it is not an offline
smoke check. `chat-runtime` is the container's server entry point; optional local
HTTP diagnostics are documented in the chat README.

The user supplies configuration; use direct `os.environ` reads without defaults,
custom environment validation, or CLI overrides. The local CLI reads
`AWS_PROFILE`, `AWS_REGION`, and `AGENTCORE_RUNTIME_ARN`. The runtime reads
`AWS_REGION`, `CHAT_MODEL`, `AGENTCORE_MEMORY_ID`, `CHAT_ACTOR_ID`, and
`AGENTCORE_GATEWAY_URL`; these
runtime settings are not sent by the CLI.
The Gateway uses IAM authentication; grant the runtime role
`bedrock-agentcore:InvokeGateway` on its ARN and use a Gateway in `AWS_REGION`.
Local `.env` files load from the working directory without overriding shell
variables. `chat/.env.example` has example values, not application defaults.

Hosted runtime credentials come from its execution role. Use boto3's normal
credential chain in the runtime; do not require a local AWS profile there or
bake credentials/configuration files into an image. Configure the hosted model
and region in AgentCore. Deployment commands are in `chat/README.md`.

Prefer the CDK workflow in `infra/README.md` for new infrastructure deployments.
From `infra/`, use `uv sync --locked --managed-python`, `npm ci`, and
`npx cdk synth --quiet` for local validation. Bootstrap and deploy mutate AWS;
run them only when deployment is requested. CDK packages the shared Lambda with
uv and builds the ARM64 chat image. `services/ecr.py` explicitly creates
`agentcore-chat-cdk`, then copies the bootstrap image asset into it. Runtime
creation depends on image publication and pulls only from this application
repository. Image publishing permissions are scoped in `services/iam.py`.
Destroy deletes the application's Memory, conversation events, ECR repository,
and images. Bootstrap
assets and old manual resources remain outside that cleanup. Voice remains excluded.

## Behavior to preserve

The CLI starts with a fresh UUID, reuses it for follow-ups, and creates a new ID
for `/new`. It attempts to stop invoked sessions on reset/exit and closes response
bodies. Failed cleanup can leave a session running until timeout.

AgentCore Memory events persist independently of runtime compute, scoped by
resource, configured actor, and session ID. `/session` displays the UUID and
`/resume <UUID>` selects saved history; `/new` does not erase prior events.
This is a single-user prototype, not per-user authorization. Use one caller per
conversation; a process lock does not provide distributed serialization.
No long-term strategies or RAM fallback. Save only non-empty `end_turn` replies;
failed inference or other generation stop reasons write nothing.
Memory errors surface. Unknown write outcomes or lost responses can leave a
saved turn the caller did not see, and user retries can duplicate turns.
There is no history trimming or transcript export; CloudWatch can contain text.
Deleting runtime compute does not delete the separate Memory resource.
Keep application logging concise and avoid adding secret or payload dumps.
`uv run chat` appends request/SDK and session-cleanup exceptions to `error.log`
in the current working directory, with timestamps, session IDs, and tracebacks.
Log files are ignored by Git. Keep the normal CLI as the user's entry point;
do not redirect CLI error logging work into a local HTTP debugging workflow.
A generic AWS 500 cannot expose a server exception the SDK did not return.

## Verification and maintenance

Automated test files remain deferred unless requested. Use focused offline
checks for configuration wiring, multi-turn memory, failed-turn behavior,
session reset/isolation, and cleanup. Do not mistake imports or local HTTP
checks for a verified deployment. Report live AWS verification separately.

The user confirmed the manual chat and Gateway tool working on 2026-10-04,
using `testing_local_1-Pgyd5WH6O4` in `eu-west-1`. That manual Runtime, Memory,
Gateway/target, Lambda, ECR repository, four experiment roles and two customer
policies were deleted later that day for the CDK migration. Their four remaining
CloudWatch groups and all three related log deliveries, sources, and destinations
were also deleted and verified absent. The shared CDK bootstrap repository was preserved.
The user confirmed successful CDK deployment on 2026-10-04. Live chat, memory,
and Gateway acceptance checks for the CDK deployment remain pending.
The caller needed a separate IAM policy allowing `sts:AssumeRole` on the four
CDK bootstrap deployment, file-publishing, image-publishing, and lookup roles.
This caller setup is outside the application stack and precedes deployment.
The previous live confirmation does not establish that
every failure, restart/resume, or session-isolation case was tested. The chat
README contains acceptance checks. Future source changes require an image rebuild
and runtime update; pushing the image alone is insufficient. Do not redeploy
unless the user requests it, or reintroduce the old `agentcore_chat` package path.

Verify current official AWS documentation before changing API/runtime assumptions.
Keep generated files, `.env`, `.venv/`, session artifacts, and AWS secrets out of
Git. Avoid reading private configuration or recordings unless needed. Preserve
unrelated user changes; untracked files are not disposable. Documentation review
alone does not authorize cloud deployments or resource changes.

Test Gateway tools through the chat agent with `uv run chat` after integration.
Do not add a separate manual MCP diagnostic workflow unless the user asks.
