"""Connect LangGraph checkpoints to the configured AgentCore Memory resource.

The graph saves and restores execution state; this module only supplies its
storage adapter and the actor/conversation identifiers used to find that state.
"""

import os

from langgraph_checkpoint_aws import AgentCoreMemorySaver


class Memory:
    """Persist LangGraph conversation state in AgentCore Memory."""

    def __init__(self):
        """Build the AWS checkpointer using the Runtime's supplied configuration."""
        self.memory_id = os.environ["AGENTCORE_MEMORY_ID"]
        self.actor_id = os.environ["CHAT_ACTOR_ID"]
        self.checkpointer = AgentCoreMemorySaver(
            self.memory_id, region_name=os.environ["AWS_REGION"],
        )

    def config(self, session_id):
        """Scope saved state to this actor and conversation, running tools in order.

        LangGraph calls a conversation a thread. Its ``thread_id`` is the same
        UUID the CLI sends to the Runtime. One concurrent task keeps tool calls
        sequential; it does not serialize requests across Runtime processes.
        """
        return {
            "configurable": {
                "thread_id": session_id,
                "actor_id": self.actor_id,
            },
            "max_concurrency": 1,
        }
