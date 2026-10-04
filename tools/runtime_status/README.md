# Runtime status tool

A shared Lambda function for the text and future voice agents. It calls
AgentCore's `GetAgentRuntime` API and returns the requested runtime's deployment
status. It has no dependency on either agent's Python package.

## Files and configuration

- `handler.py`: Lambda entry point `handler.lambda_handler`.
- `requirements.txt`: SDK to include in the Lambda deployment package.
- `tool-schema.json`: tool definitions to register inline on a Gateway Lambda target.

The user supplies the runtime ID in chat, and the agent passes it as a tool
argument. Lambda provides `AWS_REGION`; deploy the function in the runtimes' region.
Credentials come from the Lambda execution role. No local AWS profile is needed.

For a message such as “Is the environment ready for runtime
example_runtime-AbCdEf1234?”, the tool input is:

```json
{"runtime_id": "example_runtime-AbCdEf1234"}
```

Use a real AWS runtime ID, which has the form `name-10CharacterSuffix`, rather
than an ARN or a made-up ID. AWS validates the ID and reports invalid or missing
runtimes. If the chat message omits the ID, the agent should ask for it.

The result looks like:

```json
{
  "runtime_id": "example_runtime-AbCdEf1234",
  "name": "example_runtime",
  "status": "READY",
  "version": "1"
}
```

`READY` describes the runtime deployment. It does not check model access, memory
permissions, the status of individual sessions, or the success of a chat request.
Without a version argument, the API retrieves the latest runtime version; this
can differ from the version served by the chat CLI's `DEFAULT` endpoint.
The result deliberately excludes runtime environment variables and credentials.
SDK failures propagate as Lambda errors rather than being reported as a status.
Lambda's normal error logging records uncaught exceptions in CloudWatch.

## AWS CLI prerequisite

Use a current AWS CLI v2 and export your profile before running AWS commands:

```bash
export AWS_PROFILE=default
export AWS_REGION=eu-west-1
export PATH="/usr/local/bin:$PATH"
rehash
command -v aws
aws --version
```

On this Mac, `command -v aws` should show `/usr/local/bin/aws`, the standalone
AWS CLI. The Homebrew executable currently fails with a Python `pyexpat` /
`libexpat` error. Repeat the PATH selection in new terminals or add it to
`~/.zshrc`. The AWS CLI does not load `chat/.env`.

If the standalone CLI is not installed:

```bash
curl -fL https://awscli.amazonaws.com/AWSCLIV2.pkg -o /tmp/AWSCLIV2.pkg
sudo installer -pkg /tmp/AWSCLIV2.pkg -target /
/usr/local/bin/aws --version
```

The commands below describe first-time setup in account `781356123457`, region
`eu-west-1`. These resources already exist for this experiment; skip creation
when reusing them. For another account, replace the account IDs in the ARNs.

## Step 1: Package the Lambda

From the repository root, paste this block into your terminal to build a ZIP
for Python 3.12 on Lambda ARM64. Requires `uv` and `zip`:

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
```

The result is `tools/runtime_status/runtime-status.zip`, ignored by Git.
uv installs the dependencies and `zip` packages them with the handler. The block
stops on failure and removes its temporary build folder on exit. From inside
`tools/runtime_status/`, omit the `cd tools/runtime_status` line.
uv is used during packaging; Lambda executes the Python handler directly.

Check its contents:

```bash
unzip -l tools/runtime_status/runtime-status.zip
```

You should see `handler.py`, `boto3/`, and `botocore/` at the ZIP root, alongside
the SDK's other dependencies. Do not zip the enclosing `runtime_status/` folder.
The tool schema is registered separately with Gateway and is not needed in the ZIP.

This only builds the package locally. When creating Lambda in the next step,
select **Python 3.12**, **ARM64**, upload this ZIP, and set the handler to
`handler.lambda_handler`.

## Step 2: Create and test the Lambda

Run from the repository root with AWS CLI v2 and `AWS_PROFILE` exported in
your terminal; the CLI does not load `chat/.env`. These commands explicitly
target `eu-west-1`, where this experiment runs, and create AWS resources.
Your caller needs IAM role/policy management, `iam:PassRole`, and Lambda
creation/invocation permissions.

The Lambda commands and runtime-read policy use `eu-west-1` directly, so they
cannot silently use a different region from your AWS profile. IAM roles are
global; their policy restricts runtime reads to `eu-west-1`.

Create a dedicated execution role trusted by Lambda:

```bash
aws iam create-role \
  --role-name agentcore-runtime-status-lambda \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
  --query Role.Arn --output text

aws iam attach-role-policy \
  --role-name agentcore-runtime-status-lambda \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam put-role-policy \
  --role-name agentcore-runtime-status-lambda \
  --policy-name ReadRuntimeStatus \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"bedrock-agentcore:GetAgentRuntime","Resource":"arn:aws:bedrock-agentcore:eu-west-1:781356123457:runtime/*"}]}'
```

The role grants log writing and read-only runtime inspection in this account
and region. Allow a short time for IAM propagation, then create the function:

```bash
aws lambda create-function \
  --region eu-west-1 \
  --function-name agentcore-runtime-status \
  --runtime python3.12 \
  --architectures arm64 \
  --handler handler.lambda_handler \
  --role arn:aws:iam::781356123457:role/agentcore-runtime-status-lambda \
  --zip-file fileb://tools/runtime_status/runtime-status.zip \
  --timeout 30 \
  --memory-size 256

aws lambda wait function-active-v2 \
  --region eu-west-1 \
  --function-name agentcore-runtime-status
```

If creation says the role cannot be assumed, wait briefly and retry
`create-function`; do not recreate the role. These are first-time creation
commands, not commands to update an existing function.

Invoke it directly. This example uses the runtime successfully checked on
2026-10-04; replace the ID if you are inspecting a different runtime:

```bash
runtime_status_response=$(mktemp)
aws lambda invoke \
  --region eu-west-1 \
  --function-name agentcore-runtime-status \
  --cli-binary-format raw-in-base64-out \
  --payload '{"runtime_id":"testing_local_1-Pgyd5WH6O4"}' \
  "$runtime_status_response"
cat "$runtime_status_response"
```

A successful result has the runtime ID, name, status, and version. Check the
response body and absence of `FunctionError`; invocation `StatusCode: 200` alone
does not mean the handler succeeded. Errors also appear in
`/aws/lambda/agentcore-runtime-status` in CloudWatch.

## Step 3: Create Gateway and register the tool

Run from the repository root using the same AWS profile. These first-time setup
commands use account `781356123457` and `eu-west-1`. Your caller needs IAM
role/policy management, `iam:PassRole`, and Gateway creation, target creation,
and read permissions. Run each block only after the previous block succeeds.

Use the standalone CLI selected above. Older CLI API models may incorrectly
require `--authorizer-configuration` for `AWS_IAM`; update the CLI rather than
adding JWT configuration. That configuration applies to `CUSTOM_JWT`.

Create a separate Gateway execution role. AgentCore assumes this role to invoke
our Lambda; it does not need the Lambda's runtime-read permissions.

```bash
aws iam create-role \
  --role-name agentcore-tools-gateway \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{
      "Effect":"Allow",
      "Principal":{"Service":"bedrock-agentcore.amazonaws.com"},
      "Action":"sts:AssumeRole",
      "Condition":{
        "StringEquals":{"aws:SourceAccount":"781356123457"},
        "ArnLike":{"aws:SourceArn":"arn:aws:bedrock-agentcore:eu-west-1:781356123457:gateway/*"}
      }
    }]
  }'

aws iam put-role-policy \
  --role-name agentcore-tools-gateway \
  --policy-name InvokeRuntimeStatusLambda \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[{
      "Effect":"Allow",
      "Action":"lambda:InvokeFunction",
      "Resource":"arn:aws:lambda:eu-west-1:781356123457:function:agentcore-runtime-status"
    }]
  }'
```

Allow time for IAM propagation, then create the MCP Gateway with IAM inbound
authentication. Keep the returned ID in this terminal:

```bash
tools_gateway_id=$(aws bedrock-agentcore-control create-gateway \
  --region eu-west-1 \
  --name agentcore-tools \
  --role-arn arn:aws:iam::781356123457:role/agentcore-tools-gateway \
  --protocol-type MCP \
  --authorizer-type AWS_IAM \
  --query gatewayId --output text)

aws bedrock-agentcore-control get-gateway \
  --region eu-west-1 \
  --gateway-identifier "$tools_gateway_id" \
  --query '{id:gatewayId,status:status,url:gatewayUrl,arn:gatewayArn}'
```

If the role cannot be assumed, wait briefly and retry creation. Wait until
`get-gateway` reports `READY` before adding the target. If creation already
succeeded, reuse its ID rather than creating another Gateway. In a new terminal,
restore this experiment's existing ID before registering or checking targets:

```bash
tools_gateway_id="agentcore-tools-j4l3ivunkl"
```

For another Gateway, use the ID returned by creation.

Register the existing Lambda with the tool definitions from this repository:

```bash
runtime_status_schema=$(cat tools/runtime_status/tool-schema.json)
runtime_status_target_id=$(aws bedrock-agentcore-control create-gateway-target \
  --region eu-west-1 \
  --gateway-identifier "$tools_gateway_id" \
  --name runtime-status \
  --target-configuration "{\"mcp\":{\"lambda\":{\"lambdaArn\":\"arn:aws:lambda:eu-west-1:781356123457:function:agentcore-runtime-status\",\"toolSchema\":{\"inlinePayload\":$runtime_status_schema}}}}" \
  --credential-provider-configurations '[{"credentialProviderType":"GATEWAY_IAM_ROLE"}]' \
  --query targetId --output text)

aws bedrock-agentcore-control get-gateway-target \
  --region eu-west-1 \
  --gateway-identifier "$tools_gateway_id" \
  --target-id "$runtime_status_target_id" \
  --query '{id:targetId,status:status,reasons:statusReasons}'
```

The target must reach `READY`. Gateway exposes the tool with a target prefix:
`runtime-status___get_runtime_status`. The next step is to connect the chat agent
and grant its runtime role `bedrock-agentcore:InvokeGateway` on the returned
Gateway ARN. Creating the target alone does not verify
end-to-end tool invocation.

## Step 4: Connect and test through the chat agent

The chat agent implements tool discovery and execution. Follow
[Connect Gateway tools](../../chat/README.md#connect-gateway-tools) to give the
chat runtime's execution role Gateway invocation permission, configure the
Gateway URL, rebuild the image, and update the runtime.

After deployment or when checking the existing integration, test from `chat/`:

```bash
uv run chat
```

Ask “Is the environment ready for runtime testing_local_1-Pgyd5WH6O4?”
The agent should call `get_runtime_status` through Gateway and explain the
returned status. Also check a normal greeting and a tool failure. A normal text
reply alone does not verify tool invocation; verify that the tool was called.
There is no separate manual MCP test required for this project.

## Connecting it to both agents

The intended path is:

```text
Text or voice agent → AgentCore Gateway (MCP) → Lambda → GetAgentRuntime
```

This Lambda is the tool implementation; Gateway provides the MCP endpoint.
It implements a single tool, so it does not need to dispatch using Gateway's
prefixed tool name. Both agents can use the same Gateway tool and Lambda.
The input determines which runtime they inspect, within the Lambda's AWS account,
region, and IAM permissions. Both agents use the same `runtime_id` input contract.

For deployment, the Lambda execution role needs normal CloudWatch logging
permissions and this policy. Replace `YOUR_ACCOUNT_ID` with the account
whose runtimes the tool can inspect; this example targets `eu-west-1`. Use explicit runtime ARNs instead of
`runtime/*` if access should be limited to particular runtimes.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock-agentcore:GetAgentRuntime",
      "Resource": "arn:aws:bedrock-agentcore:eu-west-1:YOUR_ACCOUNT_ID:runtime/*"
    }
  ]
}
```

Step 3 grants the Gateway execution role permission to invoke this Lambda.
The chat runtime's execution role also has Gateway invocation permission.
The future voice agent will need the same permission when connected.

## Verification status

On 2026-10-04, the user deployed the Lambda in `eu-west-1` and successfully
invoked it for `testing_local_1-Pgyd5WH6O4`: deployment status `READY`, version `4`.
The user also created the IAM-authenticated Gateway and reported its Lambda
target as `READY`. The commands used are documented in steps 2 and 3 above.

The user reported the complete deployed chat → Gateway → Lambda flow working
through `uv run chat` on 2026-10-04. The Gateway is
`agentcore-tools-j4l3ivunkl`. This is user-reported live verification; subsequent
source changes still require packaging and deployment before they are verified.

References: [GetAgentRuntime API](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_GetAgentRuntime.html),
[Gateway Lambda targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html),
[Python Lambda ZIP packaging](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html),
[CreateFunction CLI](https://docs.aws.amazon.com/cli/latest/reference/lambda/create-function.html),
[Invoke CLI](https://docs.aws.amazon.com/cli/latest/reference/lambda/invoke.html).
