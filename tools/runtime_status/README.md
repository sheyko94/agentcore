# Runtime-status tool

`get_runtime_status` is a Python 3.12 ARM64 Lambda exposed through the
`runtime-status` Gateway target. It reads an AgentCore runtime's latest
deployment status using the control-plane `GetAgentRuntime` API.
It has no dependency on the chat package.

## Tool contract

The required `runtime_id` argument is the exact ID supplied by the user or
conversation, not an ARN. Obtain the deployed ID from `RuntimeId` in
`infra/outputs.json`. If no ID is supplied, the agent should ask for one.

This is an illustrative input; replace the placeholder with your real ID:

```json
{"runtime_id": "YOUR_RUNTIME_ID"}
```

The result has four fields:

```json
{
  "runtime_id": "YOUR_RUNTIME_ID",
  "name": "agentcore_chat_cdk",
  "status": "READY",
  "version": "1"
}
```

`READY` means deployment readiness. The tool does not check active sessions,
model access, Memory access, or successful chat requests. It reads the latest
runtime version, which can differ from the version served by `DEFAULT`.
SDK errors propagate as Lambda errors, and missing runtimes produce
`ResourceNotFoundException`. The response excludes environment variables and
credentials.

## How it works

```text
Chat agent → IAM-authenticated Gateway → Lambda → GetAgentRuntime
```

Gateway exposes `runtime-status___get_runtime_status`. The chat agent presents
`get_runtime_status` to Nova and maps it back when calling Gateway. The Lambda
implements a single tool and receives its arguments directly in the event.

| File | Purpose |
| --- | --- |
| `handler.py` | Entry point `handler.lambda_handler`; reads the runtime and returns the four result fields |
| `requirements.txt` | boto3 SDK dependencies packaged with the handler |
| `tool-schema.json` | Input/output schemas registered on the Gateway target |
| `.gitignore` | Excludes the optional generated ZIP |

Lambda supplies `AWS_REGION` and execution-role credentials. The Gateway,
Lambda, and runtime being inspected must use the configured region.
The Gateway role needs `lambda:InvokeFunction`; the Lambda role needs
`bedrock-agentcore:GetAgentRuntime` on permitted runtime ARNs and log-writing
permissions. CDK wires these roles separately from the chat Runtime role.

## Deploy and verify

Use [the CDK deployment commands](../../infra/README.md#deploy-or-update).
CDK packages the handler and SDK, registers the schema, and updates the Lambda.
There is no separate manual Lambda or Gateway creation step.

From the repository root, with the chat CLI configured:

```bash
uv run --directory chat chat
```

Ask “Check the deployment status of runtime <RuntimeId>” with the actual ID
from CDK outputs. Confirm the CLI prints
`Tool: runtime-status___get_runtime_status`, then ask “Check its status again”.
Also check that a missing ID prompts a question and a nonexistent ID produces
an explained failure. See [the chat acceptance checks](../../chat/README.md#verify-the-deployed-application).

## Optional standalone ZIP packaging

CDK handles packaging for normal deployments. To inspect a standalone package,
run this block from the repository root. Requires `uv` and `zip`; it builds for
Lambda's Python 3.12 ARM64 platform without creating AWS resources.

```bash
(
  set -e
  cd tools/runtime_status
  runtime_status_build=$(mktemp -d)
  trap 'rm -rf "$runtime_status_build"' EXIT
  uv pip install \
    --python-version 3.12 \
    --python-platform aarch64-manylinux2014 \
    --only-binary :all: \
    --target "$runtime_status_build/package" \
    --requirements requirements.txt
  cp handler.py "$runtime_status_build/package/"
  (
    cd "$runtime_status_build/package"
    zip -qr "$runtime_status_build/runtime-status.zip" . -x '*/__pycache__/*' '*.pyc'
  )
  cp "$runtime_status_build/runtime-status.zip" ./runtime-status.zip
)
unzip -l tools/runtime_status/runtime-status.zip
```

The ZIP contains `handler.py`, `boto3/`, `botocore/`, and their dependencies at
its root. The tool schema is registered separately and does not belong in the
Lambda ZIP. No build script is required.

References: [GetAgentRuntime](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_GetAgentRuntime.html),
[Gateway Lambda targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html),
[Lambda ZIP packaging](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html).
