# Minimal chat agent

A terminal chat backed by an AgentCore Runtime in AWS. The runtime's agent memory
stores the current conversation in a Python list and sends it to the Bedrock
inference model with each new message. There are no tools or persistent memory.
See [the chat flow diagram](../docs/chat-flow.md) for the local/cloud boundary.

## Setup and configuration

Run the commands in this README from `chat/`. Requires Python 3.12+, `uv`, an
AWS profile, and a deployed runtime implementing this project's JSON interface.

```bash
uv sync --locked
```

For first-time setup, copy `.env.example` to `.env`; otherwise edit the existing
file. The example uses `eu-west-1` and `eu.amazon.nova-lite-v1:0`. Those are example
values, not application defaults.

| Variable | CLI on your Mac | Hosted runtime in AWS |
| --- | --- | --- |
| `AWS_PROFILE` | Required; names your local AWS profile | Use the execution role; do not configure a local profile name |
| `AWS_REGION` | Required; region of the AgentCore runtime | Required by the agent; region used for Bedrock calls |
| `AGENTCORE_RUNTIME_ARN` | Required; your deployed runtime ARN | Not read by the agent |
| `CHAT_MODEL` | Not read or sent by the CLI | Required; Bedrock model or inference profile ID |

Both entry points load `.env` from their working directory, with existing shell
variables taking precedence. Configuration is read directly from `os.environ`,
with no application defaults, CLI overrides, or custom configuration validation.
The Docker image excludes `.env`: configure hosted values on the runtime itself.
For local runtime testing, the same `chat/.env` can contain all four variables.

Your local profile needs `bedrock-agentcore:InvokeAgentRuntime` and
`bedrock-agentcore:StopRuntimeSession`. The hosted execution role needs image
pull/logging permissions and `bedrock:InvokeModel` access to the selected model
or inference profile and its destination models. See
[AWS runtime permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html).

## Chat

```bash
uv run chat
```

The CLI always invokes AgentCore's `DEFAULT` endpoint. It sends
`{"prompt":"..."}` and expects `{"reply":"..."}`. It waits for a complete reply
before displaying it; responses are not streamed to the terminal.

- Follow-up messages reuse one UUID session ID and the same agent memory.
- `/new` attempts to stop the old session and creates a fresh session ID.
- `/exit`, Ctrl+C, or EOF exits and attempts to stop an invoked session.
- Blank input is ignored. Invocation errors are printed and the loop continues.

The runtime commits a user/assistant turn only after a valid text reply. Memory
is held only in its process. Stopping, restarting, or expiring its compute loses
that memory; cleanup failure can leave the old session running until timeout.
The agent has no automatic history limit or summarization, so long conversations
can exceed the model's context window. No transcript files or memory resources
are created by the application. CloudWatch logs can still contain request text.
See [AWS session behavior](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html).

## Local HTTP check

This runs the AgentCore SDK server locally while still calling Bedrock for
inference. It does not test hosted AgentCore deployment. Set `AWS_REGION` and
`CHAT_MODEL` in `chat/.env` and use local AWS credentials with model access:

```bash
uv run chat-runtime
```

The server binds to port 8080. In another terminal:

```bash
curl http://localhost:8080/ping
curl http://localhost:8080/invocations \
  -H 'Content-Type: application/json' \
  -H 'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: 11111111-1111-4111-8111-111111111111' \
  -d '{"prompt":"My name is Ivan. Reply briefly."}'
curl http://localhost:8080/invocations \
  -H 'Content-Type: application/json' \
  -H 'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: 11111111-1111-4111-8111-111111111111' \
  -d '{"prompt":"What is my name?"}'
```

The same session ID preserves context; a different ID starts with empty memory.
Restarting the local server clears all sessions. The CLI targets hosted
AgentCore, so use HTTP requests for this local check. Invocations incur Bedrock
charges. This server is for local experimentation.

## Deploy the container

The [AWS container deployment guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html)
requires ARM64 Linux and an HTTP server on port 8080 with `/ping` and
`/invocations`. The Dockerfile starts `/app/.venv/bin/chat-runtime`, whose entry
point is `agent.runtime:main`.

Run these commands from `chat/`, with Docker running. Set your real account ID
and the region where you will deploy. AWS CLI and Docker do not load `chat/.env`.

```bash
export AWS_PROFILE=default
export AWS_REGION=eu-west-1
export CHAT_ACCOUNT_ID=YOUR_ACCOUNT_ID
export CHAT_ECR_HOST="$CHAT_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
```

Create the ECR repository once; skip this command if it already exists:

```bash
aws ecr create-repository \
  --repository-name agentcore-chat \
  --region "$AWS_REGION"
```

Log in, build, and push:

```bash
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$CHAT_ECR_HOST"

docker buildx build \
  --platform linux/arm64 \
  -t "$CHAT_ECR_HOST/agentcore-chat:latest" \
  --push .
```

`CHAT_ECR_HOST` contains only the registry hostname. The repository name is added
once in the tag; adding it to both produces `agentcore-chat/agentcore-chat`.

In the Bedrock AgentCore console, create or update an HTTP runtime using that
ECR image and an execution role with the permissions described above. Configure
`AWS_REGION` and `CHAT_MODEL` on the runtime. Keep local profile names and
credentials out of the container. Wait until the runtime and its `DEFAULT`
endpoint are ready, then set its ARN in `chat/.env` and run `uv run chat`.

For later source or package changes, rebuild and push the image, then update
the runtime to create a new version. Pushing a tag alone does not update the
running agent. Use `/new` or restart the CLI to test the updated version.

## Code and verification

| File | Responsibility |
| --- | --- |
| `src/agent/agent.py` | Bedrock Converse calls and per-conversation agent memory |
| `src/agent/cli.py` | Environment setup, invocation, terminal loop, session reset/cleanup |
| `src/agent/runtime.py` | AgentCore SDK HTTP entry point, session map, and lock |
| `pyproject.toml` | Package and console entry points: `agent.cli:main` and `agent.runtime:main` |

The runtime keys conversations by `context.session_id` and serializes invocations
with one lock, keeping local HTTP test sessions separate. Automated test files
are deferred. [The root plan](../TODO.md) records offline and hosted checks;
a past hosted check does not verify source changes made afterward.

## Runtime errors

For HTTP 500 errors, inspect the CloudWatch log group
`/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT`, especially streams
containing `[runtime-logs]`. Invocation request logs alone do not show the Python
exception. See [AWS troubleshooting](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-troubleshooting.html).

`KeyError: 'CHAT_MODEL'` means the hosted runtime is missing that environment
variable. The local `.env` is neither included in the image nor forwarded by the
CLI. Set the model and region on the runtime, wait for its update, then start a
fresh session. For Bedrock access errors, check the execution role's model and
inference-profile permissions separately from the local caller's runtime access.
