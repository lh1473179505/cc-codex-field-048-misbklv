"""Minimal PES collector for a single PID. Probe uses this; please reuse it."""

from __future__ import annotations

from dataclasses import dataclass

from .tsparse import TsError, TsPacket

PTS_MOD = 1 << 33


def parse_pts_field(data: bytes) -> int:
    if len(data) < 5:
        raise TsError("truncated PTS")
    return (
        ((data[0] >> 1) & 0x07) << 30
        | (data[1] << 22)
        | ((data[2] >> 1) << 15)
        | (data[3] << 7)
        | (data[4] >> 1)
    ) & (PTS_MOD - 1)


@dataclass
class PesUnit:
    stream_id: int
    pts: int | None
    payload: bytes
    offset: int


def collect_pes(packets: list[TsPacket], pid: int) -> list[PesUnit]:
    out: list[PesUnit] = []
    buf = b""
    start = 0
    collecting = False
    for pkt in packets:
        if pkt.pid != pid or not pkt.has_payload:
            continue
        if pkt.pusi:
            if collecting and buf:
                unit = _parse(buf, start)
                if unit:
                    out.append(unit)
            buf = pkt.payload
            start = pkt.offset
            collecting = True
        elif collecting:
            buf += pkt.payload
    if collecting and buf:
        unit = _parse(buf, start)
        if unit:
            out.append(unit)
    return out


def _parse(buf: bytes, offset: int) -> PesUnit | None:
    if len(buf) < 6 or buf[:3] != b"\x00\x00\x01":
        return None
    sid = buf[3]
    if len(buf) < 9:
        return PesUnit(sid, None, buf[6:], offset)
    flags = buf[7]
    hdrlen = buf[8]
    opt = buf[9 : 9 + hdrlen]
    pts = None
    if flags & 0x80 and len(opt) >= 5:
        pts = parse_pts_field(opt[:5])
    return PesUnit(sid, pts, buf[9 + hdrlen :], offset)
