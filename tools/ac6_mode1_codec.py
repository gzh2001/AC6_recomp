#!/usr/bin/env python3
from __future__ import annotations

import struct
import zlib
from functools import lru_cache


# Number of distinct pads. The keygen masks the index with 0xFF, so there are
# exactly 256 possible pads; entry indices beyond 255 reuse them mod 256.
_PAD_COUNT = 256

# We need pi fractional words up to 2*(255)+2 = 512, plus slack.
_PI_WORDS_NEEDED = 2 * (_PAD_COUNT - 1) + 3


@lru_cache(maxsize=1)
def _pi_fractional_words(nwords: int) -> tuple[int, ...]:
    """First `nwords` base-2^32 words of frac(pi), most-significant word first.

    Pure-integer Machin formula: pi = 16*arctan(1/5) - 4*arctan(1/239).
    """
    bits = 32 * nwords + 64

    def arctan_inv(x: int) -> int:
        total = 0
        term = (1 << bits) // x
        x2 = x * x
        k = 0
        sign = 1
        while term // (2 * k + 1):
            total += sign * (term // (2 * k + 1))
            term //= x2
            k += 1
            sign = -sign
        return total

    pi_scaled = 16 * arctan_inv(5) - 4 * arctan_inv(239)
    frac = pi_scaled - (3 << bits)  # drop the integer part "3"
    return tuple(
        (frac >> (bits - 32 * (i + 1))) & 0xFFFFFFFF for i in range(nwords)
    )


@lru_cache(maxsize=_PAD_COUNT)
def pad_for_index(index: int) -> bytes:
    """Return the 8-byte descramble pad for a DATA.TBL entry index."""
    words = _pi_fractional_words(_PI_WORDS_NEEDED)
    w0 = 2 * (index & 0xFF) + 1
    return struct.pack(">II", words[w0], words[w0 + 1])


def descramble(data: bytes, index: int) -> bytes:
    """Undo the XOR scrambling for a compressed entry at the given table index."""
    pad = pad_for_index(index)
    return bytes(b ^ pad[i & 7] for i, b in enumerate(data))


def decompress_entry(data: bytes, index: int, expected_size: int | None = None) -> bytes:
    """Descramble + raw-inflate a compressed PAC entry.

    Args:
        data: the on-disk (scrambled, compressed) entry bytes from DATA00/01.PAC.
        index: the entry's DATA.TBL row index (drives the descramble pad).
        expected_size: optional decompressed size from DATA.TBL for validation.

    Returns the decompressed payload (typically an FHM container).
    Raises zlib.error on a decode failure or ValueError on a size mismatch.
    """
    raw = descramble(data, index)
    out = zlib.decompress(raw, wbits=-15)
    if expected_size is not None and len(out) != expected_size:
        raise ValueError(
            f"decompressed size mismatch: got {len(out)}, expected {expected_size}"
        )
    return out


if __name__ == "__main__":
    # Smoke test: print the first few pads so the table can be eyeballed.
    for i in range(4):
        print(f"pad[{i}] = {pad_for_index(i).hex()}")
