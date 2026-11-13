"""MISB 0601 decode and PTS alignment. Not implemented in the initial snapshot."""

from __future__ import annotations


class NotImplementedDecode(NotImplementedError):
    pass


def decode(input_path: str, policy_path: str, telemetry_path: str, report_path: str) -> int:
    raise NotImplementedDecode(
        "misbklv.decode.decode is not implemented yet; TS / raw KLV probe already work"
    )
