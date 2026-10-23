# 高警示药液跨班次配制计划

某住院药房在一条配制线上安排两种高警示注射液。每次配制固定产出 `batch_size` 支同一品种，批次从配制班次起最多可使用 `shelf_life_shifts` 个班次；过了最后一个可用班次仍未使用的药液必须报废。两种药液共用每个班次的配制次数上限，同一班次切换品种会额外产生一次换线成本。班组长希望给定未来需求后，得到总成本最低的配制安排，并能复核同事提交的方案。

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
- `changeover_cost_cents`：同一班次既配制 A 又配制 B 时的换线成本，非负整数分；
- `storage_capacity_doses`：班次结束后 A、B 合计可留存的药液上限，非负整数；
- `shifts`：1 到 12 个班次，按 `index` 从 0 连续排列，每项恰好含 `index`、`demand`、`capacity`。`demand` 必须恰好含 `A` 和 `B` 两个非负整数，每项不超过 30；`capacity` 是两种药液合计的配制次数上限，取 `0..3`。

若实例字段、类型、班次编号或范围不合规，命令应以非零状态退出，且不得新建输出文件或覆盖已有输出。

## 配制规则

班次 `t` 为品种 A 配制 `a` 次、为品种 B 配制 `b` 次时，必须满足 `a + b <= capacity`，产出分别为 `a * batch_size` 和 `b * batch_size` 支。A、B 的批次各自从配制班次起可用 `shelf_life_shifts` 个班次，互不共用库存。

每个班次每种品种的需求必须由该班可用批次精确覆盖，不能少发，不能跨品种替代，也不能跨过保质期继续使用。把每次配制的药液逐支分配；对同一品种和同一个使用班次，必须优先消耗失效班次最早的批次。未使用的药液在其失效班次计入报废，计划结束时仍未用完的批次也全部报废。

每个班次完成消耗和报废之后，A、B 两个品种仍留存的药液合计不能超过 `storage_capacity_doses`。这个上限只约束班次结束时的库存，不把当班生产并当班用完的药液计入库存；若某个配额内方案在任一班次结束时超过上限，该方案不可行。

总成本由三部分组成：

```text
total_runs * run_cost_cents
+ total_wasted_doses * waste_cost_cents
+ total_changeovers * changeover_cost_cents
```

若一个班次的 `a` 和 `b` 都大于 0，则该班次产生一次换线，`total_changeovers` 加一；同一班次只计一次。最终选择总成本最低的 A/B 配制次数方案。成本相同时，按班次 0 到末班依次比较二元组 `(A次数, B次数)`，取该序列字典序最小者。若没有任何方案能覆盖全部需求，命令应失败且不写输出。

## 输出

`plan` 和 `run` 写出对象，字段名固定为：

```text
instance_id
run_counts                 每个班次一个 {shift, A, B} 对象
production                 每个班次和品种一项，含 production_shift, sku,
                           runs, produced_doses, used_doses, wasted_doses
allocations                只列正数分配，含 production_shift, sku,
                           use_shift, doses
total_runs
total_produced_doses
total_wasted_doses
total_changeovers
total_cost_cents
```

`run_counts` 按 `shift` 升序，`production` 先按 `production_shift` 再按 `sku` 升序，`allocations` 先按 `production_shift`、再按 `sku`、最后按 `use_shift` 升序；`sku` 只允许 `A` 或 `B`。每一项 `produced_doses` 必须等于 `runs * batch_size`，且严格满足 `produced_doses = used_doses + wasted_doses`。`total_cost_cents` 必须与上面的三项成本公式一致。所有剂量和金额都使用整数，不得出现浮点数、`NaN` 或无限值。

## 方案复核

当实例本身有效、方案 JSON 能读入时，`audit` 输出：

```text
instance_id
valid
actual_cost_cents         方案自报总额为整数时填该值，否则为 null
minimum_cost_cents        从实例重新计算的最低总成本
reason                    方案有效时为空字符串，否则给出简短原因
```

审计必须独立重算 A/B 的联合最优次数、各自先到期先用分配、换线次数和总成本，逐项核对次数、生产汇总、分配、报废量及合计。不能只相信方案里的合计字段，也不能把可行但非最低成本的方案判为有效。若实例无效或方案文件无法解析，命令以非零状态退出，并保持已有输出不变。

## 实现约束

- 只使用 Python 标准库，不改变包名、命令名、参数顺序和 JSON 字段名。
- A 和 B 共用班次产能，但各自维护保质期库存；不能把两种药液合并成一条库存。
- 同一班次同时安排 A、B 时只能计一次换线成本，不能按运行次数重复计费。
- 配制次数必须联合考虑班次产能、固定批量、保质期和换线成本，不能只按当前班次缺口做贪心。
- `plan`、`run` 和 `audit` 的输出写入应采用临时文件完成后再替换，失败路径不能留下半成品。
