from aws_cdk import ArnFormat, aws_iam as iam


def configure_tool_permissions(stack, tool):
    tool.add_to_role_policy(iam.PolicyStatement(
        actions=["bedrock-agentcore:GetAgentRuntime"],
        resources=[stack.format_arn(service="bedrock-agentcore", resource="runtime", resource_name="*")],
    ))


def create_gateway_role(stack, tool):
    gateway_role = iam.Role(
        stack, "GatewayRole",
        assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com", conditions={
            "StringEquals": {"aws:SourceAccount": stack.account},
            "ArnLike": {"aws:SourceArn": stack.format_arn(
                service="bedrock-agentcore", resource="gateway", resource_name="*")},
        }),
    )
    tool.grant_invoke(gateway_role)
    return gateway_role


def create_image_publishing_role(stack, source_repository, destination_repository):
    role = iam.Role(
        stack, "ImagePublishingRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
            "service-role/AWSLambdaBasicExecutionRole")],
    )
    source_repository.grant_pull(role)
    destination_repository.grant_pull_push(role)
    role.add_to_policy(iam.PolicyStatement(
        actions=["ecr:GetRepositoryPolicy", "ecr:DescribeRepositories", "ecr:DescribeImages",
                 "ecr:ListImages", "ecr:ListTagsForResource", "ecr:DescribeImageScanFindings"],
        resources=[source_repository.repository_arn, destination_repository.repository_arn],
    ))
    return role


def create_runtime_role(stack, repository, memory_arn, gateway):
    runtime_role = iam.Role(
        stack, "RuntimeRole",
        assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com", conditions={
            "StringEquals": {"aws:SourceAccount": stack.account},
            "ArnLike": {"aws:SourceArn": stack.format_arn(
                service="bedrock-agentcore", resource="runtime", resource_name="*")},
        }),
    )
    repository.grant_pull(runtime_role)
    runtime_role.add_to_policy(iam.PolicyStatement(
        actions=["bedrock-agentcore:ListEvents", "bedrock-agentcore:CreateEvent"],
        resources=[memory_arn],
    ))
    runtime_role.add_to_policy(iam.PolicyStatement(
        actions=["bedrock-agentcore:InvokeGateway"], resources=[gateway.attr_gateway_arn],
    ))
    runtime_role.add_to_policy(iam.PolicyStatement(
        actions=["bedrock:InvokeModel"], resources=[
            stack.format_arn(service="bedrock", resource="inference-profile",
                            resource_name=stack.node.get_context("model")),
            f"arn:{stack.partition}:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
        ],
    ))
    runtime_logs_arn = stack.format_arn(
        service="logs", resource="log-group",
        resource_name="/aws/bedrock-agentcore/runtimes/agentcore_chat_cdk-*",
        arn_format=ArnFormat.COLON_RESOURCE_NAME,
    )
    runtime_role.add_to_policy(iam.PolicyStatement(
        actions=["logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:PutResourcePolicy"],
        resources=[runtime_logs_arn],
    ))
    runtime_role.add_to_policy(iam.PolicyStatement(
        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
        resources=[runtime_logs_arn + ":log-stream:*"],
    ))
    runtime_role.add_to_policy(iam.PolicyStatement(
        actions=["logs:DescribeLogGroups"], resources=[
            f"arn:{stack.partition}:logs:{stack.region}:{stack.account}:log-group:*"],
    ))
    runtime_role.add_to_policy(iam.PolicyStatement(
        actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"],
        resources=["*"],
    ))
    runtime_role.add_to_policy(iam.PolicyStatement(
        actions=["cloudwatch:PutMetricData"], resources=["*"],
        conditions={"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
    ))
    return runtime_role
