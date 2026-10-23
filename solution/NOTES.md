# 领域说明与复算

## 双品种配制

班次 t 可以为 A 或 B 各配制若干次，但 A 次数加 B 次数不能超过该班的 `capacity`。
每次固定产出 B 支同一品种，品种 A、B 各自拥有 L 个班次的保质期。一个班次同时配制两种
药液时只收一次换线费，与两种药液各运行多少次无关。

方案成本为：

```text
cost = total_runs * run_cost_cents
       + total_wasted_doses * waste_cost_cents
       + total_changeovers * changeover_cost_cents
```

每个生产明细必须满足：

```text
produced_doses = runs * batch_size
produced_doses = used_doses + wasted_doses
```

每个班次消耗需求和淘汰失效桶之后，A、B 合计剩余库存不得超过
`storage_capacity_doses`。超限的状态不能进入下一班次，展开器也会对提交的次数向量
重新检查这个条件。

## 联合最优次数

状态由 A、B 两个年龄桶数组共同组成。每个桶表示距离失效还剩多少班次；桶 0 在当前班次
结束后失效。枚举本班全部 `(A次数, B次数)` 组合，只要两者之和不超过 capacity，就分别
把对应产出加入 A、B 的最远失效桶，再按品种分别从最早失效桶开始满足当前需求。

本班结束后，两种药液的桶 0 都计入报废；若两种次数同时为正，再加一次换线费。状态保留
相同库存下成本更低的前缀，成本相同则保留逐班二元组序列字典序更小的前缀。最后对 A、B
剩余库存补记报废成本，再比较总成本和序列。转移过程中同时丢弃超过冷库容量的状态。

## 独立复算

`tests/test_outputs.py` 的 `reference_plan()` 只依赖实例和 A/B 次数行，分别维护两个品种的
库存并执行 FIFO；`brute_force_plan()` 枚举每班所有满足 `A + B <= capacity` 的配对数，
按 `(total_cost_cents, [(A,B), ...])` 选最小项。两边都不调用待修程序的状态转移或合计函数。

演示数据由 `solution/generate_example.py` 以固定种子 20261023 生成；它是可复现实验数据，
不表示医院实际需求记录。
