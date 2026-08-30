"""Copilot — the local translator and multi-model session cockpit.

The user says what they want in plain words; the Copilot rewrites it into a lean,
model-efficient prompt (``optimize``), routes it to the model that clears the
quality bar for the least cost (``router``), and can run many model sessions in
parallel from one place (``session``). Everything runs locally on the user's own
keys — prompts never leave the machine.
"""

from handover.copilot.optimize import OptimizedPrompt, optimize
from handover.copilot.router import Candidate, load_candidates, pick
from handover.copilot.session import Session, SessionManager, SessionReply

__all__ = [
    "Candidate",
    "OptimizedPrompt",
    "Session",
    "SessionManager",
    "SessionReply",
    "load_candidates",
    "optimize",
    "pick",
]
