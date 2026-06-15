#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ac6_fhm import ext_for_magic, parse_fhm as parse_fhm_container, safe_tag


DUMP_RE = re.compile(
    r"^entry_(?P<record_id>\d+)_mode(?P<mode>\d+)_c(?P<compressed_size>\d+)_u(?P<decompressed_size>\d+)"
    r"(?:_off(?P<source_offset>[0-9a-fA-F]+))?\.bin$"
)


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"entries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest_entries(path: Path) -> dict[tuple[int, int], list[dict]]:
    manifest = load_manifest(path)
    by_pair: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for entry in manifest["entries"]:
        if entry["storage_kind"] != "compressed":
            continue
        by_pair[(entry["compressed_size"], entry["decompressed_size"])].append(entry)
    return by_pair


def safe_name(name: str) -> str:
    return safe_tag(name)


def extract_container(blob: bytes, container_dir: Path, output_root: Path, depth: int,
                      max_depth: int) -> list[dict]:
    children = parse_fhm_container(blob) or []
    if not children:
        return []

    child_entries = []
    for child in children:
        safe_magic = safe_name(child.magic)
        child_name = f"{child.index:03d}_{safe_magic}{ext_for_magic(child.magic)}"
        child_path = container_dir / child_name
        child_path.write_bytes(child.data)

        child_entry = {
            "index": child.index,
            "offset": child.offset,
            "declared_size": child.declared_size,
            "size": child.size,
            "magic": child.magic,
            "path": str(child_path.relative_to(output_root)).replace("\\", "/"),
        }
        if child.notes:
            child_entry["parser_notes"] = child.notes

        if depth < max_depth and child.data[:4] == b"FHM ":
            nested_dir = container_dir / f"{child.index:03d}_{safe_magic}"
            nested_dir.mkdir(parents=True, exist_ok=True)
            nested_children = extract_container(child.data, nested_dir, output_root, depth + 1,
                                                max_depth)
            if nested_children:
                child_entry["nested"] = nested_children

        child_entries.append(child_entry)

    return child_entries


def extract_blob(blob: bytes, label: str, output_root: Path, max_depth: int,
                 source_record: dict) -> dict:
    container_dir = output_root / safe_name(label)
    container_dir.mkdir(parents=True, exist_ok=True)

    children = parse_fhm_container(blob) or []
    if not children:
        raw_path = container_dir / f"{safe_name(label)}.bin"
        raw_path.write_bytes(blob)
        return {
            **source_record,
            "kind": "raw",
            "magic": blob[:4].decode("latin-1", errors="replace") if len(blob) >= 4 else "",
            "size": len(blob),
            "path": str(raw_path.relative_to(output_root)).replace("\\", "/"),
        }

    child_entries = extract_container(blob, container_dir, output_root, 0, max_depth)
    return {
        **source_record,
        "kind": "fhm",
        "child_count": len(child_entries),
        "children": child_entries,
    }


def iter_offline_manifest_sources(manifest_path: Path, files_dir: Path) -> list[dict]:
    manifest = load_manifest(manifest_path)
    sources = []
    manifest_root = manifest_path.parent
    for entry in manifest.get("entries", []):
        if not entry.get("extracted"):
            continue
        rel_path = entry.get("path")
        if not rel_path:
            continue
        path = manifest_root / rel_path
        if files_dir and not path.is_relative_to(files_dir):
            # Keep support for custom --pac-files while still trusting the
            # manifest's relative paths when they point elsewhere.
            alt = files_dir / Path(rel_path).name
            if alt.exists():
                path = alt
        if not path.exists():
            continue
        sources.append({"entry": entry, "path": path})
    return sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract child payloads from offline-decoded or runtime-dumped AC6 FHM containers.")
    parser.add_argument(
        "--dump-dir",
        type=Path,
        default=Path("out") / "ac6_pac_runtime_dump",
        help="Directory containing runtime PAC decode dumps",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("out") / "ac6_pac_extracted_raw" / "manifest.json",
        help="Manifest produced by extract_ac6_pac.py",
    )
    parser.add_argument(
        "--pac-files",
        type=Path,
        default=None,
        help="Decoded PAC files directory produced by extract_ac6_pac.py (default: <manifest-dir>/files)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("out") / "ac6_runtime_fhm_typed",
        help="Output directory for parsed FHM containers and child payloads",
    )
    parser.add_argument(
        "--include-runtime-dumps",
        action="store_true",
        help="Also merge entry_* runtime dumps from --dump-dir when present",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=4,
        help="Maximum nested FHM recursion depth",
    )
    args = parser.parse_args()

    dump_dir = args.dump_dir.resolve()
    manifest_path = args.manifest.resolve()
    pac_files = args.pac_files.resolve() if args.pac_files else manifest_path.parent / "files"
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    by_pair = load_manifest_entries(manifest_path)
    extracted = []

    for source in iter_offline_manifest_sources(manifest_path, pac_files):
        entry = source["entry"]
        path = source["path"]
        blob = path.read_bytes()
        label = f"idx_{entry['index']:04d}"
        extracted.append(
            extract_blob(
                blob,
                label,
                output_root,
                args.max_depth,
                {
                    "source": "offline_pac",
                    "entry_index": entry["index"],
                    "pac_name": entry["pac_name"],
                    "storage_kind": entry["storage_kind"],
                    "compressed_size": entry["compressed_size"],
                    "decompressed_size": entry["decompressed_size"],
                    "source_offset": entry["offset"],
                    "input_path": str(path.relative_to(manifest_path.parent)).replace("\\", "/"),
                },
            )
        )

    selected_dumps: dict[tuple[int, int, int, int], Path] = {}

    runtime_dump_count = 0
    runtime_glob = sorted(dump_dir.glob("*.bin")) if args.include_runtime_dumps and dump_dir.exists() else []
    for dump_path in runtime_glob:
        match = DUMP_RE.match(dump_path.name)
        if not match:
            continue

        meta = match.groupdict()
        key = (
            int(meta["record_id"]),
            int(meta["mode"]),
            int(meta["compressed_size"]),
            int(meta["decompressed_size"]),
        )
        current = selected_dumps.get(key)
        if current is None:
            selected_dumps[key] = dump_path
            continue

        current_match = DUMP_RE.match(current.name)
        assert current_match is not None
        current_has_offset = current_match.groupdict()["source_offset"] is not None
        new_has_offset = meta["source_offset"] is not None
        if new_has_offset and not current_has_offset:
            selected_dumps[key] = dump_path

    for dump_path in sorted(selected_dumps.values()):
        runtime_dump_count += 1
        match = DUMP_RE.match(dump_path.name)
        assert match is not None

        meta = match.groupdict()
        compressed_size = int(meta["compressed_size"])
        decompressed_size = int(meta["decompressed_size"])
        codec_mode = int(meta["mode"])
        record_id = int(meta["record_id"])
        source_offset = int(meta["source_offset"], 16) if meta["source_offset"] else None
        candidates = by_pair.get((compressed_size, decompressed_size), [])

        base_label = (
            f"idx_{candidates[0]['index']:04d}"
            if len(candidates) == 1
            else f"pair_c{compressed_size}_u{decompressed_size}"
        )
        blob = dump_path.read_bytes()
        extracted.append(
            extract_blob(
                blob,
                f"runtime_{base_label}",
                output_root,
                args.max_depth,
                {
                    "source": "runtime_dump",
                    "dump": dump_path.name,
                    "record_id": record_id,
                    "codec_mode": codec_mode,
                    "compressed_size": compressed_size,
                    "decompressed_size": decompressed_size,
                    "source_offset": source_offset,
                    "candidate_indexes": [entry["index"] for entry in candidates],
                },
            )
        )

    manifest = {
        "pac_files": str(pac_files),
        "dump_dir": str(dump_dir) if args.include_runtime_dumps else None,
        "manifest": str(manifest_path),
        "output": str(output_root),
        "containers": extracted,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "containers": len(extracted),
                "offline_sources": sum(1 for item in extracted if item.get("source") == "offline_pac"),
                "runtime_dumps": runtime_dump_count,
                "output": str(output_root),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
