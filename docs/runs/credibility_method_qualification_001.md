# 可信验证方法资格审计 001

日期：2026-09-01

方法合同：`CREDIBILITY_VALIDATION_METHOD.md`

机器记录：`docs/runs/credibility_method_qualification_001.json`

## 1. 审计目的

本轮不重新评价 HUGSIM，也不修改任何历史实验裁决。它把仓库中已经冻结的
窄正对照、已知负例和模糊案例组成一个回溯 challenge set，检查第一版方法是否
能够：

1. 发现已知测量、时域和状态链错误；
2. 接受有限正证据而不越界；
3. 把“产生响应”与“响应方向/幅度可信”分开；
4. 保留像素、任务、控制和闭环层之间的矛盾；
5. 在没有外部任务边界时拒绝宣布现实等效。

这些案例不是独立随机样本，也参与过方法形成，因此本轮不计算 sensitivity、
specificity 或准确率。它只能完成回溯逻辑资格和已知失效机制辨识；后续仍需
冻结规则后的前瞻案例。

## 2. 冻结 challenge set

### 2.1 窄正对照：方法不能全部误杀

| ID | 既有事实 | 方法应保留的结论 | 回溯结果 |
|---|---|---|---|
| `P1-CF-M` | 三档恒速共 `108` 个 transition；最大积分残差分别为 `5.46e-9`、`1.09e-8`、`1.64e-8 m`，低于 `1e-5 m` 门；运动顺序 `36/36`、间距/净距顺序各 `37/37` 成立 | 接受脚本恒速状态的内部积分和顺序；不升级为真实车辆动力学 | 正确分离：窄主张 `accepted`，整体 `down-weighted` |
| `P2-CF-O` | 修正坐标符号后，run001/run002 RGB 与 ego 状态最大差均为 `0`；明显遮挡端点 `37/37` 方向成立，`0` 反转、`0` 缺测 | 接受明显端点几何/RGB 支撑方向；不声称连续遮挡或真实传感器一致 | 正确分离：两项窄主张 `accepted`，整体 `down-weighted` |
| `P3-ORDINAL` | 四条独立几何关系在 `26/26` 有效时刻成立；Sparse4Dv3 可用比较均无反转，其中两条 `13/13` 完整，另两条各缺 `1/13` | 接受完整序数关系；缺测关系降权且不插补 | 正确分离：两条 `accepted`、两条 `down-weighted`，完整可用主张 `rejected` |

### 2.2 已知负例：方法必须 fail closed

| ID | 已定位问题 | 关键观测 | 方法回溯结果 |
|---|---|---|---|
| `N1-PROJECTION` | 遮挡分析器把 box 高度坐标符号解释反了 | actor 实际造成每帧 `1,641–3,883` 个 RGB 差分像素，但错误投影掩码在 `37/37` 帧与其零交集 | 投影测量链和 RGB 主张 `rejected`；分析器错误诊断单独 `accepted`；没有误判为 HUGSIM 遮挡能力失败 |
| `N2-HORIZON` | 6 s 运行尾窗缺少完整 actor 未来并重复末状态 | 有效时域只到 `3.5 s`；首次 TTC/NC 失败在 `4.75/5.75 s`；扩展 9 s 后相同前缀和相同帧通过 | 旧动态风险主张 `rejected`；尾窗填充诊断 `accepted` |
| `N3-ACTUATION` | 动作框合格不能替代状态转换资格 | 六个 bounded runs 均完成 `18/18` step 且 applied action 在边界内；但 near−below 进度为 `-0.352757/-0.520462 m`，near 末速为 `-0.270178/-0.337445 m/s` | 接口机械执行 `accepted`；响应顺序及“动作合格蕴含状态合格” `rejected` |

### 2.3 模糊和跨层案例：方法不能压成单一成败

| ID | 表面现象 | 必须分开的判断 | 方法回溯结果 |
|---|---|---|---|
| `A1-FACTUAL` | fully warmed real–sim 计划 ADE `0.358 m`、端点差 `0.639 m`，远超 paired repeat `9.54e-6 m` | 域差可测；没有 `ε_task` 时不能宣布等效或不等效；像素相似不能代替任务输出 | 域差测量 `accepted`；等效主张 `down-weighted`；像素推出任务等效 `rejected` |
| `A2-RESPONSE` | strong−weak 前进效应中位数 `-1.484 m`，远超 repeat `0.000204 m`，但预期方向仅 `3/5` 成立 | “接收方有显著响应”与“方向规律成立”必须分别裁决 | 响应可分辨 `accepted`；无条件前进单调规律 `rejected`；现实幅度 `down-weighted` |
| `A3-MANEUVER` | frame 48 的 `+1.249 m` 反转由 fixed-mode `-0.366 m` 与 selection `+1.615 m` 组成；frame 54 模式不变且六模式均反转 `+0.046…+0.228 m` | 模式选择混杂与同模式局部反转不能混为同一机制，也不能事后重判原 `3/5` | 分解工具 `accepted`；路线前进指标 `down-weighted`；原始单调结论继续 `rejected` |
| `A4-PIXEL-TASK` | native dynamic 造成 factual–static plan ADE `0.094668–0.094669 m`，repeat 仅 `8.04e-7 m`；但 real–factual ADE `0.081572–0.081573 m` 大于 real–static `0.062376 m` | 像素贡献到达 AD 不等于让任务输出更接近现实；static 也不是合格 actor-absence control | “产生 AD 响应” `accepted`；“更接近真实”和“像素支撑足够” `rejected`；整体 `down-weighted` |

## 3. 方法资格结果

| 资格维度 | 挑战案例覆盖 | 结果 | 说明 |
|---|---|---|---|
| 已知错误敏感性 | `N1–N3` | `accepted` | 能在坐标、时域和动作→状态三种机制上 fail closed，并保留独立诊断 |
| 有限正对照识别 | `P1–P3` | `accepted` | 没有把内部正证据全部误杀，也没有把它升级为现实真值 |
| 层间与构念区分 | `A2–A4` | `accepted` | 能同时保存 response-positive / direction-negative、pixel-positive / task-negative 和 interface-positive / state-negative |
| 缺测与模糊保留 | `P3, A1, A3` | `accepted` | 不插补缺失，不以平均分掩盖反转，不事后重写原裁决 |
| 局部稳定性处理 | `P2, N3, A1–A4` | `down-weighted` | 能比较同管线 repeat envelope；尚无跨场景统计抽样和合格 `Θ` |
| 外部等效性校准 | `A1, A4` | `rejected`（强主张） | 已有部分 factual anchor，但没有来源独立的任务允许误差和现实后果边界 |
| 前瞻泛化资格 | 无 held-out challenge | `rejected`（强主张） | 当前 challenge set 为回溯选择，不能证明方法能覆盖未知失效机制 |

整体方法资格：`down-weighted`。

这个结果不是“方法不好”，而是准确限定它当前能做什么：方法已经能组织证据、
发现已知错误并拒绝错误的强结论，因此可以指导下一项实验；但它还不能自行证明
某个仿真器在现实 AD 测试中有效。

## 4. 当前可执行的裁决逻辑

对任一条件化主张 `C`，只检查它声明为必要的证据向量：

```text
E(C) = (G, F, Q, U, O)

G: 身份、时域、干预、测量、接收方和状态传播 gate
F: matched factual real–sim 域差/等效性
Q: 反事实干预与接收方响应
U: 重复、参数、渲染和接收方不确定性
O: 规划、控制或闭环后果
```

裁决为非补偿式：

```text
任一必要项 rejected          -> 该主张 rejected
所有必要项 accepted          -> 该主张 accepted
没有 rejected、但存在降权项  -> 该主张 down-weighted
```

没有测试必要项时，按 `not_tested` 或 `scope_exceeds_evidence` 拒绝该范围主张，
不能当作“暂未发现问题”。`D_domain`、`E_CF`、repeat error 和闭环结果分别报告，
不合成总分。

## 5. 现在能支持与不能支持什么

### 能支持

- 第一版方法对现有已知坐标、时域、控制/状态和指标构念问题具有回溯辨识能力；
- 它能接受窄内部正证据，同时限制其来源和适用范围；
- 它能处理“实验有价值但主张被拒绝”的情况；
- 它可以作为后续 HUGSIM 高信息量实验的预注册裁决骨架。

### 不能支持

- 不能给出 HUGSIM 或其他仿真器的无条件可信总分；
- 不能把当前 challenge set 的通过率解释成统计 sensitivity/specificity；
- 不能用一个 fully warmed factual 时刻定义通用 `ε_task`；
- 不能证明 SparseDrive 正确、闭环响应幅度符合现实或 AD 安全；
- 不能证明该方法已经覆盖未来未知的仿真失效机制。

## 6. 下一门槛

在新闭环实验之前，应由目标任务决定一个最小外部边界：例如“什么程度的关键
目标排序或规划差异会改变目标 AD 的动作”。先冻结 `ε_task` 或一个可辩护的
序数/决策边界，再选择一项新的、未参与本轮规则形成的前瞻 challenge。车辆模型
和 HUGSIM step 适配器仅在该前瞻实验需要闭环状态传播时再资格化。

本轮没有运行新场景、没有增加接收方、没有修改历史阈值或历史裁决。
