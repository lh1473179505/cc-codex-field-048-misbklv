"""Inventory MPEG-TS PIDs and raw UAS Local Set packets. Does not decode 0601 tags."""

from __future__ import annotations

import json
from collections import defaultdict

from . import klv, pes, tsparse


def probe_path(path: str, meta_pid: int = 0x0102, video_pid: int = 0x0100) -> dict:
    packets = tsparse.read_ts(path)
    by_pid: dict[int, int] = defaultdict(int)
    pcrs = 0
    for pkt in packets:
        by_pid[pkt.pid] += 1
        if pkt.adaptation and pkt.adaptation.pcr is not None:
            pcrs += 1
    vunits = pes.collect_pes(packets, video_pid)
    munits = pes.collect_pes(packets, meta_pid)
    raw = b"".join(u.payload for u in munits)
    klvs = klv.iter_klv(raw)
    return {
        "path": path,
        "packets": len(packets),
        "pid_counts": {str(k): v for k, v in sorted(by_pid.items())},
        "pcr_samples": pcrs,
        "video_pid": video_pid,
        "video_pes": len(vunits),
        "video_first_pts": vunits[0].pts if vunits else None,
        "video_last_pts": vunits[-1].pts if vunits else None,
        "meta_pid": meta_pid,
        "meta_pes": len(munits),
        "meta_first_pts": munits[0].pts if munits else None,
        "klv_packets": [
            {
                "offset_in_payload": k.offset,
                "key": k.key.hex(),
                "is_uas_ls": k.key == klv.UAS_LS_KEY,
                "length": k.length,
            }
            for k in klvs
        ],
    }


def format_probe(info: dict) -> str:
    return json.dumps(info, ensure_ascii=False, indent=2)
