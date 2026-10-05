# Shared tools

This directory contains tools exposed through AgentCore Gateway. They remain
independent of the chat package so an agent can call them through MCP without
importing another application's code.

| Directory | Tool | Documentation |
| --- | --- | --- |
| `runtime_status/` | `get_runtime_status`: reads one runtime's deployment status | [Contract, packaging, and verification](runtime_status/README.md) |

## How tools are connected

Each tool owns its implementation, SDK requirements, and Gateway schema.
[The CDK project](../infra/README.md) packages the Lambda, registers its Gateway
target, and grants the required permissions. The Runtime authenticates to
Gateway with its execution role; Gateway uses its own role to invoke Lambda.

## Run and verify

There is no executable or Python environment at the `tools/` directory level.
Deploy using the commands in `infra/README.md`, then check the tool through the
[chat CLI](../chat/README.md#verify-the-deployed-application):

```bash
# From the repository root, with chat configured:
uv run --directory chat chat
```

For optional standalone ZIP packaging, follow the tool's own README.
