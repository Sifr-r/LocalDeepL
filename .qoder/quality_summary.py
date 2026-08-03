"""Summarize the code-quality results for the review."""
import json
from pathlib import Path

p = Path(r"d:\OmniScribe\.qoder\quality_results.json")
d = json.loads(p.read_text(encoding="utf-16"))

print("=== AGGREGATE ===")
print(f"directory:           {d.get('directory')}")
print(f"files_analyzed:      {d.get('files_analyzed')}")
print(f"average_score:       {d.get('average_score')}")
print(f"overall_grade:       {d.get('overall_grade')}")
print(f"total_code_smells:   {d.get('total_code_smells')}")
print(f"total_solid_violations: {d.get('total_solid_violations')}")

files = d.get("files", [])
print()
print("=== WORST 20 FILES BY SCORE ===")
for f in sorted(files, key=lambda x: x.get("quality_score", 100))[:20]:
    metrics = f.get("metrics", {})
    smells = f.get("smells", [])
    solids = f.get("solid_violations", [])
    funcs = f.get("function_details", [])
    high_cx = [fn for fn in funcs if fn.get("complexity", 0) > 10]
    long_fns = [fn for fn in funcs if fn.get("lines", 0) > 50]
    hi_score = sum(1 for s in smells if s.get("severity") == "high")
    print(
        f"  {f.get('quality_score'):3d} {f.get('grade')}  "
        f"smells={len(smells):3d} (h={hi_score})  solid={len(solids):2d}  "
        f"hi_cx={len(high_cx):2d}  long_fn={len(long_fns):2d}  "
        f"{f.get('file')}"
    )

print()
print("=== HIGHEST-COMPLEXITY FUNCTIONS (top 25) ===")
all_fns = []
for f in files:
    for fn in f.get("function_details", []):
        all_fns.append((
            fn.get("complexity", 0),
            fn.get("name", "?"),
            fn.get("lines", 0),
            f.get("file"),
            len(fn.get("parameters", [])) if isinstance(fn.get("parameters"), list) else fn.get("parameters", 0),
        ))
all_fns.sort(reverse=True)
for cx, name, lines, path, params in all_fns[:25]:
    short = path.replace("D:\\OmniScribe\\", "")
    print(f"  cx={cx:2d}  lines={lines:3d}  params={params}  {short}::{name}")

print()
print("=== SMELL TYPE DISTRIBUTION ===")
smell_dist = {}
sev_dist = {}
for f in files:
    for s in f.get("smells", []):
        t = s.get("type", "?")
        smell_dist[t] = smell_dist.get(t, 0) + 1
        sev = s.get("severity", "?")
        sev_dist[sev] = sev_dist.get(sev, 0) + 1
for t, c in sorted(smell_dist.items(), key=lambda x: -x[1]):
    print(f"  {c:4d}  {t}")
print()
print("Severity distribution:")
for s, c in sorted(sev_dist.items(), key=lambda x: -x[1]):
    print(f"  {c:4d}  {s}")

print()
print("=== SOLID VIOLATION DISTRIBUTION ===")
solid_dist = {}
for f in files:
    for s in f.get("solid_violations", []):
        t = s.get("principle", "?")
        solid_dist[t] = solid_dist.get(t, 0) + 1
for t, c in sorted(solid_dist.items(), key=lambda x: -x[1]):
    print(f"  {c:4d}  {t}")
