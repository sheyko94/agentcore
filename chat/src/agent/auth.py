"""AWS request signing, separate from the Gateway's MCP tool protocol."""

import httpx2
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


class GatewayAuth(httpx2.Auth):
    """Attach an AWS SigV4 signature to every outgoing Gateway request."""

    requires_request_body = True

    def __init__(self, session, region):
        """Use the Runtime's boto3 session and the Gateway's AWS region."""
        self.session = session
        self.region = region

    def auth_flow(self, request):
        """Refresh credentials and sign the actual URL, headers, and body."""
        # A reused request must not carry an earlier signature or session token.
        for header in ("Authorization", "X-Amz-Date", "X-Amz-Security-Token"):
            request.headers.pop(header, None)
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers=dict(request.headers),
        )
        credentials = self.session.get_credentials().get_frozen_credentials()
        SigV4Auth(credentials, "bedrock-agentcore", self.region).add_auth(aws_request)
        request.headers.update(dict(aws_request.headers))
        yield request
