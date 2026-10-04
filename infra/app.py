import aws_cdk as cdk

from stack import ChatStack

app = cdk.App()
ChatStack(
    app,
    "AgentCoreChatDev",
    env=cdk.Environment(
        account=app.node.get_context("account"),
        region=app.node.get_context("region"),
    ),
)
app.synth()
