import threading
from pathlib import Path

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from dotenv import load_dotenv

from .agent import Chat

app = BedrockAgentCoreApp()
conversations = {}
lock = threading.Lock()


@app.entrypoint
def invoke(payload, context):
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if not context.session_id:
        raise ValueError("A runtime session ID is required for conversation memory.")
    # Also isolate sessions when testing multiple sessions in one local server.
    with lock:
        if context.session_id not in conversations:
            conversations[context.session_id] = Chat()
        return {"reply": conversations[context.session_id].ask(prompt)}


def main():
    load_dotenv(Path.cwd() / ".env", override=False)
    app.run(host="0.0.0.0", port=8080)
