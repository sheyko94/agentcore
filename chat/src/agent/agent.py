import os

import boto3


class Chat:
    """One conversation. Commit a turn only after a successful model response."""

    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"])
        self.model = os.environ["CHAT_MODEL"]
        self.messages = []

    def ask(self, prompt):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        messages = self.messages + [{"role": "user", "content": [{"text": prompt.strip()}]}]
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
        self.messages = messages + [reply]
        return text
