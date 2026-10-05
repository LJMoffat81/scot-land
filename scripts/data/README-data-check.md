# Data check (`scripts/data_check.py`)

Read-only check run by Build before each push and by QA after it. Python standard library only.

    python3 scripts/data_check.py . --ref HEAD [--base <sha>] [--allow <glob>...] [--json]

- REPORT: every file changed since `--base` (default: parent of `--ref` on origin/main, else `git merge-base origin/main <ref>`).
- FAIL with `--allow`: a changed watched file (agr.yaml, sources.yaml, councils.json, docs/ENGINE.md, docs/engine/LOG.md, backend/agr/**) not covered by the job's declared files.
- WARN: `docs/engine/LOG.md` changed other than by appending.
- WARN: a new or changed number in `data/config/` with no `# ASSUMPTION:` comment on its line and no register row (`--registers <md>...`).
- FAIL: any committed or staged Hutton- or Registers of Scotland-derived file (LCA/LCF, INSPIRE or title outlines, raw GIS, derived rasters).
- No figure pins: QA reports figure moves.

Exit codes: 0 PASS (warnings allowed), 1 FAIL, 2 bad checkout or ref.
`backend/tests/test_data_check.py` runs it on the repo and on a throwaway repo with a Hutton-named file.
