# 冻结轨迹 SparseDrive 接收方回归 001：预注册

2026-10-11。本实验借鉴 NVIDIA／理想 NuRec 的下游接收方和运行一致性检查，
在已冻结的两段 scene-0383 轨迹上回答一个有限问题：

> 当当前 HUGSIM RGB 与历史 golden 逐字节相同时，同一个冻结
> SparseDrive 接收方能否在独立 reset 后复现历史原生输出，并复现已报告的
> 真实—仿真计划差异？

它是一个发布回归和运行复现性实验。因为真实 RGB 和接收方都没有新增，
通过不会增加新的真实—仿真等效证据，也不证明 SparseDrive 规划正确。

## 冻结输入和运行合同

- 上游输入：`fixed_trajectory_render_regression_001/run002`；该轮是预注册的
  完整轮次，96/96 RGB 与历史 golden 逐字节一致。
- `straight`：帧 `12,18,24,30,36,42,48,54`。
- `turn`：帧 `60,66,72,78,84,90,96,102`。
- 两个窗口分别启动 SparseDrive，不把它们拼成一段 16 帧历史。
- 每个窗口执行一次 baseline 和一次独立 reset repeat，共
  `2 × 8 × 2 = 32` 个帧前向接收。
- SparseDrive commit、已记录 working diff、adapter、config、checkpoint、
  四个 anchor、校准 `infos.pkl`、source metadata 及 archive manifest 全部以
  SHA-256 冻结在
  [`configs/fixed_trajectory_receiver_regression_001.json`](../../configs/fixed_trajectory_receiver_regression_001.json)。
- 运行 Python 固定为
  `/home/yawei/miniforge3/envs/sparse4d-audit/bin/python`；比较器要求本仓库工作区干净。
- 新输出必须写入全新目录，不覆盖历史运行。

## 执行

先用已有的无损装配器分别生成两个接收方输入窗口：

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/assemble_hugsim_exact_pose_window.py \
  --metadata artifacts/hugsim_source_anchor/scene-0383-official-sample-metadata-run001/meta_data_init.json \
  --render 12=artifacts/fixed_trajectory_render_regression_001/run002/renders/straight/frame_00012 \
  --render 18=artifacts/fixed_trajectory_render_regression_001/run002/renders/straight/frame_00018 \
  --render 24=artifacts/fixed_trajectory_render_regression_001/run002/renders/straight/frame_00024 \
  --render 30=artifacts/fixed_trajectory_render_regression_001/run002/renders/straight/frame_00030 \
  --render 36=artifacts/fixed_trajectory_render_regression_001/run002/renders/straight/frame_00036 \
  --render 42=artifacts/fixed_trajectory_render_regression_001/run002/renders/straight/frame_00042 \
  --render 48=artifacts/fixed_trajectory_render_regression_001/run002/renders/straight/frame_00048 \
  --render 54=artifacts/fixed_trajectory_render_regression_001/run002/renders/straight/frame_00054 \
  --variant factual \
  --output artifacts/fixed_trajectory_receiver_regression_001/inputs/straight-current-run002
```

`turn` 使用同一命令形式，将帧和渲染目录替换为
`60,66,72,78,84,90,96,102` 及 `renders/turn/frame_XXXXX`，输出为
`inputs/turn-current-run002`。

然后对每个窗口各执行一次：

```bash
PYTHONPATH=artifacts/sparsedrive_receiver/runtime-deps-v1 \
MPLCONFIGDIR=/tmp/mpl-sparsedrive-receiver-regression \
/home/yawei/miniforge3/envs/sparse4d-audit/bin/python \
  scripts/run_sparsedrive_real_source.py \
  --sparsedrive-root /home/yawei/SparseDrive \
  --checkpoint artifacts/sparsedrive_receiver/official-v1.0/sparsedrive_stage2.pth \
  --runtime-deps artifacts/sparsedrive_receiver/runtime-deps-v1 \
  --anchor-dir artifacts/sparsedrive_receiver/official-v1.0/anchors \
  --source-root <CURRENT_INPUT_ROOT> \
  --metadata <CURRENT_INPUT_ROOT>/metadata_exact_pose_window.json \
  --source-archive-manifest <CURRENT_INPUT_ROOT>/assembled_render_manifest.json \
  --metadata-archive-manifest artifacts/hugsim_source_anchor/scene-0383-official-sample-metadata-run001/source_archive_manifest.json \
  --calibration-reference-run artifacts/hugsim_contrast/scene-0383-easy-00-run007-9s \
  --frame-index <F1> --frame-index <F2> --frame-index <F3> --frame-index <F4> \
  --frame-index <F5> --frame-index <F6> --frame-index <F7> --frame-index <F8> \
  --baseline-only \
  --output <CURRENT_RECEIVER_ROOT>
```

最后执行冻结比较器：

```bash
/home/yawei/miniforge3/envs/sparse4d-audit/bin/python \
  scripts/compare_fixed_trajectory_receiver_regression.py \
  --config configs/fixed_trajectory_receiver_regression_001.json \
  --output artifacts/fixed_trajectory_receiver_regression_001/receiver_regression.json
```

## 预注册通过门

只有以下条件全部成立，才把“冻结接收方发布回归”记为有限
`accepted`：

1. 装配的 96/96 张唯一 RGB 与 run002 源文件、历史 golden 均逐字节相同。
2. 当前和历史接收方的 model、source commit/diff、adapter、calibration、
   ego/command/reference 合同完全一致；除图像路径外，32/32 个帧的输入合同一致。
3. 新的两组 baseline/reset repeat 全部有限、非退化，各自的计划最大差不超过
   `1e-4 m`。
4. 历史—当前的 32/32 个时序帧所选 command/mode 相同，全部最终
   `6 × 2` 计划坐标最大绝对差不超过 `1e-4 m`。
5. 两个 `native_outputs.pt` 的结构、容器类型、array/tensor dtype 和 shape 一致；
   整数、布尔和其他标量精确一致；所有浮点有限，全局最大绝对差不超过
   `1e-4`。`.pt` 文件本身的 SHA-256 不作为数值通过门。
6. 用冻结的真实输入报告重算 16 行 `D_domain`，其中 10 行具有四帧完整历史；
   ADE、FDE、最终横向／纵向差和 real/sim mode 均复现历史 audit，数值差不超过
   `1e-4 m`。

任一健康门、身份门或数值门失败，对应的完整回归主张记为 `rejected`；
保留已完成的窄事实。如果 RGB 仍精确一致而接收方不复现，只能定位为接收方／运行时
复现性回归；在没有额外证据时不归因到具体 CUDA、PyTorch、SparseDrive 模块或资产。

## 证据边界

即使全部通过，整体 segment 仍为 `down-weighted`：它只覆盖同机器、同场景、
两个窗口和一个接收方，且真实端输出没有重跑。它可以说明历史 matched
real–sim 结果在当前冻结链路上仍可数值复现，不能把原有的实际等效证据升级。
