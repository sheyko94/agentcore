"""AgentCore Memory, Gateway, and Runtime resources."""

import json

from aws_cdk import RemovalPolicy, aws_bedrockagentcore as core


def create_memory(stack):
    memory = core.CfnMemory(
        stack, "Memory", name="agentcore_chat_cdk_memory",
        event_expiry_duration=3,
    )
    memory.apply_removal_policy(RemovalPolicy.DESTROY)
    return memory


def tool_schema(schema):
    values = dict(schema)
    if "properties" in values:
        values["properties"] = {name: tool_schema(value) for name, value in values["properties"].items()}
    if "items" in values:
        values["items"] = tool_schema(values["items"])
    return core.CfnGatewayTarget.SchemaDefinitionProperty(**values)


def create_gateway(stack, gateway_role, tool, tool_directory):
    gateway = core.CfnGateway(
        stack, "Gateway", name="agentcore-chat-cdk-tools",
        role_arn=gateway_role.role_arn, protocol_type="MCP", authorizer_type="AWS_IAM",
    )
    gateway.node.add_dependency(gateway_role)
    schemas = json.loads((tool_directory / "tool-schema.json").read_text())
    target = core.CfnGatewayTarget(
        stack, "RuntimeStatusTarget", name="runtime-status",
        gateway_identifier=gateway.attr_gateway_identifier,
        credential_provider_configurations=[core.CfnGatewayTarget.CredentialProviderConfigurationProperty(
            credential_provider_type="GATEWAY_IAM_ROLE")],
        target_configuration=core.CfnGatewayTarget.TargetConfigurationProperty(
            mcp=core.CfnGatewayTarget.McpTargetConfigurationProperty(
                lambda_=core.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                    lambda_arn=tool.function_arn,
                    tool_schema=core.CfnGatewayTarget.ToolSchemaProperty(inline_payload=[
                        core.CfnGatewayTarget.ToolDefinitionProperty(
                            name=item["name"], description=item["description"],
                            input_schema=tool_schema(item["inputSchema"]),
                            output_schema=tool_schema(item["outputSchema"]),
                        ) for item in schemas
                    ]),
                ),
            ),
        ),
    )

    return gateway, target


def create_runtime(stack, image_uri, runtime_role, memory, gateway, target):
    runtime = core.CfnRuntime(
        stack, "Runtime", agent_runtime_name="agentcore_chat_cdk",
        agent_runtime_artifact=core.CfnRuntime.AgentRuntimeArtifactProperty(
            container_configuration=core.CfnRuntime.ContainerConfigurationProperty(
                container_uri=image_uri)),
        role_arn=runtime_role.role_arn,
        network_configuration=core.CfnRuntime.NetworkConfigurationProperty(network_mode="PUBLIC"),
        protocol_configuration="HTTP",
        environment_variables={
            "AWS_REGION": stack.region,
            "CHAT_MODEL": stack.node.get_context("model"),
            "CHAT_ACTOR_ID": stack.node.get_context("actor"),
            "AGENTCORE_MEMORY_ID": memory.attr_memory_id,
            "AGENTCORE_GATEWAY_URL": gateway.attr_gateway_url,
        },
    )
    runtime.node.add_dependency(runtime_role, target)
    return runtime
