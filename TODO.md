# AgentCore chat experiment

Current goal: a minimal text conversation that can run on AgentCore Runtime,
with short-term conversation events stored in AgentCore Memory.

- [x] Preserve the voice prototype as an independent project in `voice/`.
- [x] Keep voice local-only and ignored by Git while working on chat.
- [x] Add a minimal chat CLI and initial in-memory multi-turn history in `chat/`.
- [x] Implement AgentCore short-term event reads/writes and CLI session resumption.
- [ ] Provision Memory and verify persistence after a compute restart in AWS.
- [x] Add an AgentCore SDK runtime entry point and ARM64 Dockerfile.
- [x] Add CLI invocation of an already deployed AgentCore runtime.
- [x] Require AGENTCORE_RUNTIME_ARN for the CLI; remove direct Bedrock fallback.
- [x] Verify real Bedrock replies and follow-up context with the selected model.
- [x] Deploy the chat runtime to AgentCore and verify multi-turn session reuse.
- [x] Verify a fresh local conversation starts without previous context.
- [x] Verify a fresh deployed AgentCore session starts without previous context.

Verification: Nova Lite through `eu.amazon.nova-lite-v1:0` in `eu-north-1`
returned a reply, recalled a synthetic tag on a follow-up, and did not know it
in a fresh conversation. Offline checks covered failed-turn rollback and reset.
The AgentCore SDK local HTTP server passed `/ping`, reply serialization,
same-session context, and separate-session isolation using a fake model.
Hosted verification on 2026-10-01: the deployed container runtime in `eu-west-1`
returned a reply, recalled a synthetic tag across turns in the same session,
and returned UNKNOWN for that tag in a new session. Both temporary test sessions
were stopped. The initial HTTP 500 was caused by missing CHAT_MODEL in the
runtime environment; setting AWS_REGION and CHAT_MODEL resolved it in version 2.

Memory implementation checks on 2026-10-04 (offline, no AWS calls): SDK
request/response shapes, multi-page history ordering, restored context with a
new Chat instance, session isolation, failed inference/empty replies writing
nothing, surfaced memory-write errors, and CLI resume/reset passed. Live memory
provisioning and restart/resume verification remain pending.

Cleanup on 2026-10-01: deleted the test AgentCore runtime and all its versions,
the `agentcore-chat` ECR repository/images, and both related CloudWatch log
groups. Verified the runtime returned ResourceNotFound, the runtime list was
empty, and the chat repository and AgentCore log groups were absent in
`eu-west-1`. The unrelated CDK ECR repository was preserved. A new deployment
is required before the next hosted chat.

Keep the experiment small: no voice changes, tools, RAG, UI, long-term memory,
or separate persistence services. Automated test files remain deferred unless
requested; use focused manual/offline verification and report its limits.

The original voice plan and historical status are preserved locally in the
ignored `voice/TODO.md`; voice files are not included in repository pushes.

CLI error logging on 2026-10-04: `uv run chat` writes request and cleanup
exceptions to `error.log`. Offline checks cover an SDK 500, continued chatting,
and session cleanup failures. Server-side 500 diagnosis remains unverified.
