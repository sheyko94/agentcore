# What happens during a chat

The CLI handles input and display. AgentCore runs the Python agent. The agent's
memory holds the current conversation, which is sent to the inference model,
Bedrock Nova Lite, with each new message.

```mermaid
sequenceDiagram
    actor You
    box rgb(235, 245, 255) Local machine
        participant CLI as Chat CLI on your Mac
    end
    box rgb(255, 245, 225) AWS Cloud
        participant Runtime as AgentCore Runtime
        participant Memory as Agent memory
        participant Model as Inference model (Bedrock Nova Lite)
    end

    You->>CLI: Type a message
    CLI->>Runtime: Message + session ID
    Runtime->>Memory: Read this session's history
    Memory-->>Runtime: Previous messages
    Runtime->>Model: History + your new message
    Model-->>Runtime: Generate a reply
    Runtime->>Memory: Store your message and the reply
    Runtime-->>CLI: Return the reply
    CLI-->>You: Display the reply

    Note over CLI,Memory: Follow-ups reuse the same session ID and history

    You->>CLI: /new or /exit
    CLI->>Runtime: Stop the session
    Note over Runtime,Memory: Stopping the session discards its memory
```

The first message starts a session with empty history. Follow-up messages reuse
the same session ID. `/new` stops the previous session and creates a fresh ID;
`/exit` stops the session and quits. Cleanup is attempted only after an invocation
and is best-effort: if stopping fails, the runtime may remain until it expires.

Agent memory is held in RAM and lasts only for the current session: a runtime
restart or session expiration loses it. Nothing is saved to a database, and the
separate AgentCore Memory service is not used.
