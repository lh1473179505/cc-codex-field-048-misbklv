# misbklv

从 MPEG-TS 里解 MISB 0601 元数据并对到视频 PTS 的工具。`probe` 已经能列出 PID、视频 PTS 和原始 UAS Local Set 包。`decode` 还没有实现。

不要引入 libmisb、ffmpeg-python、GStreamer 或 KlvLib，也不要使用 Docker。请复用 `misbklv.tsparse`、`misbklv.pes` 和 `misbklv.klv`。标签含义和校验和算法以 `docs/decode-rules.md` 为准。

## 命令

```
python -m misbklv probe --input fixtures/uas.ts --policy fixtures/policy.json
python -m misbklv decode \
  --input fixtures/uas.ts \
  --policy fixtures/policy.json \
  --telemetry /tmp/misbklv-telemetry.jsonl \
  --report /tmp/misbklv-report.json
```

规则见 `docs/decode-rules.md`，报告字段见 `docs/report-schema.md`。
