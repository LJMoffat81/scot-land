"""SYNTHETIC dry run. The B2 CLI runs in-process. No market price file."""

from __future__ import annotations

import json
from pathlib import Path

from v14_dryrun.dryrun import run


def test_pr2_dryrun_b2_chain(tmp_path: Path) -> None:
    """SYNTHETIC. B2 accepts D7 only through the pinned chain and fits S-x2."""
    result = run(tmp_path)
    assert result["status"] == "passed"
    payload = json.loads(Path(result["out"]).read_text(encoding="utf-8"))
    assert payload["label"] == "SYNTHETIC"
    assert payload["fidelity_adaptation"] == "bedrooms_o_d1"
    assert payload["d7_sha256"]
    assert payload["d7_provenance"]["filter2_output_sha256"] == payload["d7_sha256"]
    assert payload["d7_provenance"]["filter1_script_sha256"] == (
        "849081cdad05aad0a8ed4f84eacdf2bc155af5082d03a0fad459b9777097a564"
    )
    assert payload["d7_provenance"]["filter2_script_sha256"] == (
        "e4b3561b38ad982a6ffa8124156bfdc2ce3fa84ff93fb60c3e82543839dc2f8d"
    )
    assert payload["fit"]["s_x2"] == "fit"
