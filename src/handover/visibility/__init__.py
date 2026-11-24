"""Visibility Monitor — who do the AI answer engines recommend when a person asks
for a local business? The first module of the presence engine
(``docs/PRESENCE-ENGINE.md`` §8 T1).

The same question goes to the four engines people actually use (ChatGPT with
web search, Perplexity Sonar, Gemini with Google grounding, Claude with web
search). Every answer is kept verbatim with its citations; the businesses named
are extracted by a program (evidence ``derived``), aggregated with n and a
Wilson interval, and rendered as a public page. Spend is pre-authorized against
a hard daily cap, like the exchange's grader.
"""
