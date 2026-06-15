#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ac6_fhm import ext_for_blob, magic_of, parse_fhm, safe_tag


def unpack(blob: bytes, out_dir: Path, root: Path, depth: int, max_depth: int) -> list[dict]:
    children = parse_fhm(blob)
    if children is None:
        return []
    recs = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for child in children:
        magic = child.magic
        name = f"{child.index:04d}_{safe_tag(magic)}{ext_for_blob(child.data)}"
        path = out_dir / name
        path.write_bytes(child.data)
        rec = {"index": child.index, "offset": child.offset,
               "declared_size": child.declared_size, "size": child.size,
               "magic": magic, "path": str(path.relative_to(root)).replace("\\", "/")}
        if child.notes:
            rec["parser_notes"] = child.notes
        if depth < max_depth and child.data[:4] == b"FHM ":
            nested = unpack(child.data, out_dir / f"{child.index:04d}_FHM", root, depth + 1, max_depth)
            if nested:
                rec["children"] = nested
        recs.append(rec)
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=Path("out") / "ac6_pac_extracted_raw" / "files")
    ap.add_argument("--output", type=Path, default=Path("out") / "ac6_fhm_unpacked")
    ap.add_argument("--max-depth", type=int, default=8)
    args = ap.parse_args()

    inp = args.input.resolve()
    out_root = args.output.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    if inp.is_file():
        sources = [inp]
    else:
        sources = sorted(inp.rglob("*.bin"))

    manifest = []
    fhm_count = leaf_count = 0
    for src in sources:
        blob = src.read_bytes()
        stem = src.stem.split(".")[0]
        if blob[:4] != b"FHM ":
            # Top-level non-FHM (raw entry): copy through as a leaf.
            dst = out_root / f"{stem}{ext_for_blob(blob)}"
            dst.write_bytes(blob)
            manifest.append({"source": src.name, "kind": "leaf", "magic": magic_of(blob),
                             "path": str(dst.relative_to(out_root)).replace("\\", "/")})
            leaf_count += 1
            continue
        cdir = out_root / stem
        recs = unpack(blob, cdir, out_root, 0, args.max_depth)
        manifest.append({"source": src.name, "kind": "fhm", "child_count": len(recs),
                         "children": recs})
        fhm_count += 1

    def count_leaves(recs):
        n = 0
        for r in recs:
            if "children" in r:
                n += count_leaves(r["children"])
            else:
                n += 1
        return n

    total_leaves = leaf_count + sum(
        count_leaves(m["children"]) for m in manifest if m["kind"] == "fhm")
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"sources": len(sources), "fhm_containers": fhm_count,
                      "total_leaves": total_leaves, "output": str(out_root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
