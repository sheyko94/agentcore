from aws_cdk import RemovalPolicy, aws_logs as logs


def create_tool_logs(stack):
    return logs.LogGroup(
        stack, "ToolLogs", retention=logs.RetentionDays.ONE_WEEK,
        removal_policy=RemovalPolicy.DESTROY,
    )


def configure_runtime_logs(stack, runtime):
    return logs.LogRetention(
        stack, "RuntimeLogs",
        log_group_name=f"/aws/bedrock-agentcore/runtimes/{runtime.attr_agent_runtime_id}-DEFAULT",
        retention=logs.RetentionDays.ONE_WEEK,
        removal_policy=RemovalPolicy.DESTROY,
    )
