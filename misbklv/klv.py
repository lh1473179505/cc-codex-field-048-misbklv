"""Raw KLV (BER length) scanner used by probe. The 0601 local-set decode is not implemented here."""

from __future__ import annotations

from dataclasses import dataclass


class KlvError(ValueError):
    pass


# MISB 0601 UAS Datalink Local Set key (16 bytes)
UAS_LS_KEY = bytes.fromhex("060e2b34020b01010e01030101000000")


def decode_ber(data: bytes, offset: int = 0) -> tuple[int, int]:
    if offset >= len(data):
        raise KlvError("truncated BER")
    b = data[offset]
    if b < 128:
        return b, offset + 1
    n = b & 0x7F
    if n == 0 or offset + 1 + n > len(data):
        raise KlvError("bad long BER")
    return int.from_bytes(data[offset + 1 : offset + 1 + n], "big"), offset + 1 + n


@dataclass
class Packet:
    key: bytes
    length: int
    value: bytes
    offset: int


def iter_klv(blob: bytes) -> list[Packet]:
    out = []
    pos = 0
    while pos + 16 <= len(blob):
        # resync: hunt for the UAS key if needed
        key = blob[pos : pos + 16]
        if key != UAS_LS_KEY:
            nxt = blob.find(UAS_LS_KEY, pos + 1)
            if nxt < 0:
                break
            pos = nxt
            key = blob[pos : pos + 16]
        try:
            length, voff = decode_ber(blob, pos + 16)
        except KlvError:
            pos += 1
            continue
        end = voff + length
        if end > len(blob):
            out.append(Packet(key, length, blob[voff:], pos))
            break
        out.append(Packet(key, length, blob[voff:end], pos))
        pos = end
    return out
