# Project guidance for agents

Read this file at the start of conversations in this repository. Inspect the
relevant source before changing behavior and keep this guidance current.
The user's current instructions take precedence.

## Goal and scope

Experiment with Amazon Bedrock AgentCore using a minimal text conversation:
the user asks, the agent replies, and follow-ups reuse short-term agent memory.
Keep the implementation small. No tools, RAG, UI, summaries, persistent memory
service, or new voice work is needed unless the user changes the scope.

The active project is `chat/`. The preserved voice prototype is local-only in
`voice/`, ignored by Git and excluded from pushes. If present, read its local
`voice/AGENTS.md` when working there. Do not include voice files in a commit
unless the user explicitly resumes that project and asks to track it.

## Layout and entry points

- `chat/src/agent/agent.py`: boto3 Bedrock Converse call and one conversation's
  message list. Commit a turn only after a valid text reply.
- `chat/src/agent/cli.py`: local terminal UI calling the deployed AgentCore
  `DEFAULT` endpoint, with `/new`, `/exit`, and remote session cleanup.
- `chat/src/agent/runtime.py`: `BedrockAgentCoreApp`, conversations keyed by
  session ID, and a global lock serializing invocations.
- `chat/pyproject.toml`: distribution `agentcore-chat`, Python package `agent`,
  console scripts `chat = agent.cli:main` and `chat-runtime = agent.runtime:main`.
- `chat/Dockerfile`: ARM64 runtime container, port 8080, installed `chat-runtime`.
- `chat/`: Python >=3.12 uv project with its own lockfile. The local-only `voice/`
  project has separate dependencies; do not add audio libraries or Swift to chat.
- [README.md](README.md): orientation; [chat/README.md](chat/README.md): setup,
  deployment, and troubleshooting; [docs/chat-flow.md](docs/chat-flow.md): diagram.
- [TODO.md](TODO.md): verification history. `voice/TODO.md` is the earlier voice plan.

## Commands and configuration

From the repository root:

```bash
uv sync --project chat --locked
uv run --directory chat chat
uv run --directory chat chat-runtime
# Only if the ignored local voice project is present:
uv run --directory voice brainstorm
```

Run the two chat commands separately: `chat` invokes AWS; `chat-runtime` starts
an HTTP server locally for curl checks. Neither is an offline smoke check.
Inside `chat/`, use `uv run chat` or `uv run chat-runtime`.

The user supplies configuration; use direct `os.environ` reads without defaults,
custom environment validation, or CLI overrides. The local CLI reads
`AWS_PROFILE`, `AWS_REGION`, and `AGENTCORE_RUNTIME_ARN`. The runtime reads
`AWS_REGION` and `CHAT_MODEL`; a local copy of CHAT_MODEL is not sent by the CLI.
Local `.env` files load from the working directory without overriding shell
variables. `chat/.env.example` has example values, not application defaults.

Hosted runtime credentials come from its execution role. Use boto3's normal
credential chain in the runtime; do not require a local AWS profile there or
bake credentials/configuration files into an image. Configure the hosted model
and region in AgentCore. Deployment commands are in `chat/README.md`.

## Behavior to preserve

The CLI starts with a fresh UUID, reuses it for follow-ups, and creates a new ID
for `/new`. It attempts to stop invoked sessions on reset/exit and closes response
bodies. Failed cleanup can leave a session running until timeout.

Agent memory is an in-process message list, not the AgentCore Memory service.
Stopping/restarting/expiring runtime compute loses it. The runtime isolates local
HTTP sessions by session ID. There is no history trimming, transcript export,
or application persistence; CloudWatch logs can still contain invocation text.
Keep application logging concise and avoid adding secret or payload dumps.

## Verification and maintenance

Automated test files remain deferred unless requested. Use focused offline
checks for configuration wiring, multi-turn memory, failed-turn behavior,
session reset/isolation, and cleanup. Do not mistake imports or local HTTP
checks for a verified deployment. Report live AWS verification separately.

Hosted reply/memory/isolation checks passed on 2026-10-01 before the package
rename from `agentcore_chat` to `agent`; local entry points were verified after
that rename. Later source changes need an image rebuild and runtime update.
Do not reintroduce old package paths or claim an older cloud test validates new code.

Verify current official AWS documentation before changing API/runtime assumptions.
Keep generated files, `.env`, `.venv/`, session artifacts, and AWS secrets out of
Git. Avoid reading private configuration or recordings unless needed. Preserve
unrelated user changes; untracked files are not disposable. Documentation review
alone does not authorize cloud deployments or resource changes.
