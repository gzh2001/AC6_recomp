#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


MAGIC_EXT = {
    "FHM ": ".fhm", "NTXR": ".ntxr", "NDXR": ".ndxr", "NSXR": ".nsxr",
    "MDLP": ".mdlp", "PLAD": ".plad", "MATE": ".mate", "NFIC": ".nfic",
    "NFH\x00": ".nfh", "CAPT": ".capt", "Scen": ".scen", "ACE6": ".ace6",
    "RIFF": ".wav", "SWG\x00": ".swg",
}


def parse_fhm(blob: bytes):
    """Return list of (index, offset, child_bytes) or None if not an FHM."""
    if len(blob) < 0x1C or blob[:4] != b"FHM ":
        return None
    count = struct.unpack_from(">I", blob, 0x10)[0]
    if count == 0 or count > 100000:
        return []
    offs_base = 0x14
    size_base = offs_base + count * 4
    if size_base + count * 4 > len(blob):
        return []
    offsets = [struct.unpack_from(">I", blob, offs_base + i * 4)[0] for i in range(count)]
    sizes = [struct.unpack_from(">I", blob, size_base + i * 4)[0] for i in range(count)]
    out = []
    for i, (off, sz) in enumerate(zip(offsets, sizes)):
        if off == 0 or off >= len(blob):
            continue
        end = off + sz
        if end > len(blob) or end <= off:
            nxt = offsets[i + 1] if i + 1 < count else len(blob)
            end = min(nxt, len(blob))
        if end > off:
            out.append((i, off, blob[off:end]))
    return out


def magic_of(blob: bytes) -> str:
    return blob[:4].decode("latin-1") if len(blob) >= 4 else ""


def ext_for(blob: bytes) -> str:
    return MAGIC_EXT.get(magic_of(blob), ".bin")


def safe_tag(magic: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in magic) or "raw"


def unpack(blob: bytes, out_dir: Path, root: Path, depth: int, max_depth: int) -> list[dict]:
    children = parse_fhm(blob)
    if children is None:
        return []
    recs = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, off, child in children:
        magic = magic_of(child)
        name = f"{idx:04d}_{safe_tag(magic)}{ext_for(child)}"
        path = out_dir / name
        path.write_bytes(child)
        rec = {"index": idx, "offset": off, "size": len(child), "magic": magic,
               "path": str(path.relative_to(root)).replace("\\", "/")}
        if depth < max_depth and child[:4] == b"FHM ":
            nested = unpack(child, out_dir / f"{idx:04d}_FHM", root, depth + 1, max_depth)
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
            dst = out_root / f"{stem}{ext_for(blob)}"
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
