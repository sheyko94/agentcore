"""Rules that run around LangChain's model calls and tool execution.

CompletionGuard protects saved model messages. The built-in limiter bounds tool
execution. GatewayTools records the names the CLI displays after a tool returns.
"""

import re

from langchain.agents.middleware import AgentMiddleware, ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, ToolMessage


MAX_TOOL_CALLS = 4


def final_text(message):
    """Extract visible answer text, remove Nova thinking, and reject emptiness.

    An unclosed thinking block is removed through the end of the message too.
    This helper is used both before persistence and when returning the reply.
    """
    text = re.sub(r"<thinking>.*?(?:</thinking>|$)", "", message.text, flags=re.DOTALL).strip()
    if not text:
        raise RuntimeError("The model returned no text response.")
    return text


class CompletionGuard(AgentMiddleware):
    """Reject invalid generations inside the model node, before state is saved."""

    def __init__(self, tool_names):
        """Keep the set of short aliases the model is allowed to request."""
        self.tool_names = set(tool_names)

    def _validate(self, request, response):
        """Check one model response and prepare its content for persistence.

        Raising here fails the model node before its output is checkpointed.
        Earlier graph steps, including the user input, may already be saved.
        """
        message = self._response_message(response)
        if message.response_metadata["stopReason"] == "end_turn":
            content = self._final_reply(message)
        else:
            self._validate_tool_calls(message, request.state["messages"])
            # Bedrock reconstructs tool-use blocks from tool_calls. Retain the
            # calls, but exclude intermediate model text/reasoning from state.
            content = ""
        response.result[0] = message.model_copy(update={"content": content})
        return response

    def _response_message(self, response):
        """Require one assistant message with a valid Bedrock completion reason."""
        if len(response.result) != 1 or not isinstance(response.result[0], AIMessage):
            raise RuntimeError("The model returned an unexpected response.")
        message = response.result[0]
        stop_reason = message.response_metadata.get("stopReason")
        if stop_reason not in ("end_turn", "tool_use"):
            raise RuntimeError(f"The model did not complete its reply: {stop_reason}.")
        if message.invalid_tool_calls:
            raise RuntimeError("The model returned an invalid tool call.")
        return message

    def _final_reply(self, message):
        """Require a visible final answer with no pending tool requests."""
        if message.tool_calls:
            raise RuntimeError("The model ended its turn with pending tool calls.")
        return final_text(message)

    def _validate_tool_calls(self, message, history):
        """Reject unknown tools, invalid arguments, and reused or missing IDs.

        Tool results refer to their request by ID, so IDs must remain unique
        across saved history and the current batch.
        """
        if not message.tool_calls:
            raise RuntimeError("The model requested tool use without a tool call.")
        call_ids = set()
        for prior in history:
            if isinstance(prior, ToolMessage):
                call_ids.add(prior.tool_call_id)
            elif isinstance(prior, AIMessage):
                call_ids.update(call["id"] for call in prior.tool_calls)
        for call in message.tool_calls:
            name = call.get("name")
            if name not in self.tool_names:
                raise RuntimeError(f"The model requested an unknown tool: {name}")
            if not isinstance(call.get("args"), dict):
                raise RuntimeError("The model returned invalid tool arguments.")
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id or call_id in call_ids:
                raise RuntimeError("The model returned a missing or duplicate tool-call ID.")
            call_ids.add(call_id)

    async def awrap_model_call(self, request, handler):
        """Validate the async model response before its output is checkpointed."""
        return self._validate(request, await handler(request))


class GatewayTools(AgentMiddleware):
    """Record executed Gateway tools without intercepting adapter errors."""

    def __init__(self, tool_names, tools_used):
        """Share the full-name mapping and this request's tool-report list."""
        self.tool_names = tool_names
        self.tools_used = tools_used

    async def awrap_tool_call(self, request, handler):
        """Record async tool results, including results with error status.

        A tool-level error is still a returned result the model can explain.
        Transport/protocol exceptions propagate instead of becoming a reply.
        """
        result = await handler(request)
        self.tools_used.append(self.tool_names[request.tool_call["name"]])
        return result


def build_middleware(tool_names, tools_used):
    """Build the ordered rules for response validation, limits, and reporting.

    run_limit counts one user turn, resetting for the next invocation even when
    the conversation shares a checkpoint thread. exit_behavior="error" rejects
    an excessive batch before executing any tool in that batch.
    """
    return [
        CompletionGuard(tool_names),
        ToolCallLimitMiddleware(run_limit=MAX_TOOL_CALLS, exit_behavior="error"),
        GatewayTools(tool_names, tools_used),
    ]
