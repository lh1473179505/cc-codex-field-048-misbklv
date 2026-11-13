"""MISB 0601 UAS Local Set decode aligned to video PTS."""

from __future__ import annotations

import json
from pathlib import Path

from . import klv, pes, tsparse

TAG_CHECKSUM = 1
TAG_PRECISION = 2
TAG_HEADING = 5
TAG_LATITUDE = 13
TAG_LONGITUDE = 14

DEFAULT_META_PID = 0x0102
DEFAULT_VIDEO_PID = 0x0100
DEFAULT_JUMP_US = 500_000

PTS_MOD = pes.PTS_MOD
PTS_SIGN_BIT = 1 << 32

ROW_KEYS = (
    "precision_us",
    "heading_deg",
    "lat_deg",
    "lon_deg",
    "meta_pts",
    "video_pts",
    "video_pts_delta",
    "reason",
)
ANGLE_KEYS = ("heading_deg", "lat_deg", "lon_deg")


class DecodeError(Exception):
    """Raised when the transport stream or its KLV payload cannot be parsed."""


class NotImplementedDecode(DecodeError):
    """Kept for backwards compatibility with the initial snapshot."""


def imapb(raw: bytes, low: float, high: float) -> float:
    """IMAPB mapping: unsigned big-endian r over L bytes -> [low, high]."""
    r = int.from_bytes(raw, "big")
    return low + r * (high - low) / ((1 << (8 * len(raw))) - 1)


def ring_signed_delta(meta_pts: int, video_pts: int) -> int:
    """Signed 33-bit circular difference: meta_pts minus video_pts."""
    delta = (meta_pts - video_pts) & (PTS_MOD - 1)
    if delta >= PTS_SIGN_BIT:
        delta -= PTS_MOD
    return delta


def nearest_video_pts(meta_pts: int, video_pts_list: list[int]) -> int | None:
    """Video PES PTS with the shortest circular distance to meta_pts."""
    best_pts = None
    best_distance = None
    for video_pts in video_pts_list:
        distance = abs(ring_signed_delta(meta_pts, video_pts))
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_pts = video_pts
    return best_pts


def iter_klv_packets(blob: bytes):
    """Yield (klv.Packet, raw BER length bytes) for every KLV in blob."""
    pos = 0
    size = len(blob)
    while pos + 16 <= size:
        key = blob[pos : pos + 16]
        try:
            length, value_offset = klv.decode_ber(blob, pos + 16)
        except klv.KlvError as exc:
            raise DecodeError(f"bad BER length at payload offset {pos}") from exc
        length_bytes = blob[pos + 16 : value_offset]
        end = value_offset + length
        if end > size:
            raise DecodeError(f"truncated KLV packet at payload offset {pos}")
        yield klv.Packet(key, length, blob[value_offset:end], pos), length_bytes
        pos = end
    if pos != size:
        raise DecodeError("trailing bytes after KLV stream")


def parse_local_set(value: bytes) -> dict[int, bytes]:
    """Parse Tag-Length-Value items; unknown tags are walked but not required."""
    items: dict[int, bytes] = {}
    pos = 0
    while pos < len(value):
        tag = value[pos]
        try:
            length, value_start = klv.decode_ber(value, pos + 1)
        except klv.KlvError as exc:
            raise DecodeError(f"bad TLV BER length at value offset {pos}") from exc
        value_end = value_start + length
        if value_end > len(value):
            raise DecodeError("truncated TLV item in UAS Local Set")
        if tag not in items:
            items[tag] = value[value_start:value_end]
        pos = value_end
    return items


def checksum_matches(key: bytes, length_bytes: bytes, value: bytes, stored: int) -> bool:
    """16-bit big-endian word sum with Tag 1's value bytes zeroed, per ST.0601."""
    buf = bytearray(key) + bytearray(length_bytes) + bytearray(value)
    header_size = len(key) + len(length_bytes)
    pos = 0
    found = False
    while pos < len(value):
        tag = value[pos]
        length, value_start = klv.decode_ber(value, pos + 1)
        if tag == TAG_CHECKSUM:
            start = header_size + value_start
            buf[start : start + length] = b"\x00" * length
            found = True
            break
        pos = value_start + length
    if not found:
        return False
    if len(buf) % 2:
        buf.append(0x00)
    total = 0
    for i in range(0, len(buf), 2):
        total = (total + int.from_bytes(buf[i : i + 2], "big")) & 0xFFFF
    return total == stored


def render_row(row: dict) -> str:
    parts = []
    for key in ROW_KEYS:
        value = row[key]
        if key in ANGLE_KEYS:
            rendered = "null" if value is None else f"{value:.6f}"
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        parts.append(f"{json.dumps(key)}: {rendered}")
    return "{" + ", ".join(parts) + "}"


def decode(input_path: str, policy_path: str, telemetry_path: str, report_path: str) -> int:
    policy = json.loads(Path(policy_path).read_text()) if policy_path else {}
    video_pid = int(policy.get("video_pid", DEFAULT_VIDEO_PID))
    meta_pid = int(policy.get("meta_pid", DEFAULT_META_PID))
    jump_us = int(policy.get("jump_us", DEFAULT_JUMP_US))

    try:
        ts_packets = tsparse.read_ts(input_path)
    except (OSError, tsparse.TsError) as exc:
        raise DecodeError(f"cannot parse transport stream {input_path}: {exc}") from exc

    video_units = pes.collect_pes(ts_packets, video_pid)
    meta_units = pes.collect_pes(ts_packets, meta_pid)
    video_pts_list = [unit.pts for unit in video_units if unit.pts is not None]

    spans = []
    cursor = 0
    for unit in meta_units:
        spans.append((cursor, cursor + len(unit.payload), unit.pts))
        cursor += len(unit.payload)
    raw_meta = b"".join(unit.payload for unit in meta_units)

    def pts_for_offset(offset: int) -> int | None:
        for start, end, pts in spans:
            if start <= offset < end:
                return pts
        return None

    counters = {
        "packets_seen": 0,
        "emitted": 0,
        "bad_checksum": 0,
        "skipped_keys": 0,
        "timestamp_jumps": 0,
        "missing_timestamp": 0,
    }
    rows: list[dict] = []
    previous_precision_us: int | None = None

    for packet, length_bytes in iter_klv_packets(raw_meta):
        if packet.key != klv.UAS_LS_KEY:
            counters["skipped_keys"] += 1
            continue
        counters["packets_seen"] += 1

        items = parse_local_set(packet.value)
        checksum_item = items.get(TAG_CHECKSUM)
        if checksum_item is None or len(checksum_item) != 2:
            counters["bad_checksum"] += 1
            continue
        stored_checksum = int.from_bytes(checksum_item, "big")
        if not checksum_matches(packet.key, length_bytes, packet.value, stored_checksum):
            counters["bad_checksum"] += 1
            continue

        reason = None
        precision_item = items.get(TAG_PRECISION)
        if precision_item is not None and len(precision_item) == 8:
            precision_us = int.from_bytes(precision_item, "big")
            if previous_precision_us is not None:
                if precision_us - previous_precision_us > jump_us:
                    reason = "timestamp_jump"
                    counters["timestamp_jumps"] += 1
            previous_precision_us = precision_us
        else:
            precision_us = None
            reason = "missing_timestamp"
            counters["missing_timestamp"] += 1

        heading = imapb(items[TAG_HEADING], 0.0, 360.0) if TAG_HEADING in items else None
        latitude = imapb(items[TAG_LATITUDE], -90.0, 90.0) if TAG_LATITUDE in items else None
        longitude = imapb(items[TAG_LONGITUDE], -180.0, 180.0) if TAG_LONGITUDE in items else None

        meta_pts = pts_for_offset(packet.offset)
        if meta_pts is not None and video_pts_list:
            video_pts = nearest_video_pts(meta_pts, video_pts_list)
            video_pts_delta = ring_signed_delta(meta_pts, video_pts)
        else:
            video_pts = None
            video_pts_delta = None

        rows.append(
            {
                "precision_us": precision_us,
                "heading_deg": heading,
                "lat_deg": latitude,
                "lon_deg": longitude,
                "meta_pts": meta_pts,
                "video_pts": video_pts,
                "video_pts_delta": video_pts_delta,
                "reason": reason,
            }
        )

    telemetry_text = "".join(render_row(row) + "\n" for row in rows)
    Path(telemetry_path).write_text(telemetry_text, encoding="utf-8")
    counters["emitted"] = len(rows)

    decision = "ok" if rows else "reject"
    reason_codes = [] if rows else ["no_valid_packet"]
    report = {
        "input": input_path,
        "decision": decision,
        "reason_codes": reason_codes,
        "packets_seen": counters["packets_seen"],
        "emitted": counters["emitted"],
        "bad_checksum": counters["bad_checksum"],
        "skipped_keys": counters["skipped_keys"],
        "timestamp_jumps": counters["timestamp_jumps"],
        "missing_timestamp": counters["missing_timestamp"],
    }
    Path(report_path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if rows else 1
