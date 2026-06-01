#!/usr/bin/env python3
"""D0c — Packet Void Dev System audit.

Detects drift between a consumer project's rendered docs and the
result of re-rendering the current dev-system templates against the
consumer's PROJECT_PROFILE.yaml. Read-only — never mutates the
target repo.

Stdlib only. No Anthropic API. No execution of consumer-project code.

Usage:

    python devsystem/scripts/audit_project.py --target-dir <path>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Share the parser + renderer with bootstrap.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from bootstrap_project import (  # noqa: E402
    _list_templates,
    _plan_claude_surface,
    _plan_github_surface,
    _profile_assertions,
    _target_doc_path,
    parse_yaml,
    render_template,
)


def audit(target_dir: Path) -> int:
    target_dir = target_dir.resolve()
    if not target_dir.is_dir():
        print(f"target dir not found: {target_dir}", file=sys.stderr)
        return 2
    profile_file = target_dir / "PROJECT_PROFILE.yaml"
    if not profile_file.is_file():
        print(
            f"missing {profile_file} — was the target bootstrapped with "
            "this dev system?",
            file=sys.stderr,
        )
        return 2
    profile = parse_yaml(profile_file.read_text(encoding="utf-8"))
    _profile_assertions(profile)
    findings: list[str] = []
    # Docs drift.
    for template in _list_templates():
        rendered = render_template(
            template.read_text(encoding="utf-8"), profile,
        )
        out_path = _target_doc_path(template, target_dir)
        if not out_path.is_file():
            findings.append(f"missing rendered doc: {out_path}")
            continue
        on_disk = out_path.read_text(encoding="utf-8")
        if on_disk != rendered:
            findings.append(
                f"drift: {out_path} differs from re-rendered template "
                f"{template.name}"
            )
    # D0d — Claude-surface drift.
    for out_path, expected_content, executable in _plan_claude_surface(
        profile, target_dir,
    ):
        if not out_path.is_file():
            findings.append(f"missing Claude-surface artifact: {out_path}")
            continue
        on_disk = out_path.read_text(encoding="utf-8")
        if on_disk != expected_content:
            findings.append(
                f"drift: {out_path} differs from re-rendered template"
            )
            continue
        if executable:
            mode = out_path.stat().st_mode
            if not (mode & 0o111):
                findings.append(
                    f"executable-bit drift: {out_path} should be "
                    "executable (chmod +x)"
                )
    # D0e — GitHub-surface drift (workflows + PR template).
    for out_path, expected_content, _exe in _plan_github_surface(
        profile, target_dir,
    ):
        if not out_path.is_file():
            findings.append(f"missing GitHub-surface artifact: {out_path}")
            continue
        on_disk = out_path.read_text(encoding="utf-8")
        if on_disk != expected_content:
            findings.append(
                f"drift: {out_path} differs from re-rendered template"
            )
    if findings:
        for line in findings:
            print(line, file=sys.stderr)
        print(
            f"audit_project: {len(findings)} drift finding(s) — re-run "
            "bootstrap_project.py to refresh.",
            file=sys.stderr,
        )
        return 1
    print(f"audit_project: OK ({target_dir})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_project",
        description=(
            "Audit a Packet-Void-Dev-System-bootstrapped consumer "
            "project for drift against the current dev-system templates."
        ),
    )
    parser.add_argument(
        "--target-dir",
        required=True,
        type=Path,
    )
    args = parser.parse_args(argv)
    return audit(args.target_dir)


if __name__ == "__main__":
    sys.exit(main())
