# 01-feedstitch（信汇）

Feedstitch — 多源目录/价目 Feed 归并落库：解析 → 业务键去重/跨源权威裁决 → 按源水位线增量或全量落库。同键非键字段分歧时，由源权威序决定覆盖主数据还是隔离，不再一律进冲突队列。

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:5100 |
| API | http://localhost:10100 |

## 主链

配置源与夹具 → 配置源权威序 → 触发 Run → 解析 / 去重 / 权威裁决 → Canonical + 运行报告对账

## 权威序规则

每个源有可编辑的整数 `authority_rank`（数值越大越权威），在“源管理”页查看和保存。

当传入记录与 Canonical 同业务键、且 title/price/category 至少一项分歧时：

| 比较结果 | 处置 | 主数据 |
| --- | --- | --- |
| 传入源权威 > 当前归属源权威 | `authority_override` | 覆盖写入，并写 `authority_changes` 审计依据 |
| 传入源权威 < 当前归属源权威 | `authority_lost` | 不写主数据，冲突队列标注权威落败 |
| 权威相等 / 无法判定归属源 | `conflict` | 不写主数据，冲突隔离，禁止静默覆盖 |

非键字段一致时仍按 revision 走 `upsert` / `skip_stale`；权威序不参与。

## 种子说明

- **Alpha Catalog（clean）**：JSON，三件干净货号，权威序 **100**。
- **Beta Offers（dirty）**：JSONL，含与 Alpha 同键但价格不同的冲突行，权威序 **10**；另含独立货号和迟到低 revision 行。
- **Gamma Shelf（xml）**：简易 XML，两件独立货号，权威序 **50**。

用同一套夹具即可跑出两条权威路径（建议重置数据卷后分别验证）：

1. **低权威被隔离**：先跑 Alpha（incremental/full），再跑 Beta（incremental）→ SKU-1001 的 Beta 价 99 不进主数据，冲突队列 reason=`authority_lost`。
2. **高权威覆盖**：先跑 Beta（full），再跑 Alpha（full/incremental）→ SKU-1001 由 Alpha 的 129 覆盖 Beta 的 99，冲突队列页的“权威变更依据”出现 previous→incoming 记录。

打开“运行台”选源跑一次，报告中的 parsed / 写入 / 冲突 / 权威隔离 / 跳过，可与 Staging 处置明细、冲突列表行数、Canonical 条数逐项对上；报告里的 `reconcile` 区块会显式标记是否平账。

## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。

## 0-1 切口（未实现）

`lookback_backfill` / `schema_drift_guard` / `dead_letter_replay` / `webhook_push_source` /
`tombstone_retire` / `scd2_history` / `watermark_commit_gate` /
`field_map_transform` / `lineage_provenance`
