from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import sys
import uuid

import boto3
from dotenv import load_dotenv


logger = logging.getLogger(__name__)


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
        result = json.loads(body.read())
        for tool in result.get("tools_used", []):
            print(f"Tool: {tool}")
        return result["reply"]
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
        logger.exception("Session cleanup failed; session=%s", conversation.session_id)
        print(f"Could not stop the runtime session: {error} (details in error.log)", file=sys.stderr)
    finally:
        conversation.invoked = False


def reset_conversation(conversation):
    stop_session(conversation)
    conversation.session_id = str(uuid.uuid4())


def resume_conversation(conversation, session_id):
    # Validate before stopping the current conversation.
    session_id = str(uuid.UUID(session_id))
    stop_session(conversation)
    conversation.session_id = session_id


def run_conversation(conversation):
    print("Chat ready. /new starts fresh; /session shows the ID; /resume <ID> restores; /exit quits.")
    print(f"Session: {conversation.session_id}")
    while True:
        prompt = input("You: ").strip()
        if not prompt:
            continue
        if prompt == "/exit":
            return
        if prompt == "/new":
            reset_conversation(conversation)
            print(f"New conversation. Session: {conversation.session_id}")
            continue
        if prompt == "/session":
            print(f"Session: {conversation.session_id}")
            continue
        if prompt == "/resume" or prompt.startswith("/resume "):
            try:
                resume_conversation(conversation, prompt.removeprefix("/resume").strip())
                print(f"Resuming session: {conversation.session_id}")
            except ValueError:
                print("Use /resume followed by a valid UUID session ID.", file=sys.stderr)
            continue
        try:
            reply = ask(conversation, prompt)
            print(f"Agent: {reply}\n")
        except Exception as error:
            logger.exception("Chat request failed; session=%s", conversation.session_id)
            print(f"Error: {error} (details in error.log)", file=sys.stderr)


def main():
    logging.basicConfig(
        filename="error.log",
        encoding="utf-8",
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    load_dotenv(Path.cwd() / ".env", override=False)
    conversation = create_conversation()
    try:
        run_conversation(conversation)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        stop_session(conversation)
