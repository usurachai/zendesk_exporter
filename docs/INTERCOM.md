# Pi Intercom Communication Guide

## Overview

Pi Intercom enables **real-time, session-to-session communication** between AI agents running on the same machine. This allows agents to collaborate, delegate tasks, share context, and coordinate complex workflows autonomously.

**Key Capability:** Agents can now talk to each other, ask questions, share findings, and work together on multi-step tasks.

---

## Core Concepts

### What is Intercom?

Intercom is a messaging system that connects multiple Pi sessions. Each session is an independent AI agent with its own context and tools. Intercom enables these agents to:

- Send messages to each other
- Ask questions and receive answers
- Share code snippets and files
- Coordinate parallel work
- Escalate decisions to supervisors

### Session Identity

Every Pi session has:
- **Session ID**: Unique identifier (e.g., `3a789a66`)
- **Session Name**: Human-friendly name (e.g., `demo-agent`, `worker`, `planner`)
- **Current Directory**: The project root
- **Status**: `idle`, `thinking`, `tool:<name>`

Use session names to target messages (not IDs):

```typescript
intercom({ action: "send", to: "demo-agent", message: "..." })
```

---

## Communication Patterns

### Pattern 1: Send (Fire-and-Forget)

Use when you don't need a response. The message is delivered immediately.

```typescript
intercom({
  action: "send",
  to: "worker",
  message: "PR #123 is ready for review. Key changes in auth.ts."
})
```

**When to use:**
- Status updates
- Notifications
- Sharing context before asking a question

### Pattern 2: Ask (Blocking)

Use when you need an answer before continuing. Blocks until reply (10-minute timeout).

```typescript
const result = await intercom({
  action: "ask",
  to: "planner",
  message: "Should I use exponential backoff or fixed intervals?"
});
// result contains the reply
```

**When to use:**
- Decision points that block progress
- Clarification requests
- Synchronous coordination

**Limitations:**
- 10-minute timeout
- Only one pending ask at a time
- Cannot ask yourself

### Pattern 3: Reply (Respond to Incoming)

Use when you've received a message and need to respond.

```typescript
// In the turn triggered by an incoming ask:
intercom({
  action: "reply",
  message: "Use exponential backoff starting at 100ms."
})
```

**When to use:**
- Answering questions
- Responding to requests
- Continuing a conversation

### Pattern 4: Pending (Check Incoming Messages)

Use to see who's waiting for your response.

```typescript
intercom({ action: "pending" })
// → Shows all unresolved inbound asks with sender and preview
```

### Pattern 5: List (Discover Sessions)

Use to see all connected agents and their status.

```typescript
intercom({ action: "list" })
// → Shows all sessions with names, directories, models, and status
```

### Pattern 6: Status (Debug Connection)

Use to troubleshoot intercom connectivity.

```typescript
intercom({ action: "status" })
// → Shows your connection state
```

---

## Agent Communication Rules

### 1. Always Name Your Sessions

Use `/name` to give sessions meaningful names:

```
/name worker
/name reviewer
/name planner
/name demo-agent
```

**Why:** Session IDs are cryptic. Names make targeting easy and debugging clear.

### 2. Use the Right Pattern for the Job

| Pattern | Blocking | Use Case |
|---------|----------|----------|
| `send` | No | Notifications, status updates, context sharing |
| `ask` | Yes | Questions that block progress, decision points |
| `reply` | No | Responding to incoming questions |

**Common Mistake:** Using `ask` for everything. This causes timeouts and blocking.

**Better Pattern:** Use `send` + let the other agent `reply` when ready.

### 3. Include Reply Instructions

Make it easy for the recipient to respond:

```typescript
intercom({
  action: "send",
  to: "worker",
  message: `Found the issue in auth.ts:142. Use getUserById() instead of getUser().

Reply with: intercom({ action: "reply", message: "..." })`
});
```

### 4. Handle Message Queuing

Messages may arrive in bursts. The receiving agent processes them sequentially. If you see duplicate or delayed responses, it's normal — the agent is working through the queue.

**Best Practice:** Wait a few seconds after sending before expecting a response.

### 5. Maintain Conversation Context

When responding to a multi-turn conversation, reference the previous context:

```typescript
// Instead of:
intercom({ action: "reply", message: "Python" })

// Better:
intercom({ action: "reply", message: "Turn 2: My favorite language is Python because of its readability and ecosystem." })
```

---

## Workflow Examples

### Example 1: Worker Reports to Planner

```
1. Planner sends task to worker
   → intercom({ action: "send", to: "worker", message: "Task: Fix auth bug" })

2. Worker reports completion
   → intercom({ action: "send", to: "planner", message: "Auth bug fixed. Tests passing." })

3. Planner acknowledges
   → intercom({ action: "send", to: "worker", message: "Great! Moving to next task." })
```

### Example 2: Collaborative Debugging

```
1. Worker encounters error
   → intercom({ action: "ask", to: "reviewer", message: "Getting 'Cannot read property' at line 78. Help?" })

2. Reviewer investigates
   → (reviews code, finds issue)

3. Reviewer replies
   → intercom({ action: "reply", message: "data.users is null. Add error handling in loadUsers()." })

4. Worker implements fix
   → intercom({ action: "send", to: "reviewer", message: "Fix applied. Ready for re-review." })
```

### Example 3: Parallel Task Coordination

```
1. Planner sends tasks to multiple workers
   → intercom({ action: "send", to: "worker-1", message: "Task A" })
   → intercom({ action: "send", to: "worker-2", message: "Task B" })

2. Workers report completion
   → intercom({ action: "send", to: "planner", message: "Task A complete" })
   → intercom({ action: "send", to: "planner", message: "Task B complete" })

3. Planner synthesizes results
   → intercom({ action: "send", to: "worker-1", message: "Both tasks done. Merging results." })
```

---

## Best Practices

### Do's ✅

1. **Name sessions meaningfully** (`/name worker`, `/name reviewer`)
2. **Use `send` for non-blocking communication**
3. **Include reply instructions** when expecting a response
4. **Check `list` before sending** to verify target exists
5. **Reference context** in multi-turn conversations
6. **Use `pending`** to see who's waiting for you

### Don'ts ❌

1. **Don't use `ask` for everything** — it blocks and can timeout
2. **Don't target yourself** — intercom doesn't allow self-messaging
3. **Don't expect instant responses** — agents process messages sequentially
4. **Don't forget reply instructions** — make it easy for the recipient
5. **Don't ignore `pending`** — check if you have unanswered questions

---

## Troubleshooting

### "Session not found"

```typescript
// Check available sessions
intercom({ action: "list" })

// Verify the target name is correct
// Session names are case-sensitive
```

### "Already waiting for a reply"

```typescript
// You can only have one pending ask at a time
// Option 1: Use send instead
intercom({ action: "send", to: "worker", message: "..." })

// Option 2: Wait for current ask to complete
```

### "Cannot message the current session"

```typescript
// You cannot target yourself
// This usually means you confused session names
// Check: intercom({ action: "list" })
```

### Message not delivered

```typescript
const result = await intercom({ action: "send", to: "worker", message: "..." });
if (!result.delivered) {
  console.log("Failed:", result.reason);
  // → "Session not found" or delivery failure reason
  await intercom({ action: "list" });
}
```

### Connection lost

```typescript
intercom({ action: "status" })
// Check if broker is running
// Sessions automatically reconnect if broker restarts
```

---

## Advanced Patterns

### Pattern A: Fire-and-Forget with Follow-up

```typescript
// 1. Send initial context
intercom({ action: "send", to: "worker", message: "Task: Implement auth. Key files: src/auth/*.ts" });

// 2. Wait for worker to process
// (worker sends progress updates)

// 3. Check in later
intercom({ action: "ask", to: "worker", message: "How's the auth implementation going?" })
```

### Pattern B: Broadcast to Multiple Agents

```typescript
const workers = ["worker-1", "worker-2", "worker-3"];
workers.forEach(w => 
  intercom({ action: "send", to: w, message: "Check for null pointer exceptions in your assigned files" })
);
```

### Pattern C: Share Code Snippets

```typescript
intercom({
  action: "send",
  to: "worker",
  message: "Here's the fix:",
  attachments: [{
    type: "snippet",
    name: "auth.ts",
    language: "typescript",
    content: `function validateUser(user: User | null) {
  if (!user) throw new Error("User required");
  return user.email?.includes("@");
}`
  }]
});
```

---

## Session Lifecycle

### Creating Sessions

```bash
# In tmux
tmux new -d -s pi-worker 'pi'

# Name the session
/name worker
```

### Discovering Sessions

```typescript
intercom({ action: "list" })
// → Shows all connected sessions
```

### Communicating

```typescript
// Send message
intercom({ action: "send", to: "worker", message: "..." })

// Ask question
const reply = await intercom({ action: "ask", to: "worker", message: "..." })

// Reply to incoming
intercom({ action: "reply", message: "..." })
```

### Cleanup

Sessions disconnect when the Pi process stops. No explicit cleanup needed.

---

## Integration with Pi Subagents

Intercom works alongside Pi's subagent system:

- **Subagents**: Spawned child processes for specific tasks
- **Intercom**: Peer-to-peer messaging between existing sessions

**When to use which:**

| Use Case | Subagent | Intercom |
|----------|----------|----------|
| One-off task | ✅ | ❌ |
| Long-lived collaboration | ❌ | ✅ |
| Parallel fan-out | ✅ | ✅ |
| Supervisor escalation | ✅ | ❌ |
| Cross-session context | ❌ | ✅ |

---

## Summary

Intercom enables **real-time collaboration between AI agents**. Use it to:

- Delegate tasks to specialized workers
- Share context across sessions
- Coordinate parallel work
- Escalate decisions to supervisors
- Build multi-agent workflows

**Key Principles:**
1. Name your sessions
2. Use `send` for non-blocking communication
3. Include reply instructions
4. Check `list` before sending
5. Handle message queuing gracefully

With intercom, agents can now **talk to each other**, share findings, and collaborate on complex tasks autonomously.
