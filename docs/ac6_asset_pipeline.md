# AC6 Asset Pipeline

This pipeline extracts and converts the AC6 assets we currently understand.

It automates these stages:

1. `DATA.TBL` + `DATA00.PAC` / `DATA01.PAC` index extraction
2. Runtime PAC decode dump parsing
3. Recursive `FHM` extraction
4. `SWG` UI metadata parsing
5. `NTXR` texture export

## Offline mode-1 decompression (solved)

The pipeline can now **decompress every compressed PAC entry fully offline**, with
no need to launch the game. The AC6 "mode-1" codec has been reverse-engineered:

1. **Descramble**: stored bytes are XORed with an 8-byte repeating pad. The pad
   for a DATA.TBL entry is derived from the entry's table index:

   ```
   pad(index) = pi_words[2*(index % 256) + 1] ++ pi_words[2*(index % 256) + 2]
   ```

   where `pi_words` are the big-endian base-2^32 words of the fractional part of
   pi (`0x243F6A88 0x85A308D3 0x13198A2E ...`). The game generates these at runtime
   via Machin's formula (`4*arctan(1/5) - arctan(1/239)`); the offline tool simply
   computes pi to the needed precision.

2. **Inflate**: the descrambled bytes are raw DEFLATE (RFC 1951, no zlib/gzip
   wrapper) -- `zlib.decompress(data, wbits=-15)`.

This is implemented in `tools/ac6_mode1_codec.py` and wired into the extractor:

```powershell
python .\tools\extract_ac6_pac.py <asset_root> --decompress
```

Compressed entries are written as `files/DATA0x/compressed/<index>.decompressed.bin`
and the manifest records `decompressed_count` / `decode_failures`. Playing the game
to pre-populate `out/ac6_pac_runtime_dump` is no longer required for compressed-entry
extraction; it remains useful only for assets synthesized at runtime.

## Prerequisites

- The game assets exist at:
  - `C:\ext\New folder\AC6_recomp\out\build\win-amd64-relwithdebinfo\assets`
- If you want runtime-decoded content included, you must already have:
  - `C:\ext\New folder\AC6_recomp\out\ac6_pac_runtime_dump`

To collect runtime dumps in future runs:

```powershell
$env:AC6_DUMP_PAC_DECODED='1'
& 'C:\ext\New folder\AC6_recomp\out\build\win-amd64-relwithdebinfo\ac6recomp.exe'
```

Or use the launcher helper:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\launch_ac6_with_pac_dump.ps1
```

That script sets `AC6_DUMP_PAC_DECODED=1` and launches `ac6recomp.exe` for you.

## One-Command Usage

From the repo root:

```powershell
python .\tools\run_ac6_asset_pipeline.py
```

This uses the default paths:

- Asset root: `out\build\win-amd64-relwithdebinfo\assets`
- Raw PAC output: `out\ac6_pac_extracted_raw`
- Runtime dump input: `out\ac6_pac_runtime_dump`
- Typed FHM output: `out\ac6_runtime_fhm_typed`
- SWG output: `out\ac6_runtime_swg_parsed`
- Texture output: `out\ac6_runtime_ntxr_exported`

The wrapper prints a final JSON summary with the current corpus totals, including:

- PAC entries extracted
- runtime `FHM` container count
- parsed `SWG` files
- exported/skipped `NTXR` textures

## Useful Variants

Use a custom asset root:

```powershell
python .\tools\run_ac6_asset_pipeline.py --asset-root 'C:\path\to\assets'
```

Skip PAC re-extraction and only process existing dumps:

```powershell
python .\tools\run_ac6_asset_pipeline.py --skip-pac-extract
```

Recommended workflow after a new play session:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\launch_ac6_with_pac_dump.ps1
python .\tools\run_ac6_asset_pipeline.py --skip-pac-extract
```

Extract only PAC entries marked raw:

```powershell
python .\tools\run_ac6_asset_pipeline.py --raw-only
```

## Output Folders

- Raw PAC extraction:
  - `C:\ext\New folder\AC6_recomp\out\ac6_pac_extracted_raw`
- Parsed runtime FHM corpus:
  - `C:\ext\New folder\AC6_recomp\out\ac6_runtime_fhm_typed`
- Parsed SWG metadata:
  - `C:\ext\New folder\AC6_recomp\out\ac6_runtime_swg_parsed`
- Exported textures:
  - `C:\ext\New folder\AC6_recomp\out\ac6_runtime_ntxr_exported`

## What To Open

- Main texture manifest:
  - `C:\ext\New folder\AC6_recomp\out\ac6_runtime_ntxr_exported\manifest.json`
- SWG manifest:
  - `C:\ext\New folder\AC6_recomp\out\ac6_runtime_swg_parsed\manifest.json`
- Example exported textures:
  - `C:\ext\New folder\AC6_recomp\out\ac6_runtime_ntxr_exported`

## Notes About Texture Types

Not every texture is a normal color image.

The exporter now handles:

- Standard tiled `R8` atlases
- Standard tiled `RGBA8` atlases
- `BC1` textures
- `BC3` textures
- Packed-mip `BC3` families
- Six-face `BC1` assets using contact-sheet previews
- Several support textures stored as grayscale-in-ARGB

Some outputs are still valid but are things like:

- masks
- glyph sheets
- lookup textures
- normal maps
- cubemap-style faces

## Current Status

At the time this guide was written, the texture exporter was producing:

- `845` exported textures
- `0` skipped textures

That count applies to the currently available runtime dump corpus.
