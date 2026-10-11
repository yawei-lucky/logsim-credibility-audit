# HUGSIM 冻结轨迹渲染回归 001 预注册

2026-10-11。用户要求参考 NVIDIA／理想 NuRec 的验证做法继续实际实验。本轮执行
固定轨迹重渲染和运行一致性回归，复用已有 matched factual 窗口，不增加场景、
动态 actor 或 AD。

## 要回答的问题

在场景、相机、逐帧位姿、时间、原生动态对象和 checkpoint 都保持相同时：

1. 当前渲染管线的两个新运行是否产生相同 RGB？
2. 当前管线是否仍产生与历史 golden 完全相同的 RGB？
3. 每个冻结帧启动一个新进程时，初始化与六相机输出是否完整？

这是 renderer/pipeline regression，不是重建质量、真实—仿真图像等效或 AD 行为
验证。当前 HUGSIM commit 与场景资产未变化，只有仓库中的渲染 driver 哈希从历史
`f6198035…` 变为 `c72a4e9c…`；因此即使全部一致，也只能接受“所选窗口没有因
当前管线改动产生 RGB 回归”，不能称为跨 HUGSIM release 验证。

## 冻结输入

精确路径和帧号见[配置](../../configs/fixed_trajectory_render_regression_001.json)。

| 窗口 | 帧 | 相机 | 历史 golden |
|---|---|---:|---|
| `straight` | 12, 18, 24, 30, 36, 42, 48, 54 | 6 | `scene-0383-source-window-factual-run002` |
| `turn` | 60, 66, 72, 78, 84, 90, 96, 102 | 6 | `scene-0383-source-turn-window-factual-run001` |

每轮共 16 帧 × 6 相机 = 96 张 PNG。两个完整轮次分别输出到新的 `run001` 和
`run002`，共 192 张。每一帧由单独的 Python 子进程加载 scene 和原生动态对象，
避免跨帧模型状态掩盖启动或状态泄漏问题；两轮合计 32 个 renderer 子进程。
子进程固定 `PYTHONHASHSEED=0` 和 HUGSIM driver 内已有的 Torch seed。

历史 manifest 及其 96 张 PNG 必须先通过哈希检查。历史合同固定为：

- HUGSIM `adeca402cad4af8635e13d0a105e2fee6a14de85`；
- scene checkpoint `1b42fbd9…`，config `4b4ae91e…`；
- 原生 dynamic `d793362732e547249b1a05af84d09967` checkpoint `462a1d45…`；
- metadata `55e4e4d2…`；历史 render driver `f6198035…`。

任一当前资产与历史合同不一致就停止，不能把资产变化混入 driver 回归。
预检还须确认帧号唯一且递增、时间严格递增、每帧六相机齐全，K 有限，camera／
dynamic 变换为有效刚体矩阵，唯一原生 dynamic ID 与冻结配置一致，而且相机与
dynamic 轨迹确实变化。完成渲染后，每个窗口的每个相机至少须出现两个不同 PNG
哈希，防止常量输出误通过重复性检查。

## 比较与裁决

先比较 PNG SHA-256，再解码逐像素比较。任一不一致时，逐图保存：最大 uint8 差、
MAE、MSE、PSNR 和 SSIM。SSIM 只定位差异，不提供现实任务阈值。
比较器必须拒绝同一目录冒充两轮，并在比较图像前确认两轮 config、代码与输入哈希、
运行环境和 16 个子进程命令合同一致。任一精确性主张失败时仍保存逐图诊断，但命令
返回非零状态，防止自动流程把回归失败当作通过。

- **当前管线跨运行重复性**：96/96 张 run-to-run PNG 字节和像素都相同，且两轮
  各 16/16 子进程成功，才能在本机冻结环境内记为 `accepted`。
- **历史 golden 回归**：两轮各 96/96 张与 golden 字节和像素都相同，才能接受
  “所选窗口当前 RGB 未回归”。任一差异都拒绝 bitwise-equivalence 具体主张，
  如实报告差异位置和幅度；没有外部 task margin 时，不把微小像素差自动写成
  驾驶相关退化。
- **启动完整性**：32/32 子进程成功并各输出六张可解码、尺寸正确的有限 uint8
  RGB，才能接受本次批量启动合同。
  失败进程保留日志和输出，不能从分母中删除后再声称完全稳定。

历史 golden 与新运行共享同一 scene、HUGSIM renderer 和本机资产；它们不是独立
现实参考。即使全部通过，整体 segment 仍为 `down-weighted`。

## 运行与留存

```bash
env CUDA_HOME=/usr/local/cuda-12.1 TORCH_CUDA_ARCH_LIST=8.9 \
  PATH=/usr/local/cuda-12.1/bin:$PATH \
  /home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/run_fixed_trajectory_render_regression.py \
  --config configs/fixed_trajectory_render_regression_001.json \
  --output artifacts/fixed_trajectory_render_regression_001/run001
```

第二轮只改为 `run002`。之后用冻结比较脚本生成
`comparison_run001_run002.json`。每个输出目录必须不存在；失败运行原样保留，
不得覆盖。保存环境、输入和代码哈希、golden 资格、每个子进程命令/日志/状态、
每张 PNG 和完整比较结果。

`prev_viewpoint=None` 且每帧重新载入场景，所以本实验只检查固定姿态、无历史的
RGB 回归；不检查时间历史、光流或跨帧 renderer 状态。拼图包含日期和绝对路径，
不进入一致性裁决。
