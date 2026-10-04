import os

import boto3

from .memory import Memory


class Chat:
    """Generate a reply from stored context, then save the successful turn."""

    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"])
        self.model = os.environ["CHAT_MODEL"]
        self.memory = Memory()

    def ask(self, prompt, session_id):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        prompt = prompt.strip()
        messages = self.memory.load(session_id) + [{"role": "user", "content": [{"text": prompt}]}]
        response = self.client.converse(
            modelId=self.model,
            system=[{"text": "Be helpful and concise. Reply in English. Use the current conversation for context."}],
            messages=messages,
            inferenceConfig={"maxTokens": 512},
        )
        reply = response["output"]["message"]
        text = "\n".join(block["text"] for block in reply["content"] if "text" in block)
        if not text.strip():
            raise RuntimeError("The model returned no text response.")
        self.memory.save_turn(session_id, prompt, text)
        return text
