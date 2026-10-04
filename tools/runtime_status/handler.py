"""Shared Lambda tool for reading one AgentCore runtime's deployment status."""

import os

import boto3


def lambda_handler(event, context):
    """Read the requested runtime and return a small, JSON-serializable result."""
    runtime_id = event["runtime_id"]
    client = boto3.client("bedrock-agentcore-control", region_name=os.environ["AWS_REGION"])
    runtime = client.get_agent_runtime(agentRuntimeId=runtime_id)
    return {
        "runtime_id": runtime["agentRuntimeId"],
        "name": runtime["agentRuntimeName"],
        "status": runtime["status"],
        "version": runtime["agentRuntimeVersion"],
    }
