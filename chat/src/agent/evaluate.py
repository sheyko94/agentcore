"""Run local LangSmith scores over deployed chat conversations.

Read eval_cases for prompts and expectations, then invoke_chat for execution.
AWS executes the chat; datasets, traces, and results stay on this machine.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client
from langsmith.evaluation import evaluate

from .cli import create_conversation, invoke, reset_conversation, resume_conversation, stop_session
from .eval_cases import examples


logger = logging.getLogger(__name__)


def invoke_chat(inputs):
    """Run prompts, optionally change session before the last, and clean up.

    Each example starts with a fresh UUID. Resume requires a successful stop
    request, so a failed stop cannot pass that scenario. Stopping compute keeps
    Memory; an accepted stop request does not prove that the process has exited.
    """
    conversation = create_conversation()
    turns = []
    try:
        for index, prompt in enumerate(inputs["prompts"]):
            if index == len(inputs["prompts"]) - 1:
                action = inputs.get("session_action")
                if action == "new":
                    reset_conversation(conversation)
                elif action == "resume":
                    # Unlike final best-effort cleanup, this stop must succeed.
                    conversation.runtime.stop_runtime_session(
                        agentRuntimeArn=conversation.runtime_arn,
                        runtimeSessionId=conversation.session_id,
                        qualifier="DEFAULT",
                    )
                    conversation.invoked = False
                    resume_conversation(conversation, conversation.session_id)
            turns.append(invoke(conversation, prompt))
        return {"turns": turns}
    except Exception:
        logger.exception("Evaluation request failed; session=%s", conversation.session_id)
        raise
    finally:
        stop_session(conversation)


def has_replies(outputs, reference_outputs):
    """Require the expected number of turns, each with non-empty reply text."""
    turns = (outputs or {}).get("turns", [])
    return len(turns) == len(reference_outputs["tools"]) and all(
        isinstance(turn, dict) and isinstance(turn.get("reply"), str)
        and bool(turn["reply"].strip()) for turn in turns
    )


def expected_tools(outputs, reference_outputs):
    """Compare each tool sequence, ignoring only the Gateway prefix.

    Missing reports fail. Reports show completed tool-handler calls, not their
    arguments, results, or deployment health.
    """
    turns = (outputs or {}).get("turns", [])
    if len(turns) != len(reference_outputs["tools"]):
        return False
    for turn, expected in zip(turns, reference_outputs["tools"]):
        tools = turn.get("tools_used") if isinstance(turn, dict) else None
        if not isinstance(tools, list) or not all(isinstance(tool, str) for tool in tools):
            return False
        if [tool.rsplit("___", 1)[-1] for tool in tools] != expected:
            return False
    return True


def expected_text(outputs, reference_outputs):
    """Check required/forbidden fragments; this is not a semantic judge.

    Validate replies first so missing output cannot pass vacuously. Cases
    without text expectations still require valid replies.
    """
    if not has_replies(outputs, reference_outputs):
        return False
    replies = [turn["reply"].casefold() for turn in outputs["turns"]]
    for index, fragments in reference_outputs.get("contains", {}).items():
        if not all(fragment.casefold() in replies[index] for fragment in fragments):
            return False
    for index, fragments in reference_outputs.get("excludes", {}).items():
        if any(fragment.casefold() in replies[index] for fragment in fragments):
            return False
    return True


EVALUATORS = [has_replies, expected_tools, expected_text]


def run_evaluation():
    """Run cases sequentially without LangSmith uploads or a judge model."""
    runtime_id = os.environ["AGENTCORE_RUNTIME_ARN"].rsplit("/", 1)[-1]
    client = Client(auto_batch_tracing=False)
    try:
        return list(evaluate(
            invoke_chat,
            data=examples(runtime_id),
            evaluators=EVALUATORS,
            max_concurrency=0,
            upload_results=False,
            client=client,
        ))
    finally:
        client.close()


def print_scores(scores, outputs, reference_outputs):
    """Show each score's expected values and the corresponding returned values.

    Display turns starting at 1 for the reader; case definitions use indexes
    starting at 0. Missing tool reports remain None, distinct from no calls.
    """
    turns = (outputs or {}).get("turns", [])
    expected_count = len(reference_outputs["tools"])
    reply_count = sum(
        isinstance(turn, dict) and isinstance(turn.get("reply"), str)
        and bool(turn["reply"].strip()) for turn in turns
    )
    for evaluator in EVALUATORS:
        name = evaluator.__name__
        print(f"  {name}: {'PASS' if scores.get(name) is True else 'FAIL'}")
        if name == "has_replies":
            print(f"    Expected: {expected_count} turns, each with a non-empty reply")
            print(f"    Actual: {len(turns)} returned turns, {reply_count} non-empty replies")
        elif name == "expected_tools":
            for index, tools in enumerate(reference_outputs["tools"]):
                turn = turns[index] if index < len(turns) else None
                actual = turn.get("tools_used") if isinstance(turn, dict) else None
                print(f"    Turn {index + 1}: expected {tools!r}; actual {actual!r}")
        elif name == "expected_text":
            contains = reference_outputs.get("contains", {})
            excludes = reference_outputs.get("excludes", {})
            indexes = sorted(set(contains) | set(excludes))
            if not indexes:
                print("    Expected: valid replies; no required or forbidden text fragments")
            for index in indexes:
                turn = turns[index] if index < len(turns) else None
                actual = turn.get("reply") if isinstance(turn, dict) else None
                print(f"    Turn {index + 1}: must contain {contains.get(index, [])!r}")
                print(f"    Turn {index + 1}: must exclude {excludes.get(index, [])!r}")
                print(f"    Turn {index + 1}: actual reply {actual!r}")


def main():
    """Report all cases; exit 1 if any request or score fails, otherwise 0."""
    logging.basicConfig(
        filename="error.log",
        encoding="utf-8",
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    load_dotenv(Path.cwd() / ".env", override=False)
    rows = run_evaluation()
    passed_count = 0
    for row in rows:
        run = row["run"]
        scores = {result.key: result.score for result in row["evaluation_results"]["results"]}
        passed = not run.error and all(scores.get(evaluator.__name__) is True for evaluator in EVALUATORS)
        passed_count += bool(passed)
        print(f"{'PASS' if passed else 'FAIL'} {run.inputs['case']}")
        print_scores(scores, run.outputs, row["example"].outputs)
        if run.error:
            print(f"  Error: {run.error.splitlines()[0]} (details in error.log)")
        elif run.outputs and run.outputs.get("turns"):
            last = run.outputs["turns"][-1]
            if isinstance(last, dict):
                print(f"  Last reply: {last.get('reply')}")
    print(f"{passed_count}/{len(rows)} cases passed")
    return 0 if rows and passed_count == len(rows) else 1
