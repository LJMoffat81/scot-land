#!/usr/bin/env python3
"""Filter 2: keep only rows whose year label is exactly one of 2019..2023 (label match only).
Drops the pooled '2019-2024' rows (Statistician PASS). Reads ONLY the 'year' column; other cells
are copied as raw bytes, never parsed. Fails if output years != {2019..2023}.
Usage: filter2_keep_2019_2023.py IN OUT"""
import sys
from collections import Counter
KEEP = {b'2019', b'2020', b'2021', b'2022', b'2023'}
src, dst = sys.argv[1], sys.argv[2]
with open(src, 'rb') as f:
    lines = f.read().splitlines(keepends=True)
hdr = lines[0].rstrip(b'\r\n').split(b',')
yi = hdr.index(b'year')
out, dropped, kept = [lines[0]], Counter(), Counter()
for ln in lines[1:]:
    y = ln.rstrip(b'\r\n').split(b',')[yi]
    if y in KEEP:
        kept[y.decode()] += 1; out.append(ln)
    else:
        dropped[y.decode()] += 1
if set(kept) != {k.decode() for k in KEEP}:
    sys.exit(f"FAIL: output years {sorted(kept)}")
with open(dst, 'wb') as f:
    f.writelines(out)
print(f"dropped={sum(dropped.values())} {dict(dropped)} kept={dict(sorted(kept.items()))}")
