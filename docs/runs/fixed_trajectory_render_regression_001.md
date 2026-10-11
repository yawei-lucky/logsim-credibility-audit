# HUGSIM 冻结轨迹渲染回归 001

2026-10-11。**96 张冻结轨迹 RGB 的历史兼容性和两个完整成功轮次之间的重复性
均为逐字节、逐像素完全一致；预注册的进程启动完整性主张因一次早期
`SIGSEGV` 被 `rejected`，整体仍为 `down-weighted`。**

本实验采用 NVIDIA／理想 NuRec 验证中的固定轨迹重放、golden regression 和
运行一致性思路。它检查当前管线是否稳定地产生既有 RGB，不检查这些 RGB 是否
更接近现实，也不建立真实—仿真、AD 任务或跨硬件等效。

## 冻结设计与输入资格

[预注册](fixed_trajectory_render_regression_preregistration_001.md)及执行程序在提交
`8b22fcf97a369daf1a1a23f7b16648b51ad28ccf` 冻结，之后未修改代码、配置或阈值。

- 场景：scene-0383；HUGSIM
  `adeca402cad4af8635e13d0a105e2fee6a14de85`。
- 直行／转弯入口窗口：帧 `12,18,24,30,36,42,48,54`。
- 持续转弯窗口：帧 `60,66,72,78,84,90,96,102`。
- 每帧六相机，每轮 `16 × 6 = 96` 张 PNG；每帧启动一个全新、顺序执行的
  Python 进程，不复用已载入的 Torch/HUGSIM 状态。
- scene、config、原生动态对象、metadata、相机集合、内参、位姿、时间戳和
  dynamic ID 均在渲染前通过冻结门；每个子进程报告再次核对这些身份。
- 两个 historical golden manifest 分别包含 48 张图，SHA-256 为
  `d73786ba…` 和 `f3803f60…`；96 张 PNG 和 16 个历史报告全部通过哈希复核。

历史 golden 使用 renderer driver `f6198035…`，当前 driver 为 `c72a4e9c…`；
HUGSIM commit、scene/config、原生动态 checkpoint 和 source-pose metadata 不变。
因此新旧比较是**历史管线兼容性**，不是两个 HUGSIM release 的独立比较。

运行环境固定为同一主机、NVIDIA GeForce RTX 4090 D、driver `580.95.05`、
PyTorch `2.4.1+cu121`、CUDA `12.1`、gsplat `1.2.0`、NumPy `1.26.4` 和
imageio `2.37.0`。run002 与 run003 的比较器还验证了 config、代码和输入哈希、
去除启动时间后的环境合同、golden/trajectory preflight 以及 16 个规范化子进程
命令完全相同。

## 预注册两轮的执行结果

| 轮次 | 身份 | 完成进程 | RGB | 结果 |
|---|---|---:|---:|---|
| `run001` | 预注册第一轮 | 15/16 | 90/96 | frame 66 子进程 `SIGSEGV` |
| `run002` | 预注册第二轮 | 16/16 | 96/96 | 完成 |

`run001` 的 `turn/frame66` 子进程在启动后 `0.214 s` 以 return code `-11`
退出，未超时，也没有生成渲染报告或六相机输出。日志文件为 0 字节。根据 driver
执行顺序，只能把位置限定在创建本帧输出目录和载入 scene checkpoint 之前的早期
进程路径；Python／原生扩展导入、HUGSIM 导入和 metadata 准备等仍未区分。

其余 31 个预注册子进程完成。因此：

- 预注册的 `32/32` 启动完整性主张为 `rejected`；
- `run001 ↔ run002` 全 96 图重复性主张为 `rejected`，因为必需的 6 张图缺失；
- 两轮各 96 张均与 golden 一致的完整主张也为 `rejected`。

缺失图像没有被伪记为像素 mismatch，但也没有从分母中删除。`run001` 已产生的
90/90 张图均与 run002 对应图、历史 golden 的 PNG 字节和解码像素完全一致，
逐图诊断见
[`partial_comparison_run001_run002.json`](../../artifacts/fixed_trajectory_render_regression_001/partial_comparison_run001_run002.json)。
`run002` 的 96/96 张均与 golden 完全一致。

## 故障后留存的诊断轮次

在执行前写入并留存
[`diagnostic_run003_plan.md`](../../artifacts/fixed_trajectory_render_regression_001/diagnostic_run003_plan.md)，
SHA-256 为 `b5c7dd5e…`。其中明确规定 run003 不能替代 run001，也不能恢复原
`32/32` 主张。该说明早于 run003，但位于被 Git 忽略的产物目录且没有绑定进
run003 环境哈希，因此只作为 outcome-informed 诊断说明，不作为独立预注册。
run003 沿用相同提交、配置、环境和 16 个独立子进程，结果为
`16/16` 完成、`96/96` RGB 齐全；frame 66 在 run002、run003 中分别约
`4.48 s`、`4.52 s` 正常完成。

冻结比较器对 run002 与 run003 的结果为：

| 比较 | PNG 字节一致 | 解码像素一致 | 最大 uint8 差 | 最大 MAE | 最小 SSIM |
|---|---:|---:|---:|---:|---:|
| run002 ↔ run003 | 96/96 | 96/96 | 0 | 0 | 1.0 |
| run002 ↔ historical golden | 96/96 | 96/96 | 0 | 0 | 1.0 |
| run003 ↔ historical golden | 96/96 | 96/96 | 0 | 0 | 1.0 |

完整逐图记录见
[`comparison_run002_run003.json`](../../artifacts/fixed_trajectory_render_regression_001/comparison_run002_run003.json)。
它支持一个有限的 `accepted` 诊断：在这台机器和冻结的 96 图输入集合内，两个
成功完成的当前轮次未出现 RGB 输出不确定性，当前输出也没有相对 historical
golden 发生字节或像素回归。

![进程健康与 RGB 精确回归结果](../../artifacts/fixed_trajectory_render_regression_001/fixed_trajectory_render_regression_summary.png)

## 启动故障的证据边界

三轮共 48 个全新进程，47 个完成；所有实际产生的 282 张 RGB 均与相应 golden
完全一致。这个计数不能用来估计一般失败率，也不能把 run003 当成对 run001 的
静默重试。

`-11` 只确认该进程收到 `SIGSEGV`。本次没有 Python traceback；core limit 为
0，未保留 core/backtrace；可访问的 journal 窗口也没有给出组件位置。因此故障
机制只记为 `down-weighted`：不能归因于 HUGSIM、PyTorch、CUDA、NVIDIA 驱动、
gsplat、显存或 frame 66 数据。相同 frame 之后两次成功，且输出与 golden 完全
一致，不支持确定性的 frame 66 输入缺陷或持续性 RGB 回归。
上述只读检查的原始输出已保存为
[`failure_diagnostics.txt`](../../artifacts/fixed_trajectory_render_regression_001/run001/failure_diagnostics.txt)。

## 裁决

| 主张或诊断 | 裁决 | 范围与理由 |
|---|---|---|
| 冻结输入、资产和 golden 身份通过资格门 | `accepted` | 16 帧、96 图；当前资产与历史合同哈希一致 |
| 预注册 32/32 子进程均正常完成 | `rejected` | 实际 31/32；一个子进程 return code `-11` |
| 预注册 run001 ↔ run002 全 96 图精确重复 | `rejected` | run001 缺 6 张；不是观测到像素差异 |
| 两个预注册轮次各 96/96 与 golden 精确一致 | `rejected` | run001 只有 90/96；完整主张未通过健康门 |
| run001 已产生图像与 run002/golden 一致 | `accepted` | 90/90 PNG 字节及解码像素一致 |
| run002 ↔ outcome-informed run003 精确重复 | `accepted` | 96/96；最大像素差 0，严格合同相同 |
| run002、run003 与 historical golden 兼容 | `accepted` | 两轮各 96/96；限定本机、该场景和管线版本 |
| 单次早期 `SIGSEGV` 的具体触发机制 | `down-weighted` | 事件已确认，组件和原因未隔离 |
| 整体 segment | `down-weighted` | 有强的有限 RGB 回归证据，但预注册启动合同失败且参考仍同源 |

这些结果没有测量 reconstruction fidelity、真实图像误差、时间历史、光流、跨帧
renderer 状态、跨 GPU/驱动稳定性或 AD 输出。成功的 RGB identity 说明旧的
SparseDrive matched real–sim 结果没有被**当前 RGB 文件变化**解释；receiver
runtime 是否仍能复现，仍须由独立 reset 重跑检查。

## 产物

```text
artifacts/fixed_trajectory_render_regression_001/
  run001/                          # 原样保留的预注册失败轮次
  run002/                          # 完整预注册轮次
  run003/                          # 故障后冻结的完整诊断轮次
  diagnostic_run003_plan.md
  partial_comparison_run001_run002.json
  comparison_run002_run003.json
  fixed_trajectory_render_regression_summary.png
```

机器可读裁决见
[fixed_trajectory_render_regression_001.json](fixed_trajectory_render_regression_001.json)。
