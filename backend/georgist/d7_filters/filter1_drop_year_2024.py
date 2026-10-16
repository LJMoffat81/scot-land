#!/usr/bin/env python3
"""Filter 1 (reconstructed from the inline step of 2026-10-16 23:17 BST): drop rows whose year
label is a single year >= 2024. Only the 'year' cell is inspected; all other cells are passed
through as opaque strings (never parsed). Non-numeric labels (pooled '2019-2024') are kept, as in
the original. Uses csv.writer defaults (CRLF line endings), matching the original output.
Usage: filter1_drop_year_2024.py IN OUT"""
import csv, sys
src, dst = sys.argv[1], sys.argv[2]
with open(src, newline='') as f:
    rows = list(csv.reader(f))
yi = rows[0].index('year')
out = [rows[0]] + [r for r in rows[1:] if not (r[yi].isdigit() and int(r[yi]) >= 2024)]
with open(dst, 'w', newline='') as f:
    csv.writer(f).writerows(out)
print(f"dropped={len(rows)-len(out)} kept={len(out)-1}")
