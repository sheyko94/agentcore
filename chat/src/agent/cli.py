"""Terminal client: send prompts to AWS and manage the selected session UUID.

The agent itself runs remotely. This module owns only terminal interaction,
request/response handling, and best-effort cleanup of runtime compute.
"""

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
    """Keep the AWS client, runtime target, and currently selected conversation.

    ``invoked`` tracks whether this CLI has attempted a request in the session.
    It lets cleanup skip fresh sessions that have never started remote compute.
    """

    runtime: object
    runtime_arn: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    invoked: bool = False


def create_conversation():
    """Use the local AWS profile and required environment to start a fresh session."""
    session = boto3.Session(profile_name=os.environ["AWS_PROFILE"])
    runtime = session.client("bedrock-agentcore", region_name=os.environ["AWS_REGION"])
    return Conversation(runtime=runtime, runtime_arn=os.environ["AGENTCORE_RUNTIME_ARN"])


def invoke(conversation, prompt):
    """Invoke the hosted agent and return its reply/tool report as a dictionary.

    Mark the session before sending: a failed request may still start compute.
    Always close the response stream, including when JSON parsing fails. Both
    the terminal UI and evaluation runner use this request path.
    """
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
        return json.loads(body.read())
    finally:
        body.close()


def ask(conversation, prompt):
    """Show returned Gateway tool names and give the terminal loop its reply."""
    result = invoke(conversation, prompt)
    for tool in result.get("tools_used", []):
        print(f"Tool: {tool}")
    return result["reply"]


def stop_session(conversation):
    """Attempt to stop compute; log failures without preventing reset/resume/exit.

    Stopping compute does not delete the conversation's saved Memory checkpoints.
    """
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
    """Stop current compute and select a new UUID without deleting saved history."""
    stop_session(conversation)
    conversation.session_id = str(uuid.uuid4())


def resume_conversation(conversation, session_id):
    """Select a saved conversation; invalid UUIDs leave the current one untouched."""
    session_id = str(uuid.UUID(session_id))
    stop_session(conversation)
    conversation.session_id = session_id


def handle_session_command(conversation, prompt):
    """Handle /new, /session, or /resume and return whether input was a command.

    Return True even for an invalid /resume so it is never sent as a chat prompt.
    /exit stays in the input loop because it controls that loop's lifetime.
    """
    if prompt == "/new":
        reset_conversation(conversation)
        print(f"New conversation. Session: {conversation.session_id}")
        return True
    if prompt == "/session":
        print(f"Session: {conversation.session_id}")
        return True
    if prompt == "/resume" or prompt.startswith("/resume "):
        try:
            resume_conversation(conversation, prompt.removeprefix("/resume").strip())
            print(f"Resuming session: {conversation.session_id}")
        except ValueError:
            print("Use /resume followed by a valid UUID session ID.", file=sys.stderr)
        return True
    return False


def run_conversation(conversation):
    """Read input, handle session commands locally, and send ordinary prompts."""
    print("Chat ready. /new starts fresh; /session shows the ID; /resume <ID> restores; /exit quits.")
    print(f"Session: {conversation.session_id}")
    while True:
        prompt = input("You: ").strip()
        if not prompt:
            continue
        if prompt == "/exit":
            return
        if handle_session_command(conversation, prompt):
            continue
        try:
            reply = ask(conversation, prompt)
            print(f"Agent: {reply}\n")
        except Exception as error:
            logger.exception("Chat request failed; session=%s", conversation.session_id)
            print(f"Error: {error} (details in error.log)", file=sys.stderr)


def main():
    """Load local settings, run the terminal loop, and clean up on any exit."""
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
