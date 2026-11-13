# decode 规则

默认策略见 `fixtures/policy.json`。视频 PID 默认 0x0100，元数据 PID 默认 0x0102，都是 PES。元数据的 stream id 为 0xBD。

## 0601 局部集

- 16 字节键必须是 `060e2b34020b01010e01030101000000`（UAS Datalink Local Set）。其它键跳过并在报告 `skipped_keys` 里计数。
- 值是一系列 Tag-Length-Value：Tag 和 Length 都是 BER，Tag 在本夹具里都小于 128（单字节）。禁止 indefinite length。
- 必须识别的标签：

| Tag | 长度 | 含义 |
|---|---|---|
| 1 | 2 | 校验和，uint16 大端 |
| 2 | 8 | Precision Time Stamp，UTC 微秒，uint64 大端 |
| 5 | 2 | Platform Heading，IMAPB(0, 360, 2)，单位度 |
| 13 | 4 | Sensor Latitude，IMAPB(-90, 90, 4)，单位度 |
| 14 | 4 | Sensor Longitude，IMAPB(-180, 180, 4)，单位度 |

- IMAPB(min, max, L)：把 L 字节无符号大端整数 r 映射为 `min + r * (max - min) / (2^(8*L) - 1)`。
- 未列出的标签必须忽略，不要因此失败。

## 校验和

- 把整个 KLV 包（16 字节键 + BER 长度 + 完整 value）拷贝一份，将 Tag 1 的两个数值字节置零（保留 tag 与 length），若总长为奇数则末尾补 0x00。
- 按 16 bit 大端字累加，模 65536。结果必须等于 Tag 1 的值。
- 校验和失败的包：不要输出到 telemetry，报告 `bad_checksum` 加一。不要尝试“修复”后再用。

## 时间对齐

- 每个通过校验的包用 Tag 2 的微秒时间，和对应该元数据 PES 的 PTS（90 kHz）一起写入 telemetry。
- 同时还要给出 `video_pts`：在视频 PID 上找与该元数据 PTS 最近的视频 PES PTS（环形最短距离），并给出 `video_pts_delta`（元数据 PTS 减视频 PTS，33 bit 环形有符号差）。
- `fixtures/uas.ts` 里有一处 Tag 2 时间戳向前跳了大约 2 秒（不是 PCR 不连续）。对跳变包仍然输出，但 `reason` 字段写 `timestamp_jump`，报告 `timestamp_jumps` 加一。判断阈值是策略 `jump_us`（默认 500000）。
- 缺 Tag 2 的包：若校验和通过，仍输出其它字段，`precision_us` 为 null，`reason` 为 `missing_timestamp`。

## 输出

`--telemetry` 为 UTF-8 JSONL，每行：

```
{"precision_us", "heading_deg", "lat_deg", "lon_deg", "meta_pts", "video_pts", "video_pts_delta", "reason"}
```

角度至少保留 6 位小数。`reason` 在正常包里为 null。

## 退出码

- 至少写出一条通过校验的遥测并且完整报告：退出 0，`decision` 为 `ok`。坏校验和与跳变不算 reject。
- 一个有效包都没有：退出 1，`decision` 为 `reject`，`reason_codes` 含 `no_valid_packet`。
- TS 无法解析：退出 2。
