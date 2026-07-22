# HUGSIM CF-M 001 恒速运动形变实验结果

## 结论

CF-M 001 按提交 `93217332f64f8d6d3fd5b5c2e229e46521bb70ff` 中的预注册
执行完成。slow、nominal、fast 三组均完成 36/36 step，运行配置、HUGSIM 版本、
ego 状态/动作/计划和 plan-writer 契约通过 fail-closed 配对检查。

两个预声明的窄主张均为 `accepted`：

1. HUGSIM 保存的 ConstantPlanner actor 状态满足声明恒速的向量积分、速度、
   heading 和零加速度关系；
2. 在当前同向 lead-actor 设计中，三档速度产生预期的累计位移、相对前向间距和
   footprint 净距顺序，未出现反转或并列。

整体 segment 仍为 `down-weighted`：这验证的是一个脚本化恒速控制器在 HUGSIM
保存状态中的内部运动机制，不是一般车辆动力学、真实交通行为或 AD 响应。

## 输入与产物

运行：

```text
artifacts/hugsim_motion_metamorphic/scene-0383-motion-slow-001-run001
artifacts/hugsim_motion_metamorphic/scene-0383-motion-nominal-001-run001
artifacts/hugsim_motion_metamorphic/scene-0383-motion-fast-001-run001
```

分析：

```text
artifacts/hugsim_motion_metamorphic/analysis-run001/motion_metamorphic_audit.json
artifacts/hugsim_motion_metamorphic/analysis-run001/motion_indicator_summary.png
artifacts/hugsim_motion_metamorphic/analysis-run001/motion_cam_front_contact_sheet.png
artifacts/hugsim_motion_metamorphic/analysis-run001/motion_cam_front_comparison.mp4
```

## 硬约束结果

每组有 36 个相邻状态 transition，共 108 个。预注册位置积分容差为 `1e-5 m`。

| 条件 | 声明速度 | 最大向量积分残差 | 最大速度误差 | 最大 heading 变化 | 最大加速度残差 | 裁决 |
|---|---:|---:|---:|---:|---:|---|
| slow | 0.5 m/s | 5.46e-9 m | 0 | 0 | 0 | `accepted` |
| nominal | 1.0 m/s | 1.09e-8 m | 0 | 0 | 0 | `accepted` |
| fast | 1.5 m/s | 1.64e-8 m | 0 | 0 | 0 | `accepted` |

残差约为容差的千分之一，未发现瞬移、错误方向、速度漂移或 heading 跳变。人工
构造的瞬移、反向等速运动和 slow/fast 顺序交换均被单元测试识别，说明这些指标
至少能捕获预定义反例；这不代表已覆盖所有运动错误。

## 条件单调结果

| 预声明关系 | 匹配时刻 | 成立 | 反转/并列 | 最小相邻间隔 | 裁决 |
|---|---:|---:|---:|---:|---|
| fast travel > nominal > slow | 36 | 36 | 0 | 0.125 m | `accepted` |
| fast forward gap > nominal > slow | 37 | 37 | 0 | 0.125 m | `accepted` |
| fast clearance > nominal > slow | 37 | 37 | 0 | 0.125 m | `accepted` |

末帧 `t=9.0 s` 的差异已经明显：

| 条件 | 从首条记录累计运动 | ego-frame 前向间距 | footprint 净距 |
|---|---:|---:|---:|
| slow | 4.50 m | 5.12 m | 1.83 m |
| nominal | 9.00 m | 9.74 m | 6.45 m |
| fast | 13.50 m | 14.37 m | 11.08 m |

这里“fast 更远、更大净距”成立，是因为 actor 与 ego 同向行驶且 ego 轨迹固定；
它不能被一般化为“车辆速度越快越安全”。真正受检验的是声明前提下的相对运动
方向。

## 可视化如何阅读

`motion_indicator_summary.png` 中：

- 左上三条直线分别以 0.5/1.0/1.5 m/s 增长；
- 右上有限差分速度保持在三条声明水平线上；
- 左下 slower actor 被 ego 更快追近，fast actor 保留更大前向间距；
- 右下向量积分残差约为 `1e-8 m`，远低于 `1e-5 m` 容差。

CAM_FRONT 对比图和视频显示同一现象：首帧只有 reset 提前一次更新造成的小差异；
到末帧 slow 车辆明显更近，nominal 居中，fast 更远。画面只用于理解状态后果，
不参与硬约束裁决。

## 这次实验对研究的推动

这次首次把“运动规律”落实成了可运行的指标组合：硬规律用残差和违反次数，条件
单调规律用成立数、反转数和最小间隔。指标不是从结果曲线反推，而是在运行前
固定，并且能对已知负例发出信号。

因此可以接受：该方法能够审计 HUGSIM 当前恒速机制的内部一致性。仍不能接受：
HUGSIM 已具备真实车辆动力学、真实交互行为、传感器现实性或 AD 测试域可信性。
下一种互补失效机制应转向 CF-O 可控遮挡，而不是继续增加速度档位。
