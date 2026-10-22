# 高警示药液跨班次配制计划

某住院药房把高警示注射液集中配制成固定规格的班次批次。配置组每天按班次排班，每次配制固定产出 `batch_size` 支，批次从配制班次起最多可使用 `shelf_life_shifts` 个班次；过了最后一个可用班次仍未使用的药液必须报废。班组产能有限，班组长希望给定未来需求后，得到总成本最低的配制安排，并能复核同事提交的方案。

`/workspace` 下的 `pharmacy_lots` 包目前只有入口和输入模型。请补全算法，保留下面三个命令及参数顺序：

```bash
cd /workspace
python -m pharmacy_lots plan instance.json plan.json
python -m pharmacy_lots audit instance.json plan.json audit.json
python -m pharmacy_lots run instance.json result.json
```

## 输入

`example.json` 是按固定种子生成的演示数据，不是医院实际记录。实例是一个 JSON 对象，必须恰好包含以下字段：

- `instance_id`：非空字符串；
- `batch_size`：每次配制的支数，整数 `1..12`；
- `shelf_life_shifts`：批次可用的班次数，整数 `1..6`，包含配制当班；
- `run_cost_cents`：每次配制的固定成本，非负整数分；
- `waste_cost_cents`：报废一支药液的成本，非负整数分；
- `shifts`：1 到 12 个班次，按 `index` 从 0 连续排列，每项恰好含 `index`、`demand`、`capacity` 三个整数；`demand` 为非负整数且不超过 60，`capacity` 为 `0..3`。

若实例字段、类型、班次编号或范围不合规，命令应以非零状态退出，且不得新建输出文件或覆盖已有输出。

## 配制规则

班次 `t` 配制 `k` 次会产出 `k * batch_size` 支药液，成本为 `k * run_cost_cents`。该批药液可以在班次 `t` 到 `t + shelf_life_shifts - 1` 使用。每次配制次数必须是不超过该班 `capacity` 的非负整数。

每个班次的需求必须由该班可用批次精确覆盖，不能少发，也不能跨过保质期继续使用。把每次配制的药液逐支分配；对同一个使用班次，必须优先消耗失效班次最早的批次。未使用的药液在其失效班次计入报废，计划结束时仍未用完的批次也全部报废。报废成本为 `waste_cost_cents` 乘以报废支数。

最终选择总成本最低的配制次数向量。总成本相同的候选方案不止一个时，比较从班次 0 开始的整数配制次数数组，取字典序最小者。若没有任何方案能覆盖全部需求，命令应失败且不写输出。

## 输出

`plan` 和 `run` 写出对象，字段名固定为：

```text
instance_id
run_counts                 每个班次一个非负整数
production                 每个班次一项，含 production_shift, runs,
                           produced_doses, used_doses, wasted_doses
allocations                只列正数分配，含 production_shift, use_shift, doses
total_runs
total_produced_doses
total_wasted_doses
total_cost_cents
```

`production` 按 `production_shift` 升序，`allocations` 先按 `production_shift` 再按 `use_shift` 升序。每项配制的 `produced_doses` 必须等于 `runs * batch_size`，并且严格满足 `produced_doses = used_doses + wasted_doses`。`total_cost_cents` 必须等于 `total_runs * run_cost_cents + total_wasted_doses * waste_cost_cents`。所有剂量和金额都使用整数，不得出现浮点数、`NaN` 或无限值。

## 方案复核

当实例本身有效、方案 JSON 能读入时，`audit` 输出：

```text
instance_id
valid
actual_cost_cents         方案自报总额为整数时填该值，否则为 null
minimum_cost_cents        从实例重新计算的最低总成本
reason                    方案有效时为空字符串，否则给出简短原因
```

审计必须独立重算最优次数及先到期先用分配，逐项核对次数、生产汇总、分配、报废量和总成本；不能只相信方案里的合计字段，也不能把可行但非最低成本的方案判为有效。若实例无效或方案文件无法解析，命令以非零状态退出，并保持已有输出不变。

## 实现约束

- 只使用 Python 标准库，不改变包名、命令名、参数顺序和 JSON 字段名。
- 配制次数必须联合考虑班次产能、固定批量和保质期，不能只按当前班次缺口做贪心。
- 同一使用班次按失效时间消耗；批次跨越多个班次时，已用量、报废量和总成本必须能够从明细复算。
- `plan`、`run` 和 `audit` 的输出写入应采用临时文件完成后再替换，失败路径不能留下半成品。
