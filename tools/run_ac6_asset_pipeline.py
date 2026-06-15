#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
DEFAULT_ASSET_ROOT = Path("out") / "build" / "win-amd64-relwithdebinfo" / "assets"
DEFAULT_RAW_OUT = Path("out") / "ac6_pac_extracted_raw"
DEFAULT_DUMP_DIR = Path("out") / "ac6_pac_runtime_dump"
DEFAULT_TYPED_OUT = Path("out") / "ac6_runtime_fhm_typed"
DEFAULT_MDLP_OUT = Path("out") / "ac6_mdlp_parts"
DEFAULT_SWG_OUT = Path("out") / "ac6_runtime_swg_parsed"
DEFAULT_NTXR_OUT = Path("out") / "ac6_runtime_ntxr_exported"


def run_step(args: list[str], cwd: Path) -> None:
    cmd = [sys.executable, *args]
    subprocess.run(cmd, cwd=cwd, check=True)


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def count_fhm_containers(manifest: dict | None) -> int | None:
    if not manifest:
        return None
    containers = manifest.get("containers")
    if isinstance(containers, list):
        return sum(1 for item in containers if item.get("kind") == "fhm")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the AC6 asset extraction pipeline over offline-decoded PAC archives."
    )
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=DEFAULT_ASSET_ROOT,
        help="Directory containing DATA.TBL, DATA00.PAC, and DATA01.PAC",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=DEFAULT_RAW_OUT,
        help="Output directory for extract_ac6_pac.py",
    )
    parser.add_argument(
        "--dump-dir",
        type=Path,
        default=DEFAULT_DUMP_DIR,
        help="Directory containing optional runtime PAC decode dumps",
    )
    parser.add_argument(
        "--typed-out",
        type=Path,
        default=DEFAULT_TYPED_OUT,
        help="Output directory for extract_ac6_runtime_fhm.py",
    )
    parser.add_argument(
        "--swg-out",
        type=Path,
        default=DEFAULT_SWG_OUT,
        help="Output directory for parse_ac6_swg.py",
    )
    parser.add_argument(
        "--mdlp-out",
        type=Path,
        default=DEFAULT_MDLP_OUT,
        help="Output directory for extract_ac6_mdlp_parts.py",
    )
    parser.add_argument(
        "--ntxr-out",
        type=Path,
        default=DEFAULT_NTXR_OUT,
        help="Output directory for export_ac6_ntxr.py",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Pass --raw-only to extract_ac6_pac.py",
    )
    parser.add_argument(
        "--no-decompress",
        action="store_true",
        help="Do not pass --decompress to extract_ac6_pac.py",
    )
    parser.add_argument(
        "--include-runtime-dumps",
        action="store_true",
        help="Also process entry_* runtime dumps from --dump-dir when present",
    )
    parser.add_argument(
        "--skip-pac-extract",
        action="store_true",
        help="Skip extract_ac6_pac.py even if the PAC archives are available",
    )
    args = parser.parse_args()

    repo_root = THIS_DIR.parent
    asset_root = args.asset_root.resolve()
    raw_out = args.raw_out.resolve()
    dump_dir = args.dump_dir.resolve()
    typed_out = args.typed_out.resolve()
    mdlp_out = args.mdlp_out.resolve()
    swg_out = args.swg_out.resolve()
    ntxr_out = args.ntxr_out.resolve()

    raw_manifest = raw_out / "manifest.json"

    if not args.skip_pac_extract:
        if asset_root.exists():
            pac_args = [str(THIS_DIR / "extract_ac6_pac.py"), str(asset_root), "--output", str(raw_out)]
            if args.raw_only:
                pac_args.append("--raw-only")
            elif not args.no_decompress:
                pac_args.append("--decompress")
            run_step(pac_args, repo_root)
        elif not raw_manifest.exists():
            raise SystemExit(f"asset root does not exist and no prior raw manifest is available: {asset_root}")

    fhm_args = [
        str(THIS_DIR / "extract_ac6_runtime_fhm.py"),
        "--manifest",
        str(raw_manifest),
        "--pac-files",
        str(raw_out / "files"),
        "--output",
        str(typed_out),
    ]
    if args.include_runtime_dumps:
        fhm_args.extend(["--include-runtime-dumps", "--dump-dir", str(dump_dir)])
    run_step(fhm_args, repo_root)

    run_step(
        [
            str(THIS_DIR / "extract_ac6_mdlp_parts.py"),
            "--input",
            str(typed_out),
            "--output",
            str(mdlp_out),
        ],
        repo_root,
    )

    run_step(
        [
            str(THIS_DIR / "parse_ac6_swg.py"),
            "--input",
            str(typed_out),
            "--output",
            str(swg_out),
        ],
        repo_root,
    )

    run_step(
        [
            str(THIS_DIR / "export_ac6_ntxr.py"),
            "--input",
            str(typed_out),
            "--output",
            str(ntxr_out),
        ],
        repo_root,
    )

    summary = {
        "asset_root": str(asset_root),
        "raw_manifest": str(raw_manifest) if raw_manifest.exists() else None,
        "dump_dir": str(dump_dir) if args.include_runtime_dumps else None,
        "typed_manifest": str(typed_out / "manifest.json"),
        "mdlp_manifest": str(mdlp_out / "manifest.json"),
        "swg_manifest": str(swg_out / "manifest.json"),
        "ntxr_manifest": str(ntxr_out / "manifest.json"),
    }

    raw_data = read_json(raw_manifest)
    typed_data = read_json(typed_out / "manifest.json")
    mdlp_data = read_json(mdlp_out / "manifest.json")
    swg_data = read_json(swg_out / "manifest.json")
    ntxr_data = read_json(ntxr_out / "manifest.json")

    if raw_data:
        summary["pac_entries"] = raw_data.get("entry_count")
        summary["pac_extracted"] = raw_data.get("extracted_count")
        summary["pac_skipped"] = raw_data.get("skipped_count")
        summary["pac_decompressed"] = raw_data.get("decompressed_count")
    fhm_containers = count_fhm_containers(typed_data)
    if fhm_containers is not None:
        summary["fhm_containers"] = fhm_containers
    if mdlp_data:
        summary["mdlp_packages"] = mdlp_data.get("package_count")
    if swg_data:
        summary["swg_files"] = swg_data.get("parsed_count")
    if ntxr_data:
        summary["textures_exported"] = ntxr_data.get("exported_count")
        summary["textures_skipped"] = ntxr_data.get("skipped_count")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
