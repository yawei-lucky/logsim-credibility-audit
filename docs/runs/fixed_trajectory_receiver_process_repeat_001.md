# SparseDrive 全新进程重复诊断 001

2026-10-11。**在冻结资产和已记录运行字段下，最终规划再次稳定复现；完整
native 状态再次未达到预注册精度。结果支持“当前全新进程之间也存在内部输出
非精确复现”，但没有定位触发组件。整体为 `down-weighted`。**

这是
[冻结轨迹 SparseDrive 接收方回归 001](fixed_trajectory_receiver_regression_001.md)
失败后的 outcome-informed 诊断。它按照
[执行前说明](fixed_trajectory_receiver_process_repeat_preregistration_001.md)新增一组
`straight-current-run003` 和 `turn-current-run003`，与已完成的 run002 比较。
它不能改变历史—当前主比较中完整 native 主张的 `rejected` 裁决。

## 执行资格

预注册在 commit `9e61dcbd476d0589ac23238347079d390ab1e5b0` 提交并推送后执行。

- 两个 GPU 子任务都返回 0，共新增 32 个 frame forward。
- 执行时本仓库干净，GPU／driver 为
  `NVIDIA GeForce RTX 4090 D / 580.95.05`。
- 每个窗口执行前后，48 张图像、manifest、metadata 和全部冻结哈希均不变；
  合计覆盖 96 张唯一 RGB。
- SparseDrive commit/status、checkpoint、config、adapter、helper、anchors、校准和
  58 文件 runtime-deps 树均通过冻结门。
- 执行清单记录了实际命令、三个关键环境字段、日志和输出哈希；run003 使用新的
  输出目录，没有覆盖既有成功运行。

这些事实足以资格化本次**已记录合同内**的进程重复比较。系统库、cuDNN、进程
调度和全部环境变量没有完整冻结，因此不支持“全部运行环境完全相同”或跨平台
确定性主张。

## 预注册主结果

| 检查 | straight | turn | 总体裁决 |
|---|---:|---:|---|
| run002↔run003 时序帧 mode/command 相同 | 16/16 | 16/16 | `accepted` |
| final plan 最大绝对差 | `2.098e-5 m` | `1.526e-5 m` | `accepted`，低于 `1e-4 m` |
| run003 baseline↔reset plan 最大差 | `1.240e-5 m` | `1.431e-5 m` | `accepted`，低于 `1e-4 m` |
| native 结构、dtype、shape 和有限性 | 通过 | 通过 | `accepted` 的窄事实 |
| native float 最大绝对差 | `46.8773` | `66.6675` | `rejected` |
| native integer mismatch | 8/16,016 | 16/16,016 | `rejected` |

32/32 个时序帧的输入合同在预注册的 path-normalized 规则下相同，实际输入图像
又逐张通过冻结哈希；全部 selected mode 和 command 相同。最终规划最大差为
`2.09808349609375e-5 m`，run003 自身 reset repeat 最大差为
`1.430511474609375e-5 m`，均通过冻结的 `1e-4 m` 门。

完整 native 比较则有 1,457,317/2,007,312 个浮点元素不是 bit-exact，最大差
`66.66753768920898`，最坏字段为 `trajs_3d`。24/32,032 个整数位置不同。因此
完整 native 的 `1e-4` 浮点门和整数精确门均失败，主比较器按预注册返回
`all_checks_passed=false`。

## 只读定位

预注册允许的 ID 对齐和前 10 detection 定位没有替代失败门：

- 18 个 instance-ID 排名位置不一致，并伴随 6 个 label 位置变化，合计正好
  对应 24 个整数 mismatch；最早在 rank 80，相关 score 不超过 `0.021525`。
- 按相同 instance ID 对齐后，ID/label mismatch 归零；`boxes_3d` 最大差降为
  `6.356e-4`，`trajs_3d` 最大差仍为 `0.05235`，继续超过原 `1e-4` 门。
- 两个窗口前 10 detection 共 320 个，label 320/320 相同；最大 score 差
  `4.268e-5`，最大 box 分量差 `2.641e-4`。它们没有真值匹配，只是排名输出
  的重复性诊断。

这排除了“只有历史 release drift 才造成 native 差异”这一单独解释：同一当前
代码、同一冻结资产和相同 RGB 的新进程之间也观察到同型失败。它没有排除未完整
记录的 runtime 状态，也不能归因到 CUDA、PyTorch、SparseDrive 或具体算子。

## 裁决与仿真用途

| 主张 | 裁决 | 可用范围 |
|---|---|---|
| 冻结资产与已记录执行合同通过 | `accepted` | 本机、两窗口、执行清单所列字段 |
| 全新进程的 mode/command 与最终 plan 复现 | `accepted` | 32 时序帧，plan 最大差 `2.098e-5 m` |
| 全新进程的完整 native 状态复现 | `rejected` | float 最大差 `66.6675`，24 个 integer mismatch |
| native 差异触发机制 | `down-weighted` | 低分排名位置变化只解释部分表现，组件未隔离 |
| 整体 segment | `down-weighted` | 运行一致性诊断；没有新增 real–sim 现实性证据 |

因此，这组证据支持把当前链路用于两个冻结窗口上的**最终规划容差回归**；不支持
把完整感知／运动中间状态当作逐元素确定的 golden，也不支持仿真现实性、感知
准确性或 AD 正确性。后续若任务依赖中间检测或轨迹，应为具体字段建立任务容许
误差和匹配规则，不能沿用 final-plan 的通过结果。

## 产物

```text
artifacts/fixed_trajectory_receiver_regression_001/
  process_repeat_execution_manifest.json
  process_repeat_001.json
  process_repeat_001_logs/
  receiver/straight-current-run003/
  receiver/turn-current-run003/
```

逐帧比较见
[`process_repeat_001.json`](../../artifacts/fixed_trajectory_receiver_regression_001/process_repeat_001.json)，
执行身份和前后快照见
[`process_repeat_execution_manifest.json`](../../artifacts/fixed_trajectory_receiver_regression_001/process_repeat_execution_manifest.json)。
