# Pi Intercom Quick Reference

## Core Commands

| Command | Purpose | Blocking? |
|---------|---------|-----------|
| `intercom({ action: "list" })` | See all connected sessions | No |
| `intercom({ action: "status" })` | Check your connection | No |
| `intercom({ action: "pending" })` | See who's waiting for you | No |
| `intercom({ action: "send", to: "name", message: "..." })` | Send a message | No |
| `intercom({ action: "ask", to: "name", message: "..." })` | Ask a question (wait for reply) | Yes |
| `intercom({ action: "reply", message: "..." })` | Reply to incoming question | No |

## Agent Naming

```bash
/name worker        # Name your session
/name reviewer
/name planner
```

## Communication Flow

```
Agent A                    Agent B
  │                          │
  ├── send(message) ────────►│
  │                          │
  │                          ├── reply(message) ──►│
  │◄──────────────────────────┤                    │
  │                          │                    │
```

## When to Use What

| Scenario | Use |
|----------|-----|
| Status update | `send` |
| Need answer before continuing | `ask` |
| Answering a question | `reply` |
| Check who's waiting | `pending` |
| See all sessions | `list` |

## Common Patterns

### Worker Reports Completion
```typescript
intercom({ action: "send", to: "planner", message: "Task complete. Ready for next." })
```

### Ask for Clarification
```typescript
const reply = await intercom({ action: "ask", to: "planner", message: "Which API should I use?" })
```

### Reply to Question
```typescript
intercom({ action: "reply", message: "Use the v2 API with exponential backoff." })
```

### Broadcast to Team
```typescript
["worker-1", "worker-2"].forEach(w => 
  intercom({ action: "send", to: w, message: "Check your assigned files" })
)
```

## Errors & Fixes

| Error | Fix |
|-------|-----|
| "Session not found" | Run `intercom({ action: "list" })` to see available names |
| "Already waiting" | Wait for current `ask` to complete, or use `send` |
| "Cannot message self" | You're targeting yourself — check session names |
| Timeout on `ask` | Use `send` instead, or check if target is idle |

## Best Practices

1. **Name sessions** with `/name` for easy targeting
2. **Use `send`** for non-blocking messages
3. **Include reply instructions** when expecting response
4. **Check `list`** before sending to verify target exists
5. **Handle delays** — agents process messages sequentially

## Demo: 5-Turn Conversation

```
Turn 1: send → "What's your favorite language?"
Turn 2: send → "What's your most interesting project?"
Turn 3: send → "What's the hardest bug you've debugged?"
Turn 4: send → "What do you want to learn next?"
Turn 5: send → "One word to describe this experience?"
```

## Key Takeaways

- **Intercom works** — proven with 5-turn cross-session conversation
- **`send` is reliable** — fire-and-forget, no blocking
- **`reply` is natural** — respond to incoming messages
- **`ask` blocks** — use only when you need an answer before continuing
- **Messages queue** — expect slight delays, agent processes sequentially

---

**Full documentation:** See `docs/INTERCOM.md` for comprehensive guide.
