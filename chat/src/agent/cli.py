from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
import uuid

import boto3
from dotenv import load_dotenv


@dataclass
class Conversation:
    runtime: object
    runtime_arn: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    invoked: bool = False


def create_conversation():
    session = boto3.Session(profile_name=os.environ["AWS_PROFILE"])
    runtime = session.client("bedrock-agentcore", region_name=os.environ["AWS_REGION"])
    return Conversation(runtime=runtime, runtime_arn=os.environ["AGENTCORE_RUNTIME_ARN"])


def ask(conversation, prompt):
    conversation.invoked = True
    response = conversation.runtime.invoke_agent_runtime(
        agentRuntimeArn=conversation.runtime_arn,
        runtimeSessionId=conversation.session_id,
        qualifier="DEFAULT",
        contentType="application/json",
        payload=json.dumps({"prompt": prompt}).encode(),
    )
    body = response["response"]
    try:
        return json.loads(body.read())["reply"]
    finally:
        body.close()


def stop_session(conversation):
    if not conversation.invoked:
        return

    try:
        conversation.runtime.stop_runtime_session(
            agentRuntimeArn=conversation.runtime_arn,
            runtimeSessionId=conversation.session_id,
            qualifier="DEFAULT",
        )
    except Exception as error:
        print(f"Could not stop the runtime session: {error}", file=sys.stderr)
    finally:
        conversation.invoked = False


def reset_conversation(conversation):
    stop_session(conversation)
    conversation.session_id = str(uuid.uuid4())


def run_conversation(conversation):
    print("Chat ready. /new starts a fresh conversation; /exit quits.")
    while True:
        prompt = input("You: ").strip()
        if not prompt:
            continue
        if prompt == "/exit":
            return
        if prompt == "/new":
            reset_conversation(conversation)
            print("New conversation.")
            continue
        try:
            reply = ask(conversation, prompt)
            print(f"Agent: {reply}\n")
        except Exception as error:
            print(f"Error: {error}", file=sys.stderr)


def main():
    load_dotenv(Path.cwd() / ".env", override=False)
    conversation = create_conversation()
    try:
        run_conversation(conversation)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        stop_session(conversation)
