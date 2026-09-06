# Claude entry point

Read and follow [AGENTS.md](AGENTS.md), the single shared source of repository-wide agent rules.

The SessionStart hook invokes `scripts/session_context.py --hook`. If its **Session brief** is present, use it without rereading it; otherwise run `python3 scripts/session_context.py`. Detailed change/release rules are in [docs/agent-workflow.md](docs/agent-workflow.md), loaded when relevant.
