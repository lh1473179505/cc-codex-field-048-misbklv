"""MPEG-TS packet and adaptation-field parser. Probe uses this; please reuse it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PACKET_SIZE = 188
SYNC = 0x47
PID_NULL = 0x1FFF


class TsError(ValueError):
    pass


@dataclass
class Adaptation:
    length: int
    discontinuity: bool
    random_access: bool
    es_priority: bool
    pcr: int | None  # 27 MHz ticks, already composed from base+ext
    opcr: int | None
    splicing_point: int | None
    raw: bytes


@dataclass
class TsPacket:
    tei: bool
    pusi: bool
    transport_priority: bool
    pid: int
    scrambling: int
    has_adaptation: bool
    has_payload: bool
    continuity: int
    adaptation: Adaptation | None
    payload: bytes
    offset: int  # byte offset in the file


def compose_pcr(base: int, ext: int) -> int:
    return (base & ((1 << 33) - 1)) * 300 + (ext % 300)


def split_pcr(pcr_27mhz: int) -> tuple[int, int]:
    base = (pcr_27mhz // 300) & ((1 << 33) - 1)
    ext = pcr_27mhz % 300
    return base, ext


def parse_adaptation(data: bytes) -> Adaptation:
    if not data:
        return Adaptation(0, False, False, False, None, None, None, data)
    length = data[0]
    body = data[1 : 1 + length] if length else b""
    flags = body[0] if body else 0
    pos = 1
    pcr = opcr = splice = None
    if flags & 0x10:
        if pos + 6 > len(body):
            raise TsError("truncated PCR")
        raw = int.from_bytes(body[pos : pos + 6], "big")
        base = raw >> 15
        ext = raw & 0x1FF
        pcr = compose_pcr(base, ext)
        pos += 6
    if flags & 0x08:
        if pos + 6 > len(body):
            raise TsError("truncated OPCR")
        raw = int.from_bytes(body[pos : pos + 6], "big")
        base = raw >> 15
        ext = raw & 0x1FF
        opcr = compose_pcr(base, ext)
        pos += 6
    if flags & 0x04:
        if pos >= len(body):
            raise TsError("truncated splice countdown")
        splice = body[pos]
        if splice & 0x80:
            splice = splice - 256
        pos += 1
    return Adaptation(
        length=length,
        discontinuity=bool(flags & 0x80),
        random_access=bool(flags & 0x40),
        es_priority=bool(flags & 0x20),
        pcr=pcr,
        opcr=opcr,
        splicing_point=splice,
        raw=data[: 1 + length],
    )


def parse_packet(buf: bytes, offset: int = 0) -> TsPacket:
    if len(buf) != PACKET_SIZE:
        raise TsError(f"packet must be {PACKET_SIZE} bytes, got {len(buf)}")
    if buf[0] != SYNC:
        raise TsError(f"missing sync at {offset}")
    tei = bool(buf[1] & 0x80)
    pusi = bool(buf[1] & 0x40)
    tprio = bool(buf[1] & 0x20)
    pid = ((buf[1] & 0x1F) << 8) | buf[2]
    scrambling = (buf[3] >> 6) & 0x3
    adap = (buf[3] >> 4) & 0x3
    cc = buf[3] & 0x0F
    rest = buf[4:]
    adaptation = None
    payload = b""
    if adap in (0b10, 0b11):
        if not rest:
            raise TsError("adaptation indicated but no data")
        alen = rest[0]
        adaptation = parse_adaptation(rest[: 1 + alen] if alen < len(rest) else rest)
        rest = rest[1 + alen :]
    if adap in (0b01, 0b11):
        payload = rest
    elif adap == 0b00:
        raise TsError("adaptation_field_control=00 is reserved")
    return TsPacket(
        tei=tei,
        pusi=pusi,
        transport_priority=tprio,
        pid=pid,
        scrambling=scrambling,
        has_adaptation=adap in (0b10, 0b11),
        has_payload=adap in (0b01, 0b11),
        continuity=cc,
        adaptation=adaptation,
        payload=payload,
        offset=offset,
    )


def iter_packets(blob: bytes) -> list[TsPacket]:
    if len(blob) % PACKET_SIZE:
        raise TsError(f"file size {len(blob)} is not a multiple of {PACKET_SIZE}")
    out = []
    for i in range(0, len(blob), PACKET_SIZE):
        out.append(parse_packet(blob[i : i + PACKET_SIZE], i))
    return out


def read_ts(path: str) -> list[TsPacket]:
    return iter_packets(Path(path).read_bytes())
