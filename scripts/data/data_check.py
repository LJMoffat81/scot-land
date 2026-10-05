#!/usr/bin/env python3
"""Scot-LAND data check v2: change report, input traceability and derived-data guard.

Usage: python3 check.py <checkout> [--ref <sha>] [--base <sha>] [--allow <glob> ...]
                        [--allow-scope watched|all] [--json] [--untraced-out <file>]
Exit codes: 0 PASS (warnings allowed), 1 FAIL, 2 bad checkout.
Python 3 standard library only. Read-only on the checkout: git plumbing reads only, no network.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = []  # repo copy: pass --registers <md>... to trace against Data's registers
WATCHED = ["data/config/agr.yaml", "data/config/sources.yaml", "data/processed/councils.json",
           "docs/ENGINE.md", "docs/engine/LOG.md", "backend/agr/**"]
APPEND_ONLY = ["docs/engine/LOG.md"]
CONFIG_GLOBS = ["data/config/**"]
CONFIG_EXT = (".yaml", ".yml", ".json", ".toml")

GEO_EXT = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qix", ".gpkg", ".geojson",
           ".topojson", ".json", ".kml", ".kmz", ".gml", ".tif", ".tiff", ".asc", ".img", ".vrt",
           ".nc", ".zip", ".parquet", ".fgb", ".pmtiles", ".mbtiles", ".csv", ".jsonl")
RAW_GIS_EXT = (".shp", ".shx", ".dbf", ".sbn", ".sbx", ".qix", ".gpkg", ".tif", ".tiff", ".asc",
               ".img", ".vrt", ".fgb", ".pmtiles", ".mbtiles")
NAME_PAT = re.compile(r"(^|[^a-z])(lca|lcf|land[_-]?capab|hutton|inspire|cadastr|ros[_-]|scotlis|"
                      r"sasine|title[_-]?(plan|outline|extent)|lcf250k|lca_?250k)", re.I)
SNIFF_EXT = (".geojson", ".topojson", ".json", ".jsonl", ".csv", ".kml", ".gml")
TOKENS = ["LCCODE", "lcf250k", "LCA_250K", "LCF_250K", "LAND_CLASS", "INSPIREID", "inspireId",
          "CP.CadastralParcel", "CadastralParcel", "James Hutton Institute"]
SNIFF_BYTES = 2_000_000


class BadCheckout(Exception):
    pass


# ------------------------------------------------------------------ git (read-only)
def git(repo, *args, binary=False, ok=False):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, env=env)
    if r.returncode and not ok:
        raise BadCheckout("git %s: %s" % (" ".join(args), r.stderr.decode(errors="replace").strip()))
    if ok and r.returncode:
        return None
    return r.stdout if binary else r.stdout.decode("utf-8", "replace").strip()


def resolve(repo, rev):
    return git(repo, "rev-parse", "--verify", "--quiet", rev + "^{commit}", ok=True)


class Tree:
    """Content at --ref: the working tree when HEAD == ref, otherwise git objects."""

    def __init__(self, repo, ref, worktree):
        self.repo, self.ref, self.worktree = repo, ref, worktree

    def files(self):
        if self.worktree:
            tracked = git(self.repo, "ls-files", "-z").split("\0")
            other = git(self.repo, "ls-files", "-z", "--others", "--exclude-standard").split("\0")
            return [f for f in tracked if f and os.path.exists(os.path.join(self.repo, f))], [f for f in other if f]
        return [f for f in git(self.repo, "ls-tree", "-r", "-z", "--name-only", self.ref).split("\0") if f], []

    def read(self, path, limit=None):
        if self.worktree:
            p = os.path.join(self.repo, path)
            if not os.path.isfile(p):
                return None
            with open(p, "rb") as f:
                return f.read(limit) if limit else f.read()
        b = git(self.repo, "show", "%s:%s" % (self.ref, path), binary=True, ok=True)
        return b[:limit] if (b is not None and limit) else b


def changed_files(repo, base, tree):
    args = ["diff", "--no-renames", "--name-status", "-z", base] + ([] if tree.worktree else [tree.ref])
    parts = [p for p in git(repo, *args).split("\0") if p]
    out = {parts[i + 1]: parts[i][0] for i in range(0, len(parts) - 1, 2)}
    if tree.worktree:
        for f in tree.files()[1]:
            out.setdefault(f, "A?")  # untracked, not ignored
    return out


def base_read(repo, base, path):
    return git(repo, "show", "%s:%s" % (base, path), binary=True, ok=True)


# ------------------------------------------------------------------ globs
def glob_re(g):
    out, i = "", 0
    while i < len(g):
        if g.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif g.startswith("**", i):
            out, i = out + ".*", i + 2
        elif g[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif g[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(g[i]), i + 1
    return re.compile("^" + out + "$")


def matches(path, globs):
    return any(glob_re(g).match(path) for g in globs)


# ------------------------------------------------------------------ diff summary
def summary(old, new):
    if old is None:
        return "added (%d lines)" % (new or b"").decode("utf-8", "replace").count("\n")
    if new is None:
        return "deleted"
    a = old.decode("utf-8", "replace").splitlines()
    b = new.decode("utf-8", "replace").splitlines()
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    sa, sb = set(a), set(b)
    plus = sum(1 for x in b if x not in sa)
    minus = sum(1 for x in a if x not in sb)
    first = ("line %d: %r -> %r" % (i + 1, a[i][:90] if i < len(a) else "<eof>", b[i][:90] if i < len(b) else "<eof>")
             if i < max(len(a), len(b)) else "line endings/trailing bytes only")
    return "~+%d/-%d lines; first change %s" % (plus, minus, first)


# ------------------------------------------------------------------ numbers
NUM_RE = r"[-+]?(?:\d[\d_]*)?\.?\d+(?:[eE][-+]?\d+)?"
SCALAR_NUM = re.compile("^" + NUM_RE + "$")
DOC_NUM = re.compile(r"(?<![\w.\-])[-−]?£?(\d{1,3}(?:,\d{3})+|\d[\d_]*)(\.\d+)?(%?)")


def num(s):
    try:
        return float(s.replace("_", ""))
    except ValueError:
        return None


def yaml_numbers(text):
    out, stack, idx = [], [], {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = "" if raw.lstrip().startswith("#") else raw.split(" #")[0].rstrip()
        if not line.strip():
            continue
        ind = len(line) - len(line.lstrip(" "))
        body = line.strip()
        item = body.startswith("- ") or body == "-"
        while stack and (stack[-1][0] > ind or (stack[-1][0] == ind and (not item or stack[-1][1].startswith("[")))):
            stack.pop()
        if item:
            parent = ".".join(k for _, k in stack)
            idx[(parent, ind)] = idx.get((parent, ind), -1) + 1
            stack.append((ind, "[%d]" % idx[(parent, ind)]))
            body, ind = body[1:].strip(), ind + 2
            if not body:
                continue
        m = re.match(r"^([^:'\"]+|'[^']*'|\"[^\"]*\"):(?:\s+(.*))?$", body)
        if m:
            key, val = m.group(1).strip().strip("'\""), (m.group(2) or "").strip()
            path = ".".join([k for _, k in stack] + [key])
            if val and SCALAR_NUM.match(val):
                out.append((path, num(val), n, val))
            elif not val:
                stack.append((ind, key))
        elif SCALAR_NUM.match(body):
            out.append((".".join(k for _, k in stack), num(body), n, body))
    return out


def json_numbers(text):
    try:
        data = json.loads(text)
    except ValueError:
        return []
    out = []

    def walk(x, p):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            out.append((p, float(x), None, repr(x)))
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(v, "%s.%s" % (p, k) if p else str(k))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, "%s[%d]" % (p, i))
    walk(data, "")
    return out


def toml_numbers(text):
    out, table = [], ""
    for n, raw in enumerate(text.splitlines(), 1):
        s = raw.split("#")[0].strip()
        if s.startswith("["):
            table = s.strip("[]").strip()
            continue
        m = re.match(r"^([\w.\-]+)\s*=\s*(\S+)$", s)
        if m and SCALAR_NUM.match(m.group(2)):
            out.append(((table + "." if table else "") + m.group(1), num(m.group(2)), n, m.group(2)))
    return out


def py_numbers(text):
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        m = re.match(r"^([A-Z][A-Z0-9_]*)\s*(?::\s*\w+\s*)?=\s*(" + NUM_RE + r")\s*(#.*)?$", raw)
        if m:
            out.append((m.group(1), num(m.group(2)), n, m.group(2)))
    return out


def numbers_of(path, blob):
    if blob is None:
        return []
    t = blob.decode("utf-8", "replace")
    if path.endswith(".json"):
        return json_numbers(t)
    if path.endswith(".toml"):
        return toml_numbers(t)
    if path.endswith(".py"):
        return py_numbers(t)
    return yaml_numbers(t)


def doc_index(paths):
    lines = []
    for p in paths:
        if not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            for i, ln in enumerate(f, 1):
                vals = set()
                for m in DOC_NUM.finditer(ln):
                    v = num(m.group(1).replace(",", "") + (m.group(2) or ""))
                    if v is not None:
                        vals.add(v)
                        if m.group(3) == "%":
                            vals.add(round(v / 100.0, 12))
                lines.append((os.path.basename(p), i, ln, vals))
    return lines


def traced(path, keypath, value, lineno, docs):
    base = re.escape(os.path.basename(path))
    leaf = re.sub(r"\[\d+\]$", "", keypath).split(".")[-1] if keypath else ""
    for dn, dl, text, vals in docs:
        if not any(abs(v - value) <= 1e-9 * max(1.0, abs(value)) for v in vals):
            continue
        if leaf and leaf in text:
            return "%s:%d" % (dn, dl)
        if lineno:
            for m in re.finditer(base + r":(\d+(?:-\d+)?(?:\s*,\s*:?\d+(?:-\d+)?)*)", text):
                for part in re.split(r"\s*,\s*:?", m.group(1)):
                    a, _, b = part.partition("-")
                    if int(a) <= lineno <= int(b or a):
                        return "%s:%d" % (dn, dl)
    return None


# ------------------------------------------------------------------ checks
def check_changes(repo, base, tree, changed, allow, scope, res):
    for path in sorted(changed):
        watched = matches(path, WATCHED)
        old, new = base_read(repo, base, path), tree.read(path)
        status = "REPORT"
        note = summary(old, new)
        if allow and (watched or scope == "all"):
            if matches(path, allow):
                note += " [covered by --allow]"
            else:
                status, note = "FAIL", note + " [not covered by --allow]"
        res.append(("change", path, status, ("watched; " if watched else "") + note))
        if path in APPEND_ONLY and old is not None and new is not None and not new.startswith(old):
            res.append(("append-only", path, "WARN", "baseline content is not a prefix; " + summary(old, new)))
    if not any(r[0] == "change" for r in res):
        res.append(("change", "files", "REPORT", "no file changed since --base"))
    elif not any(r[0] == "change" and r[3].startswith("watched") for r in res):
        res.append(("change", "watched files", "REPORT", "none of the former frozen files changed"))


def check_trace(repo, base, tree, changed, docs, res, untraced):
    targets = [p for p in changed if matches(p, CONFIG_GLOBS) and changed[p] != "D"
               and p.endswith(CONFIG_EXT)]
    for path in sorted(targets):
        new = tree.read(path)
        old_vals = {(k, v) for k, v, _, _ in numbers_of(path, base_read(repo, base, path))}
        lines = new.decode("utf-8", "replace").splitlines() if new else []
        n_new = 0
        for k, v, ln, raw in numbers_of(path, new):
            if (k, v) in old_vals:
                continue
            n_new += 1
            if k.split(".")[-1] in ("version", "schema_version"):
                continue  # file-format counters, not model inputs
            if ln and "# ASSUMPTION:" in lines[ln - 1]:
                continue
            if v is not None and traced(path, k, v, ln, docs):
                continue
            untraced.append({"file": path, "key": k, "value": raw, "line": ln})
            res.append(("trace", path, "WARN", "untraced: %s = %s (line %s)" % (k, raw, ln)))
        if not any(r[0] == "trace" and r[1] == path for r in res):
            res.append(("trace", path, "PASS", "%d new or changed numeric value(s), all traced" % n_new))
    if not targets:
        res.append(("trace", "config", "PASS", "no config file changed since --base"))


def check_derived(tree, res):
    tracked, other = tree.files()
    hits = []
    for rel in tracked + other:
        low = rel.lower()
        ext = os.path.splitext(low)[1]
        tag = "" if rel in tracked else " [untracked]"
        if ext in RAW_GIS_EXT:
            hits.append("%s (raw GIS/raster file type)%s" % (rel, tag))
        elif ext in GEO_EXT and NAME_PAT.search(low):
            hits.append("%s (Hutton/RoS-like name with data extension)%s" % (rel, tag))
        elif ext in SNIFF_EXT:
            blob = (tree.read(rel, SNIFF_BYTES) or b"").decode("utf-8", "replace")
            tok = [t for t in TOKENS if t in blob]
            if tok:
                hits.append("%s (contains %s)%s" % (rel, ", ".join(tok), tag))
    res.append(("derived-data", "repo", "FAIL" if hits else "PASS",
                "; ".join(hits) if hits else "no Hutton/RoS-like files among %d files" % (len(tracked) + len(other))))


def write_untraced(path, ref, base, rows):
    now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write("# Untraced config values (data-check v2)\n\nNew or changed numeric config values with no row in "
                    "the model-inputs table or the v2 inputs proposal, and no `# ASSUMPTION:` comment. To source later.\n")
        f.write("\n## Run %s: ref %s, base %s\n\n| File | Key | Value | Line |\n|---|---|---|---|\n" % (now, ref[:12], base[:12]))
        for r in rows:
            f.write("| `%s` | `%s` | %s | %s |\n" % (r["file"], r["key"], r["value"], r["line"]))


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checkout")
    ap.add_argument("--ref", help="commit to check (default: HEAD of the checkout)")
    ap.add_argument("--base", help="last merge to diff against (default: parent of --ref if on origin/main, "
                                   "else git merge-base origin/main <ref>)")
    ap.add_argument("--allow", nargs="+", default=[], metavar="GLOB", help="files the job declared (** allowed)")
    ap.add_argument("--allow-scope", choices=["watched", "all"], default="watched",
                    help="apply --allow to watched files only (default) or to every changed file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--registers", nargs="+", metavar="MD", default=None,
                    help="register files for the trace check (default: Data's two registers on the box)")
    ap.add_argument("--untraced-out", default=None, help="append untraced values to this markdown file (default: print only)")
    a = ap.parse_args()
    root = os.path.abspath(a.checkout)
    info = {}
    try:
        if not os.path.isdir(root):
            raise BadCheckout("checkout path is not a directory: %s" % root)
        if git(root, "rev-parse", "--git-dir", ok=True) is None:
            raise BadCheckout("no git metadata in %s (v2 needs history to diff)" % root)
        head = resolve(root, "HEAD")
        ref = resolve(root, a.ref or "HEAD")
        if not ref:
            raise BadCheckout("--ref %s not found in the checkout" % a.ref)
        if a.base:
            base = resolve(root, a.base)
            if not base:
                raise BadCheckout("--base %s not found" % a.base)
            info["base_rule"] = "given"
        else:
            main_ref = resolve(root, "origin/main")
            if not main_ref:
                raise BadCheckout("no origin/main in the checkout; pass --base")
            on_main = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", ref, main_ref],
                                     env=dict(os.environ, GIT_OPTIONAL_LOCKS="0")).returncode == 0
            if on_main:
                base, info["base_rule"] = resolve(root, ref + "^"), "parent of --ref on origin/main"
            else:
                base, info["base_rule"] = git(root, "merge-base", main_ref, ref), "merge-base origin/main <ref>"
            if not base:
                raise BadCheckout("could not derive --base; pass it explicitly")
        tree = Tree(root, ref, worktree=(ref == head))
        if not (git(root, "cat-file", "-e", "%s:data/config" % ref, ok=True) is not None
                and git(root, "cat-file", "-e", "%s:backend" % ref, ok=True) is not None):
            raise BadCheckout("not a scot-land checkout (backend/ or data/config/ missing at ref)")
    except BadCheckout as e:
        out = {"result": "ERROR", "exit": 2, "problem": str(e)}
        print(json.dumps(out, indent=2) if a.json else "ERROR (exit 2): %s" % e)
        return 2

    info.update({"head": head, "ref": ref, "base": base,
                 "mode": "working tree (HEAD == ref, uncommitted changes included)" if tree.worktree
                 else "git objects (HEAD != ref)"})
    res, untraced = [], []
    changed = changed_files(root, base, tree)
    check_changes(root, base, tree, changed, a.allow, a.allow_scope, res)
    check_trace(root, base, tree, changed, doc_index(a.registers if a.registers is not None else DOCS), res, untraced)
    check_derived(tree, res)
    if untraced and a.untraced_out:
        write_untraced(a.untraced_out, ref, base, untraced)
        info["untraced_file"] = a.untraced_out
    failed = [r for r in res if r[2] == "FAIL"]
    result = "FAIL" if failed else "PASS"
    counts = {s: sum(r[2] == s for r in res) for s in ("FAIL", "WARN", "REPORT", "PASS")}
    if a.json:
        print(json.dumps({"result": result, "exit": 1 if failed else 0, "info": info, "counts": counts,
                          "changed_files": changed, "allow": a.allow, "allow_scope": a.allow_scope,
                          "untraced": untraced,
                          "checks": [dict(zip(("check", "target", "status", "detail"), r)) for r in res]}, indent=2))
    else:
        print("Scot-LAND data check v2: %s" % result)
        print("ref %s | base %s (%s) | %s" % (ref[:12], base[:12], info["base_rule"], info["mode"]))
        print("%d file(s) changed since base; --allow %s (%s)" % (len(changed), a.allow or "not given", a.allow_scope))
        for c, t, s, d in res:
            print("[%-6s] %-12s %s: %s" % (s, c, t, d))
        if untraced and a.untraced_out:
            print("untraced values written to %s" % a.untraced_out)
        print(" ".join("%s=%d" % kv for kv in counts.items()))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
