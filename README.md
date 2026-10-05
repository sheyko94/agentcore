# AgentCore playground

A small project for learning Amazon Bedrock AgentCore through a text conversation.
You ask questions in a local Python CLI; an agent hosted in AWS replies using
Amazon Nova Lite, remembers follow-ups through short-term Memory, and can call
one shared tool through Gateway.

The experiment focuses on Runtime, Memory, Gateway, and the IAM permissions
connecting them. It has no RAG, UI, summaries, or long-term memory strategies.
The earlier voice prototype remains local-only in the ignored `voice/` folder.

## How the project fits together

- **Chat CLI:** runs on your machine and sends messages with a conversation ID.
- **AgentCore Runtime:** runs the Python agent in an ARM64 container.
- **LangChain:** runs the model/tool loop inside the container using Bedrock Converse.
- **AgentCore Memory:** stores LangGraph conversation/workflow checkpoints independently of runtime compute.
- **Amazon Bedrock:** generates replies with the configured Nova Lite inference profile.
- **AgentCore Gateway:** exposes the runtime-status Lambda as an IAM-authenticated MCP tool.
- **CDK infrastructure:** builds, provisions, and connects the application resources.

```mermaid
flowchart LR
    subgraph LOCAL["Local machine"]
        CLI["Chat CLI<br/>uv run chat<br/>AWS profile + session ID"]
    end

    subgraph CLOUD["AWS Cloud"]
        subgraph ACCOUNT["AWS account 781356123457"]
            subgraph REGION["Region eu-west-1"]
                subgraph AC["Amazon Bedrock AgentCore"]
                    RUNTIME["Runtime<br/>Python agent · ARM64<br/>DEFAULT endpoint"]
                    MEMORY[("Memory<br/>Workflow checkpoints<br/>actor + session · 3-day retention")]
                    GATEWAY["Gateway · MCP<br/>IAM authentication<br/>runtime-status target"]
                    CONTROL["AgentCore control API<br/>GetAgentRuntime<br/>Latest deployment status"]
                end
                PROFILE["Amazon Bedrock<br/>EU inference profile<br/>eu.amazon.nova-lite-v1:0"]
                TOOL["AWS Lambda<br/>get_runtime_status<br/>Python 3.12 · ARM64"]
                LOGS["Amazon CloudWatch Logs<br/>Runtime + Lambda logs<br/>7-day retention"]
            end
            subgraph IAM["AWS IAM · account-wide"]
                RR["Runtime execution role<br/>Memory · model · Gateway<br/>Image pull · logging"]
                GR["Gateway execution role<br/>Invoke tool Lambda"]
                LR["Lambda execution role<br/>Read runtime status<br/>Write logs"]
            end
        end
        MODEL["AWS-managed inference<br/>Amazon Nova Lite<br/>EU destination Regions"]
    end

    CLI <-->|"HTTPS · IAM-signed invocation"| RUNTIME
    RUNTIME <-->|"Read history / save final turn"| MEMORY
    RUNTIME <-->|"Converse · history + tools"| PROFILE
    PROFILE <-->|"Cross-Region inference"| MODEL
    RUNTIME <-->|"IAM-signed MCP · discovery / call"| GATEWAY
    GATEWAY <-->|"Invoke with user-provided runtime ID"| TOOL
    TOOL <-->|"GetAgentRuntime · runtime ID"| CONTROL
    RUNTIME -->|"stdout / errors"| LOGS
    TOOL -->|"Invocation logs / errors"| LOGS
    RR -.->|"Assumed by Runtime"| RUNTIME
    GR -.->|"Assumed by Gateway"| GATEWAY
    LR -.->|"Assumed by Lambda"| TOOL

    classDef local fill:#EFF6FF,stroke:#2563EB,color:#172554
    classDef agentcore fill:#F3E8FF,stroke:#7C3AED,color:#3B0764
    classDef memory fill:#ECFDF5,stroke:#059669,color:#064E3B
    classDef compute fill:#FFF7ED,stroke:#EA580C,color:#7C2D12
    classDef inference fill:#FDF2F8,stroke:#DB2777,color:#831843
    classDef identity fill:#FAF5FF,stroke:#9333EA,color:#581C87
    classDef logs fill:#F1F5F9,stroke:#64748B,color:#0F172A
    class CLI local
    class RUNTIME,GATEWAY,CONTROL agentcore
    class MEMORY memory
    class TOOL compute
    class PROFILE,MODEL inference
    class RR,GR,LR identity
    class LOGS logs
    style LOCAL fill:#F8FAFC,stroke:#94A3B8,color:#0F172A
    style CLOUD fill:#FFFFFF,stroke:#475569,color:#0F172A
    style ACCOUNT fill:#F8FAFC,stroke:#475569,color:#0F172A
    style REGION fill:#FFFFFF,stroke:#0284C7,color:#0F172A
    style AC fill:#FAF5FF,stroke:#A78BFA,color:#3B0764
    style IAM fill:#FAF5FF,stroke:#C084FC,color:#581C87
    linkStyle 0,1,2,3 stroke:#2563EB,stroke-width:2px
    linkStyle 4,5,6 stroke:#0D9488,stroke-width:2px
    linkStyle 7,8 stroke:#64748B,stroke-width:1.5px
    linkStyle 9,10,11 stroke:#9333EA,stroke-width:1.5px
```

The agent retrieves the conversation, discovers Gateway tools, and calls the
model. If the model requests runtime status, the agent calls the tool and gives
its result back to the model. Only the original user message and completed final
reply are saved in Memory.

The status tool reads deployment readiness for a runtime ID supplied by the
user. `READY` does not establish that chat, model access, or memory are healthy.
The model runs on AWS-managed Bedrock infrastructure, outside the agent container.

## Where to go next

| Directory | What it owns | Documentation |
| --- | --- | --- |
| `infra/` | CDK stack, resources, permissions, and deployment | [Setup, deploy, and cleanup](infra/README.md) |
| `chat/` | Terminal CLI, agent, memory client, and Gateway client | [Configure, run, and verify chat](chat/README.md) |
| `tools/` | Shared tools independent of the chat package | [Tool overview](tools/README.md) |
| `tools/runtime_status/` | Runtime-status Lambda and Gateway schema | [Tool contract and packaging](tools/runtime_status/README.md) |

Start with `infra/` to deploy the application, then use `chat/` to talk to it.
[AGENTS.md](AGENTS.md) contains the repository's implementation guidance for agents.

## Conversation and data

Follow-ups reuse a session ID. Saved events survive compute shutdown, and a
conversation can be resumed by ID. New conversations select separate history.
The CDK stack uses three-day event retention; destroying it deletes Memory and
its conversation events.

This is a single-user prototype. It does not provide authorization between
users, history trimming, or transcript export. Keep conversations short and use
synthetic data: messages persist in AWS, CloudWatch can contain request text,
and AWS calls incur charges.
