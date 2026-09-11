"""Meerada Guard — the watchdog and the cage for AI models at work.

Sits on every model call in the user's workspace and answers two questions a
program can answer, live:

* **Is this task still moving, or is the model burning money in place?**
  (``signals`` — stall / burn detection with a "working hard vs. stuck" verdict)
* **Is the model trying to move anything out of the workspace it shouldn't?**
  (``cage`` — secrets, paths outside the workspace, outbound network, env dumps)

Three ways it sits on the traffic (``docs/GUARD.md``):

1. inside LLManager — every call passes through :class:`meter.GuardedCaller`;
2. beside Claude Code — :class:`claude_watch.ClaudeCodeWatcher` tails the live
   session logs under ``~/.claude/projects`` and alerts from the tray;
3. company-wide — one machine policy file (``policy.machine_policy_path``)
   locks budgets, cage rules and a webhook for every user on the machine.
"""

from handover.guard.policy import Policy, load_policy
from handover.guard.signals import Event, StallDetector, Verdict

__all__ = ["Event", "Policy", "StallDetector", "Verdict", "load_policy"]
