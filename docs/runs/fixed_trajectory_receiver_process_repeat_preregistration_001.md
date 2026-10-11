# SparseDrive 全新进程重复诊断 001：执行前说明

2026-10-11。这是 outcome-informed 诊断：它在
`fixed_trajectory_receiver_regression_001` 的完整 native 主张已失败后设计。它不能
修改原 `1e-4` 阈值、替换历史—当前主比较，或追溯恢复已被 `rejected`
的完整 native 复现主张。

它只回答：

> 对完全相同的 96 张已装配 RGB，在冻结代码与模型资产且保持已记录运行字段
> 一致的情况下，另一组全新进程是否仍会出现“最终计划稳定，
> 完整 native 状态不精确”？

## 冻结设计

- 左侧：已完成的 `straight-current-run002` 和 `turn-current-run002`。
- 右侧：全新目录 `straight-current-run003` 和 `turn-current-run003`。
- 两个窗口仍分别加载模型，各执行 baseline 和 independent reset repeat，新增
  32 个 frame forward。
- 输入根目录、metadata、manifest、八个帧号和命令与 run002 完全相同，
  只改变输出目录。
- 主配置、主比较结果、run002 报告／native、主 native 诊断、诊断 helper、
  新比较器和运行器哈希冻结在
  [`configs/fixed_trajectory_receiver_process_repeat_001.json`](../../configs/fixed_trajectory_receiver_process_repeat_001.json)。
- 运行器在每个窗口前后重算 48 张输入图像、manifest、metadata、SparseDrive
  状态和 runtime-deps 文件树；并记录实际命令、关键环境字段、GPU／driver、
  日志与输出哈希。`PYTHONDONTWRITEBYTECODE=1` 防止依赖缓存因执行本身变化。
- 比较时本仓库必须干净；新输出不得覆盖。

GPU 执行入口冻结为：

```bash
/home/yawei/miniforge3/envs/sparse4d-audit/bin/python \
  scripts/run_fixed_trajectory_receiver_process_repeat.py \
  --config configs/fixed_trajectory_receiver_process_repeat_001.json \
  --manifest artifacts/fixed_trajectory_receiver_regression_001/process_repeat_execution_manifest.json
```

运行器生成的两个 receiver 命令沿用主实验的全部输入参数。straight 使用帧
`12,18,24,30,36,42,48,54`，turn 使用帧
`60,66,72,78,84,90,96,102`；只有输出目录改为对应的 `run003`。

比较命令为：

```bash
/home/yawei/miniforge3/envs/sparse4d-audit/bin/python \
  scripts/compare_fixed_trajectory_receiver_process_repeat.py \
  --config configs/fixed_trajectory_receiver_process_repeat_001.json \
  --output artifacts/fixed_trajectory_receiver_regression_001/process_repeat_001.json
```

## 冻结门和解释

1. 32/32 个时序帧的全部输入图像、输入合同、mode 和 command 必须一致。
2. final plan 和新 run003 的 reset repeat 最大绝对差均不超过 `1e-4 m`。
3. 完整 native 结构、dtype 和 shape 要求一致；浮点全部有限且最大差不超过
   `1e-4`；整数、布尔和其他标量要求精确相同。
4. exact instance-ID 对齐和前 10 detection 比较只作定位，不作为替代通过门。

如果 current↔current 的完整 native 门仍失败，它支持“无代码变化时也存在进程级
不精确复现”的窄诊断，不再把历史—当前差异单独解释为 release drift。
如果它通过，则只把历史—当前差异保留为未记录环境／时间漂移线索。两种结果都不能
定位到 CUDA、PyTorch 或 SparseDrive 具体模块，也不会改变主实验的 `rejected`
裁决。本设计没有完整冻结或记录系统库、cuDNN、进程调度及全部环境变量，因而不作
“全部运行环境完全相同”或跨平台确定性的主张。
