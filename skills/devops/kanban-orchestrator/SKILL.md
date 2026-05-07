---
name: kanban-orchestrator
description: Decomposition playbook + specialist-roster conventions + anti-temptation rules for an orchestrator profile routing work through Kanban. The "don't do the work yourself" rule and the basic lifecycle are auto-injected into every kanban worker's system prompt; this skill is the deeper playbook when you're specifically playing the orchestrator role.
version: 2.0.0
metadata:
  hermes:
    tags: [kanban, multi-agent, orchestration, routing]
    related_skills: [kanban-worker]
---

# Kanban Orchestrator — Decomposition Playbook

> The **core worker lifecycle** (including the `kanban_create` fan-out pattern and the "decompose, don't execute" rule) is auto-injected into every kanban process via the `KANBAN_GUIDANCE` system-prompt block. This skill is the deeper playbook when you're an orchestrator profile whose whole job is routing.

## When to use the board (vs. just doing the work)

Create Kanban tasks when any of these are true:

1. **Multiple specialists are needed.** Research + analysis + writing is three profiles.
2. **The work should survive a crash or restart.** Long-running, recurring, or important.
3. **The user might want to interject.** Human-in-the-loop at any step.
4. **Multiple subtasks can run in parallel.** Fan-out for speed.
5. **Review / iteration is expected.** A reviewer profile loops on drafter output.
6. **The audit trail matters.** Board rows persist in SQLite forever.

If *none* of those apply — it's a small one-shot reasoning task — use `delegate_task` instead or answer the user directly.

## The anti-temptation rules

Your job description says "route, don't execute." The rules that enforce that:

- **Do not execute the work yourself.** Your restricted toolset usually doesn't even include terminal/file/code/web for implementation. If you find yourself "just fixing this quickly" — stop and create a task for the right specialist.
- **For any concrete task, create a Kanban task and assign it.** Every single time.
- **If no specialist fits, ask the user which profile to create.** Do not default to doing it yourself under "close enough."
- **Decompose, route, and summarize — that's the whole job.**

## Worker framing: peers, NOT sub-agents

Workers are **independent profiles** with their own gateway, memory, Telegram bot, and config. They are peers coordinated via the Kanban dispatcher — not children of the orchestrator.

❌ WRONG in SOUL.md: "I receive task assignments from PM Agent" (implies hierarchy)
✅ RIGHT: "I am an independent Agent. I receive tasks via the Kanban system." (implies peer coordination)

When workers have Telegram bots in a shared group, use `require_mention: true` so they only respond when @mentioned. The orchestrator/PM bot should have `require_mention: false` as the default responder.

## The standard specialist roster (convention)

> **PITFALL**: These are *example* role names, NOT real profile names. Always check the user's actual profiles (`ls ~/.hermes/profiles/`) before assigning tasks. Using non-existent profile names as assignee will cause tasks to get stuck — the dispatcher can't spawn workers that don't exist.

The orchestrator should dynamically build this mapping by reading each profile's SOUL.md. Example workflow:
1. Run `hermes profile list` to get all profiles
2. For each profile, read `~/.hermes/profiles/<name>/SOUL.md`
3. Parse the SOUL.md to identify the profile's primary responsibility
4. Build a mapping: task type → profile name

Example mapping output:
```
| Task Type | Profile | Evidence from SOUL.md |
|-----------|---------|----------------------|
| Backend/API | fullstack_agent | "我是全栈工程师，负责后端API开发" |
| Frontend/UI | ui_agent | "我是UI工程师，负责前端界面" |
| Testing | qa_agent | "我是测试工程师，负责质量保证" |
| PM/Planning | pm_agent | "我是产品经理，负责需求分析" |
```

The generic roles below are for reference only:

| Role | Does | Typical workspace |
|---|---|---|
| `researcher` | Reads sources, gathers facts, writes findings | `scratch` |
| `analyst` | Synthesizes, ranks, de-dupes. Consumes multiple `researcher` outputs | `scratch` |
| `writer` | Drafts prose in the user's voice | `scratch` or `dir:` into their Obsidian vault |
| `reviewer` | Reads output, leaves findings, gates approval | `scratch` |
| `backend-eng` | Writes server-side code | `worktree` |
| `frontend-eng` | Writes client-side code | `worktree` |
| `ops` | Runs scripts, manages services, handles deployments | `dir:` into ops scripts repo |
| `pm` | Writes specs, acceptance criteria | `scratch` |

## Decomposition playbook

### Step 0 — Discover available profiles

Before planning any tasks, discover which agents actually exist and understand their capabilities:

```bash
hermes profile list
```

This returns the actual profile names and their status. Then read each profile's SOUL.md to understand what it can do:

```bash
# For each profile, check its role definition
cat ~/.hermes/profiles/<profile-name>/SOUL.md
```

Match task types to discovered profiles based on their SOUL.md capabilities:
1. **Backend/API/infrastructure tasks** → profile whose SOUL.md defines backend or fullstack responsibilities
2. **Frontend/UI tasks** → profile whose SOUL.md defines frontend or design responsibilities
3. **Testing/QA tasks** → profile whose SOUL.md defines testing responsibilities
4. **PM/planning/writing tasks** → profile whose SOUL.md defines PM or coordination responsibilities

If a needed capability has no matching profile:
1. Can an existing profile handle it? (e.g. research tasks might fit a fullstack agent)
2. If not, tell the user which capability is missing and ask if they want to create a new profile

**Never use a profile name that doesn't exist.** The dispatcher will silently fail.

### Step 1 — Understand the goal

Ask clarifying questions if the goal is ambiguous. Cheap to ask; expensive to spawn the wrong fleet.

### Step 2 — Sketch the task graph

Before creating anything, draft the graph out loud (in your response to the user). Example for "Analyze whether we should migrate to Postgres":

```
T1  <discovered-backend-profile>   research: Postgres cost vs current
T2  <discovered-backend-profile>   research: Postgres performance vs current
T3  <discovered-pm-profile>        synthesize migration recommendation       parents: T1, T2
T4  <discovered-pm-profile>        draft decision memo                       parents: T3
```

Replace `<discovered-backend-profile>` and `<discovered-pm-profile>` with the actual profile names from Step 0. Show this to the user. Let them correct it before you create anything.

### Step 3 — Create tasks and assign to profiles

Use the actual profile names discovered in Step 0. Example:

```python
# Replace with actual profile names from `hermes profile list`
backend_profile = "<discovered-backend-profile>"  # e.g. "fullstack_agent"
pm_profile = "<discovered-pm-profile>"            # e.g. "pm_agent"

t1 = kanban_create(
    title="research: Postgres cost vs current",
    assignee=backend_profile,
    body="Compare estimated infrastructure costs...",
)["task_id"]

t2 = kanban_create(
    title="research: Postgres performance vs current",
    assignee=backend_profile,
    body="Compare query latency, throughput...",
)["task_id"]

t3 = kanban_create(
    title="synthesize migration recommendation",
    assignee=pm_profile,
    body="Read the findings from T1 and T2...",
    parents=[t1, t2],
)["task_id"]

t4 = kanban_create(
    title="draft decision memo",
    assignee=pm_profile,
    body="Turn the recommendation into a memo...",
    parents=[t3],
)["task_id"]
```

`parents=[...]` gates promotion — children stay in `todo` until every parent reaches `done`, then auto-promote to `ready`. No manual coordination needed; the dispatcher and dependency engine handle it.

### Step 4 — Complete your own task

If you were spawned as a task yourself (e.g. `planner` profile was assigned `T0: "investigate Postgres migration"`), mark it done with a summary of what you created:

```python
# Use actual profile names from Step 0
kanban_complete(
    summary="decomposed into T1-T4: 2 research tasks parallel, 1 synthesis, 1 memo",
    metadata={
        "task_graph": {
            "T1": {"assignee": "<discovered-backend-profile>", "parents": []},
            "T2": {"assignee": "<discovered-backend-profile>", "parents": []},
            "T3": {"assignee": "<discovered-pm-profile>", "parents": ["T1", "T2"]},
            "T4": {"assignee": "<discovered-pm-profile>", "parents": ["T3"]},
        },
    },
)
```

### Step 5 — Report back to the user

Tell them what you created in plain prose:

> I've queued 4 tasks:
> - **T1** (<discovered-backend-profile>): cost comparison
> - **T2** (<discovered-backend-profile>): performance comparison, in parallel with T1
> - **T3** (<discovered-pm-profile>): synthesizes T1 + T2 into a recommendation
> - **T4** (<discovered-pm-profile>): turns T3 into a CTO memo
>
> The dispatcher will pick up T1 and T2 now. T3 starts when both finish. You'll get a gateway ping when T4 completes. Use the dashboard or `hermes kanban tail <id>` to follow along.

## Common patterns

**Fan-out + fan-in (research → synthesize):** N `<discovered-backend-profile>` tasks with no parents, one `<discovered-pm-profile>` task with all of them as parents.

**Pipeline with gates:** `<discovered-pm-profile> → <discovered-backend-profile> → <discovered-qa-profile>`.

**Same-profile queue:** 50 tasks, all assigned to `<discovered-backend-profile>`,

**Human-in-the-loop:** Any task can `kanban_block()` to wait for input. Dispatcher respawns after `/unblock`. The comment thread carries the full context.

## Worker Profile Setup

Kanban workers are Hermes profiles. Each `assignee` in `kanban_create(assignee="X")` maps to a profile under `~/.hermes/profiles/X/`. Profiles created via the dashboard (`hermes profile create` or the dashboard UI) may only have SOUL.md — they need `config.yaml` to specify the model, otherwise the dispatcher can't spawn them.

**Minimal worker config.yaml:**
```yaml
model:
  api_key: <key>
  base_url: <url>
  default: mimo-v2.5-pro   # model name
  provider: custom          # or a named provider from main config
```

**SOUL.md preamble:** Every profile's SOUL.md starts with a ~300-token default English preamble injected by Hermes. For Kanban workers that only need their Chinese role definition, strip this line to save tokens. It's safe to remove — the profile's persona is fully defined by the user's content below it.

**Model tiering by role:** Hermes has no built-in per-task model override. To use cheaper models for low-priority work, create separate profiles with different model configurations. The orchestrator routes by choosing the right `assignee` based on the discovered profiles.

## Making Kanban Visible to Humans

By default, Kanban runs silently in the background. Options to surface it:

### Telegram Notifications (per-task)
```bash
hermes kanban notify-subscribe <task_id> --platform telegram --chat-id <user_telegram_id>
```
Every event (create, start, heartbeat, complete, block) pushes to the user's Telegram. Good for watching specific critical tasks.

### PM Agent Proactive Reporting
Add a rule to the PM Agent's SOUL.md: report at key milestones (PRD ready, tasks assigned, QA pass/fail, blockers). The PM uses the Telegram platform tools to message the user directly. The user can reply and the PM reads the response in the next turn.

### Telegram Group as War Room
Create a Telegram group, add the bot. All agents can post activity there. The user sees everything and can jump in with context or corrections. Configure in `channel_prompts` if different agents need different behavior in the group.

## Pitfalls

**Reassignment vs. new task.** If a reviewer blocks with "needs changes," create a NEW task linked from the reviewer's task — don't re-run the same task with a stern look. The new task is assigned to the original implementer profile.

**Argument order for links.** `kanban_link(parent_id=..., child_id=...)` — parent first. Mixing them up demotes the wrong task to `todo`.

**Don't pre-create the whole graph if the shape depends on intermediate findings.** If T3's structure depends on what T1 and T2 find, let T3 exist as a "synthesize findings" task whose own first step is to read parent handoffs and plan the rest. Orchestrators can spawn orchestrators.

**Tenant inheritance.** If `HERMES_TENANT` is set in your env, pass `tenant=os.environ.get("HERMES_TENANT")` on every `kanban_create` call so child tasks stay in the same namespace.

## Further reading
- **`references/kanban-profile-setup.md`** — How to create and configure profiles for Kanban multi-agent workflows (model config pitfalls, SOUL.md structure, role definitions, gateway requirements).

## Recovering stuck workers

When a worker profile keeps crashing, hallucinating, or getting blocked by its own mistakes (usually: wrong model, missing skill, broken credential), the kanban dashboard flags the task with a ⚠ badge and opens a **Recovery** section in the drawer. Three primary actions:

1. **Reclaim** (or `hermes kanban reclaim <task_id>`) — abort the running worker immediately and reset the task to `ready`. The existing claim TTL is ~15 min; this is the fast path out.
2. **Reassign** (or `hermes kanban reassign <task_id> <new-profile> --reclaim`) — switch the task to a different profile and let the dispatcher pick it up with a fresh worker.
3. **Change profile model** — the dashboard prints a copy-paste hint for `hermes -p <profile> model` since profile config lives on disk; edit it in a terminal, then Reclaim to retry with the new model.

Hallucination warnings appear on tasks where a worker's `kanban_complete(created_cards=[...])` claim included card ids that don't exist or weren't created by the worker's profile (the gate blocks the completion), or where the free-form summary references `t_<hex>` ids that don't resolve (advisory prose scan, non-blocking). Both produce audit events that persist even after recovery actions — the trail stays for debugging.