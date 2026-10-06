"""Local conversation examples: synthetic facts, session behavior, and real tools."""

import uuid

from langsmith.schemas import Example


def examples(runtime_id):
    """Build eight examples with per-turn tool and text expectations.

    Prompts share a session unless session_action changes it before the last
    prompt. contains/excludes map turn indexes to case-insensitive fragments.
    The tool target comes from the configured Runtime ARN, not a sample ID.
    """
    status_prompt = (
        f"Use get_runtime_status to check deployment status for runtime {runtime_id}. "
        "Include its exact ID in your reply."
    )

    # Each pair contains the conversation inputs, then its expected results.
    cases = [
        # Greeting: one reply, no tools.
        (
            {
                "case": "basic_greeting",
                "prompts": [
                    "Hello. Please greet me briefly.",
                ],
            },
            {
                "tools": [[]],
            },
        ),

        # Recall: the second turn should remember the first turn's code.
        (
            {
                "case": "remembers_fact",
                "prompts": [
                    "Remember this synthetic project code: BLUE_KITE_42. "
                    "Acknowledge briefly.",
                    "What project code did I give you? Reply with just the code.",
                ],
            },
            {
                "tools": [[], []],
                "contains": {
                    1: ["BLUE_KITE_42"],
                },
            },
        ),

        # Correction: recall the replacement code without repeating the old one.
        (
            {
                "case": "corrects_fact",
                "prompts": [
                    "Remember this synthetic project code: OLD_LANTERN_17. "
                    "Acknowledge briefly.",
                    "Correction: replace that project code with NEW_LANTERN_29. "
                    "Acknowledge briefly.",
                    "What is my current project code? Reply with just the current code.",
                ],
            },
            {
                "tools": [[], [], []],
                "contains": {
                    2: ["NEW_LANTERN_29"],
                },
                "excludes": {
                    2: ["OLD_LANTERN_17"],
                },
            },
        ),

        # Isolation: start a new session before asking for the code.
        (
            {
                "case": "isolates_sessions",
                "session_action": "new",
                "prompts": [
                    "Remember this synthetic project code: PRIVATE_COMET_83. "
                    "Acknowledge briefly.",
                    "What project code did I give you? If none was provided here, "
                    "say you don't know. Don't guess.",
                ],
            },
            {
                "tools": [[], []],
                "excludes": {
                    1: ["PRIVATE_COMET_83"],
                },
            },
        ),

        # Resume: stop compute, select the saved session, then recall its code.
        (
            {
                "case": "resumes_saved_fact",
                "session_action": "resume",
                "prompts": [
                    "Remember this synthetic project code: SAVED_ORBIT_61. "
                    "Acknowledge briefly.",
                    "What project code did I give you? Reply with just the code.",
                ],
            },
            {
                "tools": [[], []],
                "contains": {
                    1: ["SAVED_ORBIT_61"],
                },
            },
        ),

        # Missing ID: mention the runtime ID without calling the tool.
        (
            {
                "case": "missing_runtime_id",
                "prompts": [
                    "What is my runtime's current deployment status? "
                    "I have not provided its runtime ID.",
                ],
            },
            {
                "tools": [[]],
                "contains": {
                    0: ["runtime id"],
                },
            },
        ),

        # Status: call the tool once and include the supplied runtime ID.
        (
            {
                "case": "runtime_status",
                "prompts": [
                    status_prompt,
                ],
            },
            {
                "tools": [["get_runtime_status"]],
                "contains": {
                    0: [runtime_id],
                },
            },
        ),

        # Follow-up: reuse the remembered runtime ID, but fetch a fresh status.
        (
            {
                "case": "runtime_status_followup",
                "prompts": [
                    status_prompt,
                    "Check that same runtime again with get_runtime_status "
                    "for a fresh status. Include its exact ID in your reply.",
                ],
            },
            {
                "tools": [
                    ["get_runtime_status"],
                    ["get_runtime_status"],
                ],
                "contains": {
                    0: [runtime_id],
                    1: [runtime_id],
                },
            },
        ),
    ]

    return [
        Example(id=uuid.uuid4(), inputs=inputs, outputs=expected)
        for inputs, expected in cases
    ]
