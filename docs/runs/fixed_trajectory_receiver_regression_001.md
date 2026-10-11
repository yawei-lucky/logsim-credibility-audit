# 冻结轨迹 SparseDrive 接收方回归 001

2026-10-11。**输入 RGB、最终规划和已有 `D_domain` 数值均在预注册
阈值内复现；完整 native 中间状态未复现，所以完整主张失败，整体仍为
`down-weighted`。**

这是继 [HUGSIM 冻结轨迹渲染回归 001](fixed_trajectory_render_regression_001.md)
之后的 NuRec 式下游接收方和运行一致性检查。它检查现有 matched
real–sim 证据能否被当前冻结链路数值复现，不增加新的真实数据，也不升级
真实—仿真等效主张。

## 设计与身份门

[预注册](fixed_trajectory_receiver_regression_preregistration_001.md)、主比较器和阈值在
commit `ee04e0a00aa8ccf4280aadd960eac1d8d1c1a65d` 冻结后执行。执行时本仓库
工作区为空，本地与 `origin/main` 一致。

- `straight`：帧 `12,18,24,30,36,42,48,54`。
- `turn`：帧 `60,66,72,78,84,90,96,102`。
- 两段分别启动模型，各执行 baseline 和 independent reset repeat，共 32 个
  frame forward。
- 96 张唯一 RGB 来自完整的预注册渲染 `run002`；无损装配后它们与
  源文件、历史 golden 仍为 96/96 逐字节相同。
- SparseDrive commit `ec0225d…`、working diff/status、Stage2 checkpoint、config、
  adapter 及其间接 helper、四个 anchor、校准和 metadata 全部通过冻结哈希门。
- 运行环境与历史 receiver report 一致：PyTorch `2.0.1+cu118`、CUDA
  runtime `11.8`、NVIDIA GeForce RTX 4090 D、`TorchMHA` fallback，自定义
  deformable CUDA 关闭。
- 最终 plan、完整 native float 和 `D_domain` 复现阈值都在执行前固定为
  `1e-4`；native 整数／布尔要求精确相同。

## 主结果

| 检查 | straight | turn | 总体裁决 |
|---|---:|---:|---|
| 唯一 RGB 与历史 golden 逐字节一致 | 48/48 | 48/48 | `accepted` |
| historical↔current 时序帧 mode/command 相同 | 16/16 | 16/16 | `accepted` |
| final plan 最大绝对差 | `2.003e-5 m` | `1.812e-5 m` | `accepted`，低于 `1e-4 m` |
| 当前 baseline↔reset repeat plan 最大差 | `3.815e-6 m` | `2.241e-5 m` | `accepted`，低于 `1e-4 m` |
| `D_domain` 相对历史 audit 的最大指标差 | `9.537e-6 m` | `1.767e-5 m` | `accepted`，低于 `1e-4 m` |
| native 结构、dtype、shape 和有限性 | 通过 | 通过 | `accepted` 的窄事实 |
| native float 最大绝对差 | `46.8773` | `66.6675` | `rejected` |
| native integer mismatch | 10/16,016 | 12/16,016 | `rejected` |

32/32 个时序帧的输入合同在只忽略文件路径后完全相同，两段新运行的
原生输出全部有限，最终计划不退化。实验重算了 16 行 real–sim
`D_domain`，其中 10 行具有四帧完整历史；所有 real/sim mode 与历史 audit
相同。表中 `D_domain` 数字是**当前重算值与历史值之差**，不是 real–sim
域差异本身的大小。

这些结果支持一个有限正面主张：在该主机、该接收方和两个窗口内，当前
RGB 链路可以在既定 `1e-4 m` 数值阈值内复现旧的最终规划和已报告
`D_domain`。

## 完整 native 主张为什么失败

预注册要求历史与当前 `native_outputs.pt` 的浮点全局最大差不超过
`1e-4`，整数全部精确相同。实际两个窗口分别有 734,156/1,003,656 和
737,568/1,003,656 个浮点元素不是 bit-exact；最大差均出现在
`trajs_3d`。共有 22 个整数位置不同。

因此，预注册的**完整 native 状态复现主张为 `rejected`**，主比较器的
`all_checks_passed=false`。最终 plan 通过不能抹掉这个失败，也不能把中间差异
事后改成“无关”。

## Outcome-informed 定位

在主结果冻结后，按
[`native_difference_diagnostic_plan.md`](../../artifacts/fixed_trajectory_receiver_regression_001/native_difference_diagnostic_plan.md)
只读分析已产生的 `.pt` 和 JSON。该诊断不修改阈值，不恢复失败主张。

- 32/32 个 frame/variant 的 300 个 `instance_ids` 都各自唯一，历史与当前的
  ID 集合也完全相同。
- 14 个 ID 排名位置发生了对换，并带来 8 个 label 位置变化，合计就是主结果的
  22 个 integer mismatch。它们都位于 rank 80 之后，对应 score 不超过
  `0.021525`。
- 用完全相同的 instance ID 事后对齐后，label 和 ID 差异归零；直接比较中
  `boxes_3d` 的最大差从数十米量级降为 `7.186e-4`，`trajs_3d` 从
  `66.6675` 降为 `0.03824`。
- 对齐后仍然超过原 `1e-4` native 阈值，因此差异不只是排序表象。
- 每帧报告的前 10 个 detection 共 320 个，label 320/320 一致；最大 score
  差为 `1.918e-5`，最大 box 分量差为 `3.697e-4`。它们没有真值匹配，所以这只是
  排名输出的重复性诊断，不是感知准确性。
- 历史和当前的 baseline↔reset 内部比较本身也出现了非精确的 native 状态；
  其中 turn 历史运行的最大 float 差已为 `54.5426`。这说明“最终计划可重复”
  与“完整中间状态可重复”是两个不同的合同。

该诊断支持“低分检测的排名对换放大了按行直比的差异”这一窄事实，但不能从
现有数据判定触发源，也不能证明所有中间差异对任务都无害。触发机制记为
`down-weighted`，不归因于 CUDA、PyTorch、SparseDrive 某个模块或具体资产。

## 裁决和可用边界

| 主张或诊断 | 裁决 | 范围 |
|---|---|---|
| 冻结输入、资产、receiver 和环境身份通过 | `accepted` | 同机器、两窗口 |
| 96 张当前 RGB 与历史 golden 相同 | `accepted` | 逐字节，无新现实性证据 |
| 最终 plan 和 mode/command 发布回归 | `accepted` | 32 时序帧，最大 plan 差 `2.003e-5 m` |
| 已有 `D_domain` 的数值复现 | `accepted` | 16 行，其中 10 行历史完整；不升级域等效主张 |
| 完整 native 状态在阈值内复现 | `rejected` | float 最大差 `66.6675`，22 个 integer mismatch |
| 排名对换与其余 native 差异的触发机制 | `down-weighted` | outcome-informed；只完成定位，没有因果隔离 |
| 整体 segment | `down-weighted` | 任务端窄回归通过，完整 native 主门失败，且不是新 real–sim 实验 |

实际上，本次实验把“能有效使用仿真”进一步分成了具体合同：

- 用于这两段场景上的**冻结 SparseDrive 最终规划回归**，现有证据在 `1e-4 m`
  阈值内支持有限使用。
- 用于**完整感知／运动中间状态的精确发布回归**，本次合同不通过。
- 用于**仿真现实性、感知准确性或 AD 正确性**，本实验没有提供新证据。

这正是 NuRec 类验证需要分层的原因：输入一致、任务输出一致和内部状态一致
可以得到不同裁决，不能用最终轨迹的稳定性代替对中间机制的检查。

## 产物

```text
artifacts/fixed_trajectory_receiver_regression_001/
  inputs/straight-current-run002/
  inputs/turn-current-run002/
  receiver/straight-current-run002/
  receiver/turn-current-run002/
  receiver_regression.json
  native_difference_diagnostic_plan.md
  native_difference_diagnostic.json
```

主比较的逐帧数据见
[`receiver_regression.json`](../../artifacts/fixed_trajectory_receiver_regression_001/receiver_regression.json)；
outcome-informed 定位见
[`native_difference_diagnostic.json`](../../artifacts/fixed_trajectory_receiver_regression_001/native_difference_diagnostic.json)。
机器可读裁决见
[fixed_trajectory_receiver_regression_001.json](fixed_trajectory_receiver_regression_001.json)。
