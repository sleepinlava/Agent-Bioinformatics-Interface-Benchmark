#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Workspace Reset

Copies the specified fixture into an isolated workspace directory,
ensuring clean state before each task run.

Usage:
    python bench/harness/reset_workspace.py \
      --fixture bench/fixtures/plasmid_valid \
      --workspace bench/workspaces/G3/T03/replicate_01
"""

import argparse
import shutil
import sys
from pathlib import Path


def reset_workspace(fixture_dir: Path, workspace_dir: Path, overwrite: bool = False,
                   group_id: str = ""):
    """Copy fixture contents to workspace. Raises if workspace exists (unless overwrite)."""
    if not fixture_dir.is_dir():
        print(f"ERROR: Fixture directory not found: {fixture_dir}", file=sys.stderr)
        return 1

    if workspace_dir.exists():
        if not overwrite:
            print(f"ERROR: Workspace already exists: {workspace_dir}", file=sys.stderr)
            print("Use --overwrite to replace it.", file=sys.stderr)
            return 1
        shutil.rmtree(workspace_dir)

    workspace_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture_dir, workspace_dir, symlinks=False)

    # Create standard output directories
    provenance_dir = workspace_dir / "provenance"
    tables_dir = workspace_dir / "tables"
    report_dir = workspace_dir / "report"
    provenance_dir.mkdir(exist_ok=True)
    tables_dir.mkdir(exist_ok=True)
    report_dir.mkdir(exist_ok=True)

    # G4: Generate information-matched documentation (Fix 2)
    if group_id == "G4":
        from bench.harness.g4_docs import generate_g4_docs
        generated = generate_g4_docs(workspace_dir)
        print(f"G4 docs: {len(generated)} guide files generated in {workspace_dir / 'docs'}")

    print(f"Workspace reset: {fixture_dir} -> {workspace_dir}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Reset ABI-Bench workspace from fixture")
    parser.add_argument("--fixture", required=True, type=Path, help="Fixture directory to copy from")
    parser.add_argument("--workspace", required=True, type=Path, help="Workspace directory to create")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing workspace")
    parser.add_argument("--group-id", type=str, default="", help="Group ID (G1/G2/G3/G4/A1/A3/A4) for group-specific setup")
    args = parser.parse_args()

    return reset_workspace(args.fixture, args.workspace, args.overwrite, args.group_id)


if __name__ == "__main__":
    sys.exit(main())
