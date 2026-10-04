"""Small IAM-authenticated MCP client for AgentCore Gateway."""

import json
import os

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session


class Gateway:
    def __init__(self):
        self.url = os.environ["AGENTCORE_GATEWAY_URL"]
        self.region = os.environ["AWS_REGION"]
        self.session = boto3.Session()
        self.http = URLLib3Session(timeout=30)
        self.request_id = 0
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }

    def __enter__(self):
        try:
            result = self.request("initialize", {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "agentcore-chat", "version": "0.1.0"},
            })
            self.headers["MCP-Protocol-Version"] = result["protocolVersion"]
            self.request("notifications/initialized", notification=True)
            return self
        except Exception:
            self.http.close()
            raise

    def __exit__(self, *args):
        self.http.close()

    def request(self, method, params=None, notification=False):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notification:
            self.request_id += 1
            message["id"] = self.request_id
        request = AWSRequest(method="POST", url=self.url,
                             data=json.dumps(message).encode(), headers=dict(self.headers))
        credentials = self.session.get_credentials().get_frozen_credentials()
        SigV4Auth(credentials, "bedrock-agentcore", self.region).add_auth(request)
        response = self.http.send(request.prepare())
        body = response.content.decode()
        if response.status_code >= 400:
            raise RuntimeError(f"Gateway HTTP {response.status_code}: {body}")
        if response.headers.get("Mcp-Session-Id"):
            self.headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
        if notification:
            return None
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            replies = [json.loads(line[5:].strip()) for line in body.splitlines()
                       if line.startswith("data:") and line[5:].strip()]
            reply = next(item for item in replies if item.get("id") == message["id"])
        else:
            reply = json.loads(body)
        if reply.get("id") != message["id"]:
            raise RuntimeError("Gateway returned an unexpected MCP response ID.")
        if "error" in reply:
            raise RuntimeError(f"Gateway MCP error: {json.dumps(reply['error'])}")
        return reply["result"]

    def list_tools(self):
        tools = []
        params = {}
        while True:
            page = self.request("tools/list", params)
            tools.extend(page["tools"])
            if not page.get("nextCursor"):
                return tools
            params = {"cursor": page["nextCursor"]}

    def call_tool(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})
