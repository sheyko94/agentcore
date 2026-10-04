import shutil
import subprocess
from pathlib import Path

import jsii
from aws_cdk import BundlingOptions, DockerImage, Duration, ILocalBundling, aws_lambda as lambda_


@jsii.implements(ILocalBundling)
class LambdaBundle:
    """Package the existing tool with uv, targeting Lambda's Python and CPU."""

    def __init__(self, tool_directory):
        self.tool_directory = tool_directory

    def try_bundle(self, output_dir, options):
        subprocess.run([
            "uv", "pip", "install",
            "--python-version", "3.12",
            "--python-platform", "aarch64-manylinux2014",
            "--only-binary", ":all:",
            "--target", output_dir,
            "--requirements", str(self.tool_directory / "requirements.txt"),
        ], check=True)
        shutil.copy2(self.tool_directory / "handler.py", Path(output_dir) / "handler.py")
        return True


def create_runtime_status_tool(stack, tool_directory, tool_logs):
    tool = lambda_.Function(
        stack, "RuntimeStatus",
        runtime=lambda_.Runtime.PYTHON_3_12,
        architecture=lambda_.Architecture.ARM_64,
        handler="handler.lambda_handler",
        timeout=Duration.seconds(30), memory_size=256,
        log_group=tool_logs,
        code=lambda_.Code.from_asset(
            str(tool_directory), exclude=["runtime-status.zip", "README.md", ".gitignore"],
            bundling=BundlingOptions(
                image=DockerImage.from_registry("ghcr.io/astral-sh/uv:python3.12-bookworm-slim"),
                local=LambdaBundle(tool_directory),
            ),
        ),
    )
    return tool
