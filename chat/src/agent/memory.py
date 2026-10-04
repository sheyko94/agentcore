from datetime import datetime, timezone
import os

import boto3


class Memory:
    """Short-term conversation events for this single-user experiment."""

    def __init__(self):
        self.client = boto3.client("bedrock-agentcore", region_name=os.environ["AWS_REGION"])
        self.memory_id = os.environ["AGENTCORE_MEMORY_ID"]
        self.actor_id = os.environ["CHAT_ACTOR_ID"]

    def load(self, session_id):
        events = []
        pages = self.client.get_paginator("list_events").paginate(
            memoryId=self.memory_id,
            actorId=self.actor_id,
            sessionId=session_id,
            includePayloads=True,
        )
        for page in pages:
            events.extend(page["events"])
        events.sort(key=lambda event: (event["eventTimestamp"], event["eventId"]))
        messages = []
        for event in events:
            for item in event["payload"]:
                message = item.get("conversational")
                if message and message["role"] in ("USER", "ASSISTANT"):
                    messages.append({
                        "role": message["role"].lower(),
                        "content": [{"text": message["content"]["text"]}],
                    })
        return messages

    def save_turn(self, session_id, prompt, reply):
        self.client.create_event(
            memoryId=self.memory_id,
            actorId=self.actor_id,
            sessionId=session_id,
            eventTimestamp=datetime.now(timezone.utc),
            extractionMode="SKIP",
            payload=[
                {"conversational": {"role": "USER", "content": {"text": prompt}}},
                {"conversational": {"role": "ASSISTANT", "content": {"text": reply}}},
            ],
        )
