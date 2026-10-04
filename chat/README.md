# Minimal chat agent

A terminal chat backed by an AgentCore Runtime in AWS. The runtime's agent memory
stores conversation events in AgentCore Memory and sends the saved history to
the Bedrock inference model with each new message. There are no tools or
long-term memory strategies.
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
| `AGENTCORE_MEMORY_ID` | Not read by the CLI | Required; short-term Memory resource ID |
| `CHAT_ACTOR_ID` | Not read by the CLI | Required; stable actor ID, e.g. `ivan` |

Both entry points load `.env` from their working directory, with existing shell
variables taking precedence. Configuration is read directly from `os.environ`,
with no application defaults, CLI overrides, or custom configuration validation.
The Docker image excludes `.env`: configure hosted values on the runtime itself.
For local runtime testing, the same `chat/.env` can contain all six variables.

Your local profile needs `bedrock-agentcore:InvokeAgentRuntime` and
`bedrock-agentcore:StopRuntimeSession`. The hosted execution role needs image
pull/logging permissions and `bedrock:InvokeModel` access to the selected model
or inference profile and its destination models. It also needs
`bedrock-agentcore:ListEvents` and `bedrock-agentcore:CreateEvent` scoped to your
Memory resource ARN. The same permissions are needed by your local profile when
running `chat-runtime`. See
[AWS runtime permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html).

## Chat

```bash
uv run chat
```

The CLI always invokes AgentCore's `DEFAULT` endpoint. It sends
`{"prompt":"..."}` and expects `{"reply":"..."}`. It waits for a complete reply
before displaying it; responses are not streamed to the terminal.

- Follow-up messages reuse one UUID session ID and the same agent memory.
- `/new` attempts to stop the old compute session and creates a fresh session ID.
- `/session` displays the current UUID; save it to resume later.
- `/resume <UUID>` stops the current compute session and selects that conversation.
  History loads on your next message; an unknown UUID starts empty.
- `/exit`, Ctrl+C, or EOF exits and attempts to stop an invoked session.
- Blank input is ignored. Invocation errors are printed and the loop continues.

The runtime reads saved events before inference and saves one event containing
the successful user/assistant pair before returning the reply. Failed inference
or an empty reply writes nothing. A memory read/write error is surfaced, without
a fallback to RAM. A write whose outcome is unknown, or a lost response, can
leave a saved turn that the CLI did not display; retrying can create another turn.

Stopping compute does not delete memory. `/new` starts a separate conversation;
`/resume` reuses the saved history for the configured actor and session ID.
Events remain until their configured retention expires or you delete the Memory
resource. Cleanup failure can leave compute running until its timeout.
The agent has no automatic history limit or summarization, so long conversations
can exceed the model's context window. No transcript files are created. The Memory resource must be provisioned
separately; the application only reads and writes events. CloudWatch logs can still contain request text.
See [AWS session behavior](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html).

## Create short-term memory

This is a single-user experiment. `CHAT_ACTOR_ID` is set on the runtime, rather
than accepted from a caller. Anyone allowed to invoke this runtime can resume a
known session for that actor; this is not a multi-user authorization design.
Use one CLI at a time per conversation. The process lock does not coordinate
concurrent callers across separate compute sessions.

With `AWS_PROFILE` and `AWS_REGION` exported in your shell, create the resource
once (these commands create a billable AWS resource):

```bash
aws bedrock-agentcore-control create-memory \
  --name agentcore_chat_memory \
  --event-expiry-duration 3 \
  --region "$AWS_REGION" \
  --query 'memory.id' --output text
```

Copy the returned ID into `AGENTCORE_MEMORY_ID`. Set `CHAT_ACTOR_ID=ivan` in
`chat/.env` for local HTTP testing and on the hosted runtime for deployment.
Wait until the resource is `ACTIVE`:

```bash
aws bedrock-agentcore-control get-memory \
  --memory-id "$AGENTCORE_MEMORY_ID" \
  --region "$AWS_REGION" \
  --query 'memory.status' --output text
```

The shell command needs the memory ID exported separately from `.env`.
Three days is the minimum event retention. No long-term strategies are created;
turns also use `extractionMode=SKIP`. History is loaded with pagination and sorted
by event time. There is no context trimming, so keep learning sessions short.
See [AWS short-term memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-types.html).

To verify: tell the agent a synthetic fact, save `/session`, exit, restart the
runtime, then `/resume <UUID>` and ask about the fact. `/new` should not recall
it. Use synthetic data: messages now persist in AWS beyond compute shutdown.

For cleanup, delete the Memory resource separately from the runtime:

```bash
aws bedrock-agentcore-control delete-memory \
  --memory-id "$AGENTCORE_MEMORY_ID" \
  --region "$AWS_REGION"
```

This permanently removes the resource and its conversation data; stopping the
runtime alone does not perform this cleanup.

## Local HTTP check

This runs the AgentCore SDK server locally while still calling Bedrock for
inference. It does not test hosted AgentCore deployment. Set `AWS_REGION` and
`CHAT_MODEL`, `AGENTCORE_MEMORY_ID`, and `CHAT_ACTOR_ID` in `chat/.env` and use
local AWS credentials with model and memory access:

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
Restarting the local server preserves saved events in AgentCore Memory. The CLI targets hosted
AgentCore, so use HTTP requests for this local check. Invocations incur Bedrock and AgentCore Memory
charges. This server is for local experimentation.

## Deploy the container

The [AWS container deployment guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html)
requires ARM64 Linux and an HTTP server on port 8080 with `/ping` and
`/invocations`. The Dockerfile starts `/app/.venv/bin/chat-runtime`, whose entry
point is `agent.runtime:main`.

### 1. Set up your shell

Run from `chat/`, with Docker running and AWS CLI installed. These tools do not
load `.env`; export your profile and deployment region in the terminal:

```bash
export AWS_PROFILE=default
export AWS_REGION=eu-west-1
export CHAT_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export CHAT_ECR_HOST="$CHAT_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
export CHAT_IMAGE_URI="$CHAT_ECR_HOST/agentcore-chat:latest"
```

### 2. Create the ECR repository

Run once; skip if `agentcore-chat` already exists in this region:

```bash
aws ecr create-repository \
  --repository-name agentcore-chat \
  --region "$AWS_REGION"
```

### 3. Build and push the image

```bash
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$CHAT_ECR_HOST"

docker buildx build \
  --platform linux/arm64 \
  -t "$CHAT_IMAGE_URI" \
  --push .

aws ecr describe-images \
  --repository-name agentcore-chat \
  --image-ids imageTag=latest \
  --region "$AWS_REGION" \
  --query 'imageDetails[0].imageDigest' --output text

echo "$CHAT_IMAGE_URI"
```

The final commands confirm the uploaded image and print its URI for deployment.
`CHAT_ECR_HOST` is only the registry hostname; include `agentcore-chat` once in
the image URI to avoid the incorrect `agentcore-chat/agentcore-chat` path.

### 4. Deploy the AgentCore runtime

In the AWS console, select the same region and open **Bedrock AgentCore →
Runtime**:

1. Create a runtime using the ECR image URI printed above and the HTTP protocol.
2. Select an execution role with the [runtime permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)
   and Bedrock model access described in Setup. Use IAM authentication for this CLI.
3. Set runtime environment variables `AWS_REGION=eu-west-1` and
   `CHAT_MODEL=eu.amazon.nova-lite-v1:0` (or your chosen region/model), plus
   `AGENTCORE_MEMORY_ID` and `CHAT_ACTOR_ID` from the memory setup above.
4. Deploy, wait until the runtime and its `DEFAULT` endpoint are ready, and copy
   the runtime ARN.

The hosted runtime uses its execution role; do not configure `AWS_PROFILE` or
copy local credentials into the image.

### 5. Connect the CLI

Set `AGENTCORE_RUNTIME_ARN` to the copied ARN in `chat/.env`, keeping your local
`AWS_PROFILE` and matching `AWS_REGION`, then run:

```bash
uv run chat
```

For later changes, repeat step 3, then update the existing runtime to create a
new version using the pushed image and wait for its `DEFAULT` endpoint to be
ready. Pushing the image alone does not update the running agent. Start a fresh
conversation with `/new` or restart the CLI.

## Code and verification

| File | Responsibility |
| --- | --- |
| `src/agent/agent.py` | Bedrock Converse calls using retrieved history |
| `src/agent/cli.py` | Environment setup, invocation, terminal loop, session reset/cleanup |
| `src/agent/runtime.py` | AgentCore SDK HTTP entry point and process lock |
| `src/agent/memory.py` | Paginated event reads and successful-turn writes |
| `pyproject.toml` | Package and console entry points: `agent.cli:main` and `agent.runtime:main` |

Memory is scoped by resource ID, configured actor ID, and `context.session_id`.
The runtime serializes invocations within one process. Automated test files
are deferred. [The root plan](../TODO.md) records offline and hosted checks;
a past hosted check does not verify source changes made afterward.

## Runtime errors

`uv run chat` appends SDK and other request errors to `error.log` in the current
working directory (`chat/error.log` when run from `chat/`). Entries include a
timestamp, session ID, exception message, and CLI traceback. Session cleanup
failures are logged too. The terminal still displays the error and keeps chatting.
Log files are ignored by Git; prompts, replies, and credentials are not deliberately
logged.

The file contains the error returned by the AWS SDK. If AWS returns only a generic
500, it cannot reveal the server's internal exception; that detail still requires
the runtime CloudWatch logs.

`KeyError: 'AGENTCORE_MEMORY_ID'` or `'CHAT_ACTOR_ID'` means hosted memory
configuration is missing. Memory access errors require checking the execution
role permissions and that the resource is active in the configured region.

For HTTP 500 errors, inspect the CloudWatch log group
`/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT`, especially streams
containing `[runtime-logs]`. Invocation request logs alone do not show the Python
exception. See [AWS troubleshooting](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-troubleshooting.html).

`KeyError: 'CHAT_MODEL'` means the hosted runtime is missing that environment
variable. The local `.env` is neither included in the image nor forwarded by the
CLI. Set the model and region on the runtime, wait for its update, then start a
fresh session. For Bedrock access errors, check the execution role's model and
inference-profile permissions separately from the local caller's runtime access.
