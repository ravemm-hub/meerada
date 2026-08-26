import importlib

import handover

SUBPACKAGES = [
    "schema",
    "collect",
    "assemble",
    "verify",
    "metrics",
    "cluster",
    "pack",
    "replay",
    "migrate",
    "canary",
    "report",
    "cli",
]


def test_package_tree_imports() -> None:
    assert handover is not None
    for name in SUBPACKAGES:
        importlib.import_module(f"handover.{name}")
