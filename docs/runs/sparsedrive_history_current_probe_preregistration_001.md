# 历史与当前 RGB 来源交叉诊断 001：预注册

2026-10-30。用户在讨论新实验后明确授权“你做吧”。本轮只推进短窗口配对
核验及四组历史／当前交换，不自动恢复缺帧／陈旧输入实验，不扩闭环或新 AD。
顶层仍为预测结构、动作效应及任务边界一致性；本轮提供预测结构的接收方诊断。

## 问题和限定

已有真实与仿真输入的规划差异，可能由当前图像、历史输入造成的接收方状态、
以及二者的相互作用共同形成。只有 RR／SS 不能区分这些解释。本轮固定接收方、
逻辑时刻、相机合同、位姿、派生状态、规划命令及采样顺序，仅改变 RGB 来源。
不要求接收方仅有四帧记忆，也不把注入的混合来源序列称为物理相机记录。

选样在新模型结果前固定为既有 `straight` 窗口
`12,18,24,30,36,42,48,54`，不按新输出筛选窗口。前七帧为前缀，末帧 54
为唯一主终点。复用已归档的真实成员和 HUGSIM 图片，不重新渲染、不改变背景。
每组两个从重置开始的完整序列，每组一个新模型进程，共 64 次 frame forward。

| 组 | 前七帧 | 当前帧 54 |
|---|---|---|
| RR | 真实 R | 真实 R |
| RS | 真实 R | 仿真 S |
| SR | 仿真 S | 真实 R |
| SS | 仿真 S | 仿真 S |

没有直接移植缓存；沿用已冻结 adapter 的重置和逐帧处理，以免遗漏缓存字段。
参数、代码、数据和四组运行顺序 RR／RS／SR／SS 均由配置及其依赖哈希固定。

运行前的资产检查发现旧回归配置中的渲染 helper 哈希已过期。核对 Git `b5cd375`
确认修改为可选单相机接口；本轮 adapter 使用的六相机默认和记录数值未改变。
旧配置保持不改，新配置显式冻结当前三个 helper 的哈希及 runtime-deps 文件树。
这项前置发现发生在新模型结果之前；不把文件哈希不同默认为运行行为等价。

## 已完成的输入资格及未通过的来源门

资格记录：`artifacts/sparsedrive_history_current_probe_001/qualification_run001/qualification.json`。
配置：`configs/sparsedrive_history_current_probe_001.json`。

- 48 张真实 JPEG 的 SHA-256、提供方 ZIP 成员 CRC／长度及完整解码一致；
  48 张已有仿真 PNG 的哈希、生成报告、逐帧来源 metadata 及原生动态保留检查通过。
- 48 组声明记录除图片路径外完全相同，六相机共享声明时刻；192 个输入链接
  逐一绑定正确来源。所有 arm 使用同一份原始 metadata，不把旧 PNG 重新编码成 JPEG。
- 对齐两份记录的首帧前相机 gauge 后，所选 48 个相机记录的初始／优化位姿
  最大平移差约 0.763265 m，最大旋转差约 0.377373°。这是记录差，不是测得的
  物理相机误差；没有根据新图拟合修正，也没有据此选用另一批图片。
- 原 nuScenes 身份、完整原标定／CAN、checkpoint 训练划分及初始位姿与优化
  重建坐标的物理对应仍未获得独立资格。完整归档 SHA 仍是提供方声明。

来源门保持 `down-weighted`，不作严格真实—仿真同位姿、准确性或现实等效裁决。
本轮可裁决的是**已绑定的两种 RGB 输入及其历史怎样改变固定接收方规划**。

## 事前数值判据

输出 `Y_hc` 为当前帧原生 `final_planning` 的完整六个二维 waypoint，单位 m。
保留每个 replicate，不先把离散模式混为一类；模式和命令独立列出。

单输出数值 guard `epsilon = 1e-4 m` 继承既有最终规划回归容差，不是驾驶任务
容许误差。它只支持在本机、固定版本和观测重置范围内区分数值响应。

归因资格要求：

1. 64 个输入合同只允许图片路径不同；每张实际交付图片的哈希与绑定来源相同。
2. 每组全部原生输出有限、最终计划不退化，两个重置序列的规划最大绝对差
   不超过 epsilon。
3. 同一历史来源的四条前缀，两两最终规划差在所有七时刻不超过 epsilon。
   不要求完整 native 中间量逐元素复现；其旧失败裁决保留。

若资格失败，保留结果但不作超重复误差的历史／当前归因，不增跑直到通过。
接口／资源失败允许新目录重试，必须保留原失败记录，不改实验判据。

对每个 arm 逐坐标建立 `[两次结果最小值-epsilon, 两次结果最大值+epsilon]`。
对正负系数分别传播上下界；该包络是有限重复加数值 guard，**不是统计置信区间**，
不保证覆盖未测随机性。任何坐标包络严格不含零，才称该对比在本合同内数值可分。
两项差至少传播 2 epsilon，四项交互至少传播 4 epsilon，不拿原单输出门直接
裁决四项残差。全部六步均报告，不只挑最大一步或改主终点。

冻结对比：

- 当前影响：`Y_RS - Y_RR`、`Y_SS - Y_SR`。
- 历史影响：`Y_SR - Y_RR`、`Y_SS - Y_RS`。
- 全来源差：`Y_SS - Y_RR`。
- 交互：`I = Y_SS - Y_SR - Y_RS + Y_RR`。

竞争解释：

| 候选 | 可被何种结果排除 |
|---|---|
| 输出仅由当前来源解释 | 任一同当前、不同历史的对比合格且数值可分 |
| 输出仅由历史来源解释 | 任一同历史、不同当前的对比合格且数值可分 |
| 来源效应可按历史项加当前项解释 | 交互 I 合格且数值可分 |

未被排除只表示本分辨率下仍相容，不证明候选正确。没有预注册哪一个候选必须
失败，没有从以往单项结果保证交互必非零。若模式改变，保持上述坐标恒等式
评分并标明混合了模式选择影响；不自动归因到某个感知或记忆子模块。

## 验证与命令

新增六项资格检查使用人工可解的加性、交互、效应抵消、重复跨零及四项预算
反例，不使用待测 SparseDrive 输出建立期望。已有 adapter 与依赖不修改。

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python -m unittest tests.test_sparsedrive_history_current_probe
/home/yawei/HUGSIM/.pixi/envs/default/bin/python scripts/run_sparsedrive_history_current_probe.py prepare --config configs/sparsedrive_history_current_probe_001.json
/home/yawei/miniforge3/envs/sparse4d-audit/bin/python scripts/run_sparsedrive_history_current_probe.py run --config configs/sparsedrive_history_current_probe_001.json
/home/yawei/miniforge3/envs/sparse4d-audit/bin/python scripts/run_sparsedrive_history_current_probe.py analyze --config configs/sparsedrive_history_current_probe_001.json
```

prepare 已运行；其哈希已加入冻结配置。不要覆盖已有输出。复现实验需在新配置
中指定新的输出目录，重新准备并冻结资格记录。GPU run 要求干净且已提交的仓库，
每组子进程单独留日志、15 分钟超时与状态清单，失败立即终止。

分析重新读取 native tensor、JSON 和所有交付图片，验证相互绑定。证据同时归档
数值对比、候选裁决、重复及前缀控制、计划图和命令；tested rejection 连接独立诊断。

## 禁止扩张的主张

无外部任务容许误差，不由数值可分推出危险或不可信；未恢复“正确规划”的判题。
混合输入不是路上可直接采集的来源切换，效应可能包含这种切换的作用。
本轮不能裁决物理延迟、自动发现完备机制、HUGSIM 原生动力学、闭环结果、
真实安全性或跨场景适用性。即使所有数值资格通过，整体仍为 `down-weighted`。
