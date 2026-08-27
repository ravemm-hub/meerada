"""Brand configuration — the product name lives HERE and only here.

"Prooly" is a WORKING NAME (picked 2026-08-28; domain not purchased yet and
may be replaced). Rebranding the report, the CLI defaults, and the site build
means editing the constants below — nothing else in the codebase hardcodes
the brand. The Python package stays ``handover`` regardless: that is an
internal name, not the brand.
"""

BRAND_NAME = "Prooly"
GRADE_NAME = f"{BRAND_NAME} Grade"
PROCESS_NAME = "The Handshake"
TAGLINE = "Your AI, prooly measured."
CLI_NAME = "prooly"
