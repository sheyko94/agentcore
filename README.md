# AgentCore playground

A minimal text chat for experimenting with Amazon Bedrock AgentCore. The CLI
runs on your Mac; the Python agent runs in AWS, keeps the current conversation
in agent memory, and calls a Bedrock inference model for each reply.

The active experiment is `chat/`. The earlier voice prototype is preserved
locally in `voice/`, which is ignored by Git and not included in this repository.

| Directory | Purpose |
| --- | --- |
| [chat/](chat/README.md) | Text CLI, agent, and AgentCore runtime |
| [docs/](docs/chat-flow.md) | Mermaid diagram separating the local machine from AWS Cloud |

## Start a chat

Requires Python 3.12+, `uv`, an AWS profile, and a deployed chat runtime. Run from
the repository root:

```bash
cd chat
uv sync --locked
```

For first-time setup, copy `.env.example` to `.env`. If `.env` already exists,
edit it. Configure the local CLI with:

```dotenv
AWS_PROFILE=default
AWS_REGION=eu-west-1
AGENTCORE_RUNTIME_ARN=YOUR_DEPLOYED_RUNTIME_ARN
```

Then run from `chat/`:

```bash
uv run chat
```

From the repository root, the equivalent command is
`uv run --directory chat chat`. The CLI has no configuration flags or direct
Bedrock mode. It reads `.env` from its working directory without overriding
existing shell variables. `AWS_REGION` must match your runtime's region.

`CHAT_MODEL`, `AWS_REGION`, `AGENTCORE_MEMORY_ID`, and `CHAT_ACTOR_ID` must be
configured separately on the hosted runtime. Local `.env` values are not forwarded to AWS. See
[chat setup and deployment](chat/README.md) for the configuration table,
permissions, local HTTP checks, and Docker/ECR deployment steps.

## Conversation behavior

Type a message and receive a reply. Follow-ups reuse the same session ID and
agent memory. `/new` starts a fresh conversation; `/exit`, Ctrl+C, or EOF quits.
The CLI attempts to stop an invoked session on reset or exit. If cleanup fails,
the old session can remain until its configured timeout.

AgentCore Memory stores short-term conversation events beyond compute shutdown.
Use `/session` to get the UUID and `/resume <UUID>` to restore that conversation.
`/new` selects empty history without deleting older events. There is no automatic
history trimming or long-term memory strategy. Very long conversations can exceed the inference
model's context window. The CLI writes no transcript files; CloudWatch logs can
still contain invocation payloads and errors. AWS calls incur normal charges.

## Status and development

The test runtime, `agentcore-chat` ECR repository, and related CloudWatch log
groups in `eu-west-1` were deleted on 2026-10-01. AWS checks confirmed their
absence. Deploy a new runtime before using the CLI again.

A deployed container runtime in `eu-west-1` passed reply, follow-up memory, and
fresh-session isolation checks on 2026-10-01. That check preceded the package
rename to `chat/src/agent`; local entry points were verified after the rename.
Source changes require a new image and runtime update to reach AWS.
[TODO.md](TODO.md) records the verification history.

Keep the experiment small: text dialogue and short-term agent memory. There are
no tools, RAG, UI, summaries, or long-term memory. Automated test files remain
deferred; use focused offline checks and report live AWS verification separately.

If you have the preserved local `voice/` directory, run it from the repository root:

```bash
uv run --directory voice brainstorm
```

Its local `voice/README.md` contains installation, audio requirements, manual
checks, and remaining limitations. A fresh repository clone does not include it.
