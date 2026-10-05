"""Open one MCP connection and expose Gateway tools with model-friendly names.

LangChain/FastMCP handle the protocol; ``auth.py`` handles AWS authentication.
Use ``async with Gateway()`` so HTTP connections close even if a turn fails.
"""

import os

import anyio
import boto3
import httpx2
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter

from .auth import GatewayAuth


class Gateway:
    """Own the connection and the short-name → full-name tool mapping for a turn."""

    def __init__(self):
        """Configure the MCP adapter without opening the remote connection yet."""
        self.url = os.environ["AGENTCORE_GATEWAY_URL"]
        self.region = os.environ["AWS_REGION"]
        self.session = boto3.Session()
        self.http_clients = []
        self.tool_names = {}
        transport = StreamableHttpTransport(
            self.url,
            auth=GatewayAuth(self.session, self.region),
            httpx_client_factory=self._http_client,
        )
        # Keep the existing initialize-based protocol. Modern discovery is not
        # needed for this Lambda target and may not be enabled on the Gateway.
        client = Client(transport, mode="legacy", timeout=30, init_timeout=30)
        self.adapter = MCPAdapter(client)

    def _http_client(self, **kwargs):
        """Create and track transport clients, keeping signed requests off redirects."""
        # Never forward an IAM-signed request to a redirect destination.
        kwargs["follow_redirects"] = False
        client = httpx2.AsyncClient(**kwargs)
        self.http_clients.append(client)
        return client

    async def __aenter__(self):
        """Initialize MCP, closing any opened clients if initialization fails."""
        try:
            await self.adapter.__aenter__()
            return self
        except BaseException:
            await self._close_http()
            raise

    async def __aexit__(self, *args):
        """End the MCP session and always release the underlying HTTP clients."""
        try:
            await self.adapter.__aexit__(*args)
        finally:
            await self._close_http()

    async def _close_http(self):
        """Finish HTTP cleanup even when the task is being cancelled."""
        # FastMCP owns normal transport cleanup; this also covers failed entry
        # and cancellation before its async context has been fully established.
        with anyio.CancelScope(shield=True):
            for client in self.http_clients:
                await client.aclose()
        self.http_clients.clear()

    async def list_tools(self):
        """Discover tools and shorten schemas while retaining full-name dispatch.

        For example, Nova sees ``get_runtime_status`` instead of
        ``runtime-status___get_runtime_status``. The adapter tool's callable
        still sends its original MCP name. Reject collisions rather than
        silently choosing one of two tools with the same short name.
        """
        tools = await self.adapter.list_tools(cache_mode="bypass")
        names = {}
        aliased_tools = []
        for tool in tools:
            short_name = tool.name.rsplit("___", 1)[-1]
            if short_name in names:
                raise RuntimeError("Gateway tools have duplicate names after removing target prefixes.")
            names[short_name] = tool.name
            aliased_tools.append(tool.model_copy(update={"name": short_name}))
        self.tool_names = names
        return aliased_tools
