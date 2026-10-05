"""HTTP entry point hosted by AgentCore Runtime.

The CLI sends a prompt; AgentCore supplies its session ID. Chat owns the agent
workflow, while this module validates the request and formats the response.
"""

import threading
from pathlib import Path

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from dotenv import load_dotenv

from .agent import Chat

app = BedrockAgentCoreApp()
lock = threading.Lock()


@app.entrypoint
def invoke(payload, context):
    """Run one valid prompt in its AgentCore session and return reply/tool names.

    The lock allows one invocation at a time in this process. Other runtime
    processes are independent, so use one caller per conversation. A fresh Chat
    object loads checkpointed state using the supplied session ID.
    """
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if not context.session_id:
        raise ValueError("A runtime session ID is required for conversation memory.")
    with lock:
        chat = Chat()
        reply = chat.ask(prompt, context.session_id)
        return {"reply": reply, "tools_used": chat.tools_used}


def main():
    """Load optional local settings and serve the AgentCore HTTP contract on 8080."""
    load_dotenv(Path.cwd() / ".env", override=False)
    app.run(host="0.0.0.0", port=8080)
