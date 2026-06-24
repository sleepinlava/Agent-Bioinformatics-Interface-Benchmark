"""Load named ABI-Bench evaluation suites from a single manifest."""

from pathlib import Path

import yaml

SUITES_PATH = Path(__file__).resolve().parent.parent / "evaluation_suites.yaml"


def load_suites(path: Path = SUITES_PATH) -> dict[str, dict]:
    """Return validated suite definitions keyed by suite name."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    suites = data.get("suites", {})
    if not isinstance(suites, dict):
        raise ValueError(f"Invalid suites mapping in {path}")
    for name, suite in suites.items():
        tasks = suite.get("tasks", [])
        if not tasks or not all(isinstance(task, str) for task in tasks):
            raise ValueError(f"Suite {name!r} has no valid task list")
        if len(tasks) != len(set(tasks)):
            raise ValueError(f"Suite {name!r} contains duplicate task IDs")
    return suites


def resolve_suite(name: str, path: Path = SUITES_PATH) -> list[str] | None:
    """Resolve a named suite, returning ``None`` for an unknown name."""
    suite = load_suites(path).get(name)
    return list(suite["tasks"]) if suite else None
