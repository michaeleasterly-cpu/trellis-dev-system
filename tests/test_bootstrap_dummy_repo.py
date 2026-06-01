"""D0a — placeholder marking the future bootstrap contract.

The full bootstrap test lands in D0c. This file documents the
contract so a future stage cannot silently bypass it. The single
test below is ``xfail`` (non-strict) so D0a CI stays green while the
contract is still pending.

Contract (to be implemented in D0c):

* ``devsystem/scripts/bootstrap_project.py`` is stdlib-only.
* Given a valid PROJECT_PROFILE.yaml + a profile name + a target dir,
  it renders a complete project skeleton: ``.claude/path_registry.yaml``
  generated from the profile, all whitelisted docs/tests/scripts/
  rules/skills/agents/hooks/workflow files rendered into the target,
  and ``scripts/check_manifests.py`` rendered to validate the output.
* The rendered output passes every dev-system sentinel:
    - manifest linter (``check_manifests.py``)
    - path registry sentinel
    - Claude surface contract sentinel
    - memory boundary sentinel
    - memory index size sentinel
    - security guidance sentinel
    - session/cost report sentinel
* The rendered output contains no STE-specific path, no donor-repo
  memstore ID, and no donor-repo trading vocabulary.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _REPO / "devsystem" / "scripts" / "bootstrap_project.py"


@pytest.mark.xfail(
    reason=(
        "bootstrap_project.py lands in D0c; D0a is the skeleton-only "
        "stage and does not yet ship the bootstrap script. This "
        "xfail marker keeps the contract visible without reding CI."
    ),
    strict=False,
)
def test_bootstrap_project_script_exists_and_is_runnable() -> None:
    assert _BOOTSTRAP.is_file(), (
        f"missing {_BOOTSTRAP.relative_to(_REPO)} — bootstrap script "
        "is the D0c deliverable"
    )
    src = _BOOTSTRAP.read_text(encoding="utf-8")
    assert src.startswith("#!"), "bootstrap_project.py must have a shebang"
