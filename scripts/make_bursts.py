#!/usr/bin/env python3
"""Rebuild data/bursts.{json,csv} (per-burst panel inventory) from data/fits_readings.json.

The burst list and the in_october flag come from the existing inventory (first column of the
old file); panel counts are recomputed from the final fits readings so the two files cannot drift.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OLD = HERE / 'data/bursts.json'
OUT_J = OLD
OUT_C = HERE / 'data/bursts.csv'

res = json.loads((HERE / 'data/fits_readings.json').read_text(encoding='utf-8'))
per = defaultdict(lambda: {'slides': set(), 'panels': 0, 'numeric': 0, 'not_detected': 0, 'data_only': 0})
for r in res:
    d = per[r['burst']]
    d['slides'].add(r['slide'])
    for p in r['panels']:
        d['panels'] += 1
        st = p['status']
        if st == 'number':
            d['numeric'] += 1
        elif st == 'not detected':
            d['not_detected'] += 1
        elif st == 'data only':
            d['data_only'] += 1
        else:
            raise SystemExit(f'unknown status {st!r} on slide {r["slide"]}')

old = json.loads(OLD.read_text(encoding='utf-8'))
old_names = {x['burst'] for x in old}
names = [b['burst'] for b in old] + [n for n in sorted(per) if per[n]['panels'] and n not in old_names]
in_oct = {b['burst']: b['in_october'] for b in old}

rows = []
for n in sorted(names):
    d = per.get(n)
    if d and d['panels']:
        rows.append({'burst': n, 'slides': len(d['slides']), 'first_slide': min(d['slides']), 'has_fit_page': True,
                     'panels': d['panels'], 'numeric': d['numeric'], 'not_detected': d['not_detected'],
                     'data_only': d['data_only'], 'in_october': in_oct.get(n, False)})
    else:
        rows.append({'burst': n, 'slides': 0, 'first_slide': None, 'has_fit_page': False,
                     'panels': 0, 'numeric': 0, 'not_detected': 0, 'data_only': 0, 'in_october': in_oct.get(n, False)})

OUT_J.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
with OUT_C.open('w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
tot = {k: sum(r[k] for r in rows) for k in ('panels', 'numeric', 'not_detected', 'data_only')}
print(f"{len(rows)} bursts; panels {tot['panels']} = numeric {tot['numeric']} + not_detected "
      f"{tot['not_detected']} + data_only {tot['data_only']}; no fit page: "
      f"{[r['burst'] for r in rows if not r['has_fit_page']]}")
