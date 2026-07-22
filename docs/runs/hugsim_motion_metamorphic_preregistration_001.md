# HUGSIM CF-M 001 恒速运动形变实验预注册

> 状态：`preregistered_not_run`。本文件及配套 JSON 必须先提交，再启动仿真。

## 目的与边界

验证 CF-M 第一部分：当同一车辆只改变恒定速度时，HUGSIM 保存的 actor 状态是否
满足恒速积分、连续运动和预声明的相对运动方向；同时检查这些指标能否识别人为
构造的瞬移和顺序反转。

HUGSIM 当前 `ConstantPlanner` 只提供恒速直线更新。本实验不验证一般加速度、
车辆动力学、真实驾驶行为、感知接收方或闭环安全。

## 三个条件

所有条件固定 `scene-0383`、车辆资产、纵向起点 18 m、横向位置 0 m、yaw 0、
ego 初始条件、确定性 plan writer 和 36 个仿真 step。唯一计划内差异是 actor
速度：

| 条件 | 速度 | 配置 | 输出 |
|---|---:|---|---|
| slow | 0.5 m/s | `configs/hugsim/scenarios/scene-0383-motion-slow-001.yaml` | `artifacts/hugsim_motion_metamorphic/scene-0383-motion-slow-001-run001` |
| nominal | 1.0 m/s | `configs/hugsim/scenarios/scene-0383-motion-nominal-001.yaml` | `artifacts/hugsim_motion_metamorphic/scene-0383-motion-nominal-001-run001` |
| fast | 1.5 m/s | `configs/hugsim/scenarios/scene-0383-motion-fast-001.yaml` | `artifacts/hugsim_motion_metamorphic/scene-0383-motion-fast-001-run001` |

由于 HUGSIM reset 会在首条记录前先更新一次 actor，所有运动残差以记录到的
`t=0` 状态为锚点，不假设它等于 YAML 初始位置。

## 预声明指标和反例

### 硬约束：恒速状态演化

对每个相邻记录计算：

- 位移向量与 `v*dt` 沿 actor heading 预测位移之间的位置积分残差；
- 有限差分速度误差；
- heading 变化；
- 有限差分加速度残差；
- actor 数量和时间戳连续性。

容差仅吸收浮点保存误差：位置 `1e-5 m`、速度 `1e-5 m/s`、heading
`1e-5 rad`、加速度 `1e-4 m/s²`。任一有效 transition 超出容差，就把
“恒速状态按声明演化”的具体主张裁决为 `rejected`。

### 条件单调关系：同向 lead actor 的相对运动

在 ego 状态、路线、actor 起点和外形严格配对的前提下，所有记录时刻预期：

```text
fast actor forward gap > nominal actor forward gap > slow actor forward gap
fast ego-footprint clearance > nominal clearance > slow clearance
```

从首条记录之后，累计运动距离预期：

```text
fast travel > nominal travel > slow travel
```

报告成立次数、反转/并列次数和最小相邻间隔；任何无混杂反转或并列都会拒绝该
方向主张。这里比较的是受控同向相对运动，不把“actor 速度更快”一般化为普遍
风险规律。

### 指标负例

单元测试固定两个人工反例：

1. 在恒速序列中加入一次 1 m 瞬移，硬约束必须失败；
2. 让 actor 以正确速率反向移动，向量积分约束必须失败；
3. 交换 slow/fast 序列，顺序指标必须报告反转。

这只证明分析器能识别预定义违反模式，不证明其覆盖所有运动错误。

## 独立性与允许主张

指标不用 HUGSIM NC/TTC/PDMS，而是从保存的时间戳和 box 重新计算，因此具有
计算独立性；box 和时间仍由 HUGSIM 产生，不是独立现实状态。

若硬约束和单调关系全部通过，允许接受两个窄主张：

1. 三个声明恒速条件在保存状态中满足预定义的离散运动关系；
2. 在当前场景、控制器和速度范围内，速度干预产生预期相对运动方向。

整体证据仍为 `down-weighted`，不得升级为真实车辆动力学、现实风险、接收方
响应、AD 安全、real–sim 等效或一般 HUGSIM 可信性。

## 执行与产物

每个条件运行：

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python scripts/run_hugsim_case.py \
  --scenario <condition-config> \
  --output <condition-output> \
  --max-steps 36
```

分析：

```bash
MPLCONFIGDIR=/tmp/matplotlib-codex \
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/analyze_hugsim_motion_metamorphic.py \
  --preregistration docs/runs/hugsim_motion_metamorphic_preregistration_001.json \
  --preregistration-commit <commit> \
  --output artifacts/hugsim_motion_metamorphic/analysis-run001
```

预定产物为机器可读审计 JSON、四联指标图、CAM_FRONT 首/中/末帧对比图和三条件
同步视频。分析前不根据画面调整速度、容差或预期方向。

分析器必须 fail closed 地核对：当前脚本与提交中脚本的哈希、提交中的预注册和
三份配置、每个运行实际记录的 scenario 哈希与路径、36/36 step、干净的审计仓库
状态，以及 plan writer 的 horizon、step、响应数量和完成握手。
