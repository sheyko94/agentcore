# CDK infrastructure

Deploy the text agent and shared runtime-status tool with one Python CDK stack.
See [the AWS architecture diagrams](../docs/aws-architecture.md) for service,
account, and deployment boundaries.
Run commands below from `infra/`. Source stays in `chat/` and
`tools/runtime_status/`; infrastructure imports neither application's package.

## Resources

`AgentCoreChatDev` targets account `781356123457`, region `eu-west-1`:

- ARM64 Runtime named `agentcore_chat_cdk`, built from the existing Dockerfile.
- Application ECR repository named `agentcore-chat-cdk`, explicitly created in `services/ecr.py`.
- New short-term Memory named `agentcore_chat_cdk_memory`, with three-day event retention.
- IAM-authenticated Gateway `agentcore-chat-cdk-tools` and `runtime-status` target.
- Python 3.12 ARM64 Lambda, packaged with the shared tool's SDK requirements.
- Execution roles and model, Memory, Gateway, Lambda, ECR, and logging permissions.
- Seven-day retention for Lambda logs and the runtime's default log group.

The first deployment creates all application resources from scratch.
The previous manual application resources were deleted on 2026-10-04 before
this migration, including their CloudWatch log groups and log-delivery records.
The shared CDK bootstrap repository was preserved. This stack does not import
existing application resources. The Lambda's generated name is printed as an output.

The new Memory starts empty. Old conversations are not copied or reused.
CDK passes the new Memory ID directly to the new Runtime and scopes its IAM
permissions to that resource. Memory is deleted with the stack, including all
conversation events, so destroying and redeploying starts fresh again.
Image deployment has an explicit order:

1. CDK builds and uploads the ARM64 image to its bootstrap ECR staging repository.
2. CloudFormation creates the application repository `agentcore-chat-cdk`.
3. An image-copy deployment helper copies the image into that repository, tagged
   with its source hash.
4. The Runtime is created or updated using the application repository's image URI.

The bootstrap staging repository is created separately by `cdk bootstrap`.
`services/ecr.py` contains the application repository creation and image-copy
definition. The manually created ECR repository is not used.

## File layout

`app.py` selects the account/region. `stack.py` wires the services and outputs.

| File | AWS resources |
| --- | --- |
| `services/agentcore.py` | AgentCore Memory, Runtime, Gateway, and target |
| `services/lambda_service.py` | Lambda function and uv packaging |
| `services/iam.py` | Roles and permission policies |
| `services/ecr.py` | Application ECR repository, ARM64 image asset, and image publication |
| `services/cloudwatch.py` | Log groups, retention, and cleanup |

## One-time setup

Requires `uv`, Node.js 22+, Docker Desktop running, and your working AWS profile.
The CDK CLI is pinned locally; no global CDK installation is needed.
From the repository root:

```bash
cd infra
uv python install 3.12
uv sync --locked --managed-python
npm ci
export AWS_PROFILE=default
export AWS_REGION=eu-west-1
```

CDK uses your profile directly, not the AWS CLI executable or `chat/.env`.
`cdk.json` selects the target account/region, actor, and Nova Lite inference
profile. Model IAM permissions cover Nova Lite; changing to another model also
requires updating its resource ARNs in `services/iam.py`.

Bootstrap once per account/region, unless already bootstrapped:

```bash
npx cdk bootstrap aws://781356123457/eu-west-1 --profile "$AWS_PROFILE"
```

Bootstrap creates CDK deployment roles, an S3 asset bucket, and an ECR asset
repository. Use a profile authorized to bootstrap/deploy: the earlier restricted
`local_development` IAM user may need additional permissions. CDK uses
CloudFormation and bootstrap roles; it does not bypass IAM restrictions.

After bootstrapping, the caller also needs `sts:AssumeRole` on these four roles
in account `781356123457`: `cdk-hnb659fds-deploy-role-781356123457-eu-west-1`,
`cdk-hnb659fds-file-publishing-role-781356123457-eu-west-1`,
`cdk-hnb659fds-image-publishing-role-781356123457-eu-west-1`, and
`cdk-hnb659fds-lookup-role-781356123457-eu-west-1`.
Configure this once through an authorized IAM administrator, before deploying
the application stack. Bootstrap does not grant these permissions to the caller.
Without them, CDK can fall back to the caller's own permissions and fail to
access the bootstrap asset bucket. The deployment role passes the configured
CloudFormation execution role, which uses `AdministratorAccess` by default.

## Deploy or update

```bash
npx cdk synth --quiet
npx cdk diff --profile "$AWS_PROFILE" --no-change-set
npx cdk deploy --profile "$AWS_PROFILE" --outputs-file outputs.json
```

Synthesis generates a template and bundles Lambda dependencies using `uv`.
It can download packages, but creates no AWS resources. Diff reads deployed
stack information; `--no-change-set` avoids creating a CloudFormation change set.
Deploy builds the ARM64 image, publishes image and Lambda assets, and creates or
updates the stack, including the explicit ECR repository and image publication.
The copy helper uses `cdk-ecr-deployment`, as recommended in the
[AWS image assets documentation](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ecr_assets/README.html).
CDK uses source hashes instead of a mutable `latest` image tag. `RepositoryUri`
and `ImageUri` outputs show the application repository and the Runtime's image.
No separate ZIP, ECR login/push, role-policy commands, or console runtime update
are required. AgentCore updates `DEFAULT` to the latest version; start a new chat
session after an update to use the new version.

For normal updates, repeat diff and deploy. Change code and redeploy instead of
editing stack-managed resources in the console.

## Use the chat agent

After deployment, select the runtime output and start the existing CLI:

```bash
export AGENTCORE_RUNTIME_ARN=$(uv run --locked python -c \
  'import json; print(json.load(open("outputs.json"))["AgentCoreChatDev"]["RuntimeArn"])')
cd ../chat
uv run chat
```

Alternatively, copy `RuntimeArn` into your existing `chat/.env`. Exported shell
values take precedence. Hosted model, actor, Memory, and Gateway settings come
from CDK; local copies are not forwarded by the CLI.
Your caller still needs `bedrock-agentcore:InvokeAgentRuntime` and
`bedrock-agentcore:StopRuntimeSession` for the new runtime ARN. CDK does not modify
the local IAM user's policies. Update an existing narrowly scoped caller policy
if it only permits the old runtime.

Ask for a greeting, then “Is the environment ready for runtime <RuntimeId>?”
using the new `RuntimeId` output. Confirm the CLI prints
`Tool: runtime-status___get_runtime_status` and the status. Use `/session` to save
a session ID and `/resume <ID>` to check persisted context. These are live AWS
checks; synthesis does not establish model access or hosted conversation behavior.

## Cleanup

From `infra/`:

```bash
npx cdk destroy --profile "$AWS_PROFILE"
```

This removes the stack's Runtime, Gateway/target, tool Lambda, execution roles,
Lambda log group, runtime default log group, and Memory with all conversation
events. It also empties and deletes the application ECR repository, including
its images. Old manually provisioned resources remain.

The shared `CDKToolkit` bootstrap stack, its asset bucket/repository, uploaded
assets, and deployment helpers' own Lambda logs are outside this cleanup.
They can retain storage charges. Check them separately when retiring this
experiment; do not delete shared bootstrap resources used by other applications.
Additional log destinations enabled manually are outside this stack.

## Verification

Local synthesis checks the template, IAM/resource wiring, tool schema, Lambda
packaging, and asset manifests. Deployment and hosted chat must be verified
separately. No AWS deployment was performed while adding this code.

The user confirmed successful CDK deployment on 2026-10-04 after configuring
the caller's bootstrap-role permissions. Live chat, memory, and Gateway
acceptance checks for this deployment remain pending.

References: [CDK assets](https://docs.aws.amazon.com/cdk/v2/guide/assets.html),
[CDK bootstrapping](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html),
[AgentCore CDK resources](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_bedrockagentcore.html),
[Runtime permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html).
