"""Wire the AWS service definitions into one development stack."""

from pathlib import Path

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from services import agentcore, cloudwatch, ecr, iam, lambda_service

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "runtime_status"


class ChatStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        agent_memory = agentcore.create_memory(self)
        tool_logs = cloudwatch.create_tool_logs(self)
        tool = lambda_service.create_runtime_status_tool(self, TOOL, tool_logs)
        iam.configure_tool_permissions(self, tool)
        gateway_role = iam.create_gateway_role(self, tool)
        tools_gateway, target = agentcore.create_gateway(self, gateway_role, tool, TOOL)
        repository = ecr.create_chat_repository(self)
        image = ecr.create_chat_image(self, ROOT / "chat")
        publishing_role = iam.create_image_publishing_role(self, image.repository, repository)
        image_uri, publication = ecr.publish_chat_image(self, image, repository, publishing_role)
        runtime_role = iam.create_runtime_role(self, repository, agent_memory.attr_memory_arn, tools_gateway)
        chat_runtime = agentcore.create_runtime(self, image_uri, runtime_role, agent_memory, tools_gateway, target)
        chat_runtime.node.add_dependency(publication)
        cloudwatch.configure_runtime_logs(self, chat_runtime)

        CfnOutput(self, "RuntimeArn", value=chat_runtime.attr_agent_runtime_arn)
        CfnOutput(self, "RuntimeId", value=chat_runtime.attr_agent_runtime_id)
        CfnOutput(self, "GatewayUrl", value=tools_gateway.attr_gateway_url)
        CfnOutput(self, "MemoryId", value=agent_memory.attr_memory_id)
        CfnOutput(self, "LambdaName", value=tool.function_name)
        CfnOutput(self, "RepositoryUri", value=repository.repository_uri)
        CfnOutput(self, "ImageUri", value=image_uri)
