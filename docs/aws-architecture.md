# AWS architecture

This diagram describes the infrastructure defined by CDK, rather than a verified
live deployment. All application resources are created fresh, including Memory.
The account boundary represents resource ownership and IAM scope, not a VPC.
The Runtime uses public networking with IAM authentication.

## Chat and tool execution

Blue connections carry chat, memory, and inference requests. Teal connections
carry tool requests. Purple dotted connections associate execution roles with
resources. Grey connections carry logs. Requests and their responses share the
same connection, so bidirectional arrows represent both directions.

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
                    MEMORY[("Memory<br/>Conversation events<br/>actor + session · 3-day retention")]
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

The agent loads its conversation before inference. The model can request a tool,
then receives its result before producing the final reply. Only the user's
message and final reply enter Memory. Tool calls remain within that turn.
`READY` from the status tool describes deployment readiness, not chat health.
The model executes on AWS-managed Bedrock infrastructure; it is not deployed
inside our Runtime. The EU inference profile can route to another EU Region.

## Build and deployment

The application stack and the CDK bootstrap stack have different ownership and
cleanup boundaries. Orange dashed connections show deployment operations, not
traffic during a chat. Docker and uv packaging run on the developer's machine.

```mermaid
flowchart LR
    subgraph LOCAL["Local machine · deployment"]
        SOURCE["Repository<br/>chat/ + tools/runtime_status/ + infra/"]
        CDK["CDK CLI + Python definitions<br/>Docker builds ARM64 image<br/>uv packages Lambda"]
        SOURCE --> CDK
    end

    subgraph AWS["AWS account 781356123457 · eu-west-1"]
        subgraph BOOTSTRAP["CDKToolkit · bootstrap stack"]
            ECR["Amazon ECR<br/>Bootstrap staging repository"]
            S3["Amazon S3<br/>Lambda + template assets"]
            ROLES["AWS IAM<br/>Deployment / asset roles"]
        end
        CF["AWS CloudFormation<br/>Create / update application stack"]
        subgraph APP["AgentCoreChatDev · application stack"]
            APP_ECR["Amazon ECR<br/>agentcore-chat-cdk<br/>Explicit repository resource"]
            COPY["Image deployment helper<br/>Copy ARM64 image + source-hash tag"]
            RUNTIME["AgentCore Runtime"]
            LAMBDA["AWS Lambda tool"]
            SERVICES["AgentCore Memory + Gateway / target<br/>IAM execution roles<br/>CloudWatch log configuration"]
        end
    end

    CDK -.->|"Publish container image"| ECR
    CDK -.->|"Upload packaged assets"| S3
    CDK -.->|"Deploy template using bootstrap roles"| CF
    ROLES -.->|"Deployment permissions"| CF
    CF -.->|"Provision and wire resources"| SERVICES
    CF -.->|"Create / update Runtime"| RUNTIME
    CF -.->|"Create / update Lambda"| LAMBDA
    CF -.->|"Create application repository"| APP_ECR
    CF -.->|"Publish image before Runtime"| COPY
    ECR -.->|"Source image"| COPY
    COPY -.->|"Copy image"| APP_ECR
    APP_ECR -->|"Runtime pulls image"| RUNTIME
    S3 -->|"Lambda deployment package"| LAMBDA

    classDef local fill:#EFF6FF,stroke:#2563EB,color:#172554
    classDef assets fill:#ECFDF5,stroke:#059669,color:#064E3B
    classDef deploy fill:#FFF7ED,stroke:#EA580C,color:#7C2D12
    classDef application fill:#F3E8FF,stroke:#7C3AED,color:#3B0764
    classDef iam fill:#FAF5FF,stroke:#9333EA,color:#581C87
    class SOURCE,CDK local
    class ECR,S3,APP_ECR assets
    class CF,COPY deploy
    class RUNTIME,LAMBDA,SERVICES application
    class ROLES iam
    style LOCAL fill:#F8FAFC,stroke:#94A3B8,color:#0F172A
    style AWS fill:#FFFFFF,stroke:#475569,color:#0F172A
    style BOOTSTRAP fill:#F0FDF4,stroke:#059669,color:#064E3B
    style APP fill:#FAF5FF,stroke:#7C3AED,color:#3B0764
    linkStyle 1,2,3,4,5,6,7,8,9,10,11 stroke:#EA580C,stroke-width:1.5px
    linkStyle 12,13 stroke:#059669,stroke-width:2px
```

`cdk destroy` removes the application stack, including its Memory and conversation
events, plus the application ECR repository and images. Bootstrap staging
repositories, uploaded assets, and deployment helpers' own logs remain outside
that cleanup. The old manually created resources are
not part of this CDK deployment. See [deployment and cleanup](../infra/README.md).

For message-by-message ordering, see [the chat sequence diagram](chat-flow.md).
