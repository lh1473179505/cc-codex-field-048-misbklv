# 报告 schema

| 字段 | 类型 | 含义 |
|---|---|---|
| input | string | |
| decision | string | `ok` 或 `reject` |
| reason_codes | string[] | |
| packets_seen | integer | 扫描到的 UAS LS 数 |
| emitted | integer | 写入 telemetry 的行数 |
| bad_checksum | integer | |
| skipped_keys | integer | |
| timestamp_jumps | integer | |
| missing_timestamp | integer | |
