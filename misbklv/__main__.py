from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import decode, probe


def cmd_probe(args: argparse.Namespace) -> int:
    meta_pid, video_pid = 0x0102, 0x0100
    if args.policy:
        pol = json.loads(Path(args.policy).read_text())
        meta_pid = int(pol.get("meta_pid", meta_pid))
        video_pid = int(pol.get("video_pid", video_pid))
    info = probe.probe_path(args.input, meta_pid=meta_pid, video_pid=video_pid)
    text = probe.format_probe(info)
    if args.out:
        Path(args.out).write_text(text + "\n")
    else:
        sys.stdout.write(text + "\n")
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    try:
        return decode.decode(args.input, args.policy, args.telemetry, args.report)
    except decode.DecodeError as e:
        sys.stderr.write(str(e) + "\n")
        return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="misbklv")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("probe", help="inventory TS PIDs and raw UAS Local Sets")
    sp.add_argument("--input", required=True)
    sp.add_argument("--policy", default=None)
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_probe)
    sd = sub.add_parser("decode", help="decode 0601 and align to video PTS")
    sd.add_argument("--input", required=True)
    sd.add_argument("--policy", required=True)
    sd.add_argument("--telemetry", required=True, help="output JSONL telemetry")
    sd.add_argument("--report", required=True)
    sd.set_defaults(func=cmd_decode)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
