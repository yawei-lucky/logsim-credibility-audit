# 可信性筛查种子集资格实验 001

日期：2026 年 10 月 12 日。整体裁决：`down-weighted`。

已建立并执行第一版 CPU 筛查：11 个受控用例、35 个 RGB 图像对重新测量，
以及九个故障对照。另核验了一个真实场景的两个窗口，共 96 张不同真实图片。
本轮没有执行新 HUGSIM 渲染、实车采集、AD 推理或新闭环。

## 输入与独立参考

冻结配置为 [credibility_screening_001.json](../../configs/credibility_screening_001.json)。
受控图片来自已完成的 motion_observation_probe 与 boundary 实验，选取静态
scene-0383 背景、边界实验 24 m 深度的八种条件，以及三种速度的 baseline。
本轮选择是回顾式种子整理，不能称新增独立留出。

期望由固定三维端点和 3×3 相机内参解析计算；提交侧只提供 RGB 文件和时间／
身份字段。测试器不读取旧预测、测量值或证据裁决。旧图像仅作为重新读取的
受测输入。配置冻结正常及故障输入的 SHA-256。

## 实测结果

| 检验 | 结果 | 有限含义 |
|---|---|---|
| 独立二维测量资格 | 132/132；最大宽度误差 0.047804 px < 0.5 px | 种子标靶尺寸、宽度、背景和像素相位网格可测 |
| 历史受控种子 | 11/11 用例、35/35 图对满足合同 | 33 个宽度残差最大 0.033872 px；两图对恰有一分量，不输出宽度 |
| 故障机制对照 | 7/7 出现指定用例的已测矛盾 | 隐藏距离／延迟／尺度、运动冻结、忽略遮挡／去除、共同深度错误可检出 |
| 输入完整性对照 | 2/2 正确阻断 | 缺用例和错误时间不能被计作物理机制检出 |
| 真实成员完整性 | 96/96 本地图片匹配冻结提取清单 | 一个场景、两个窗口；完整 Source Availability Gate 仍未通过 |

`seed_run001` 是首轮开发运行，全部输入被拦截，但当时故障资格只要求拒绝，
未区分拒绝原因。审查后冻结故障图像哈希，并要求机制对照必须出现预定用例的
`tested=true / contradiction`，完整性对照必须是 `input_invalid`。
`seed_run002` 满足收紧规则，为最终报告依据；首轮保留。

九种故障是测试器资格对照，不能写成九种新发现的 HUGSIM 故障，也不能计算
总体错误检出率。两个标靶共同平移仍可能通过；单分量不能证明剩余标靶的
身份或绝对位置；没有独立测量实际曝光和交付时间。没有真实任务容许误差。

窄测量、种子重评、预设故障检出与真实成员完整性为 `accepted`；真实等效、
一般可信和新增独立留出主张为 `rejected`，具体上下文见
[机器记录](credibility_screening_seed_001.json)。整体为 `down-weighted`。

## 复现命令与产物

在 `/home/yawei/logsim-credibility-audit` 使用现有 CPU 环境。既有输出不能覆盖，
重跑必须换路径。

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/run_credibility_screening_seed.py \
  --output artifacts/credibility_screening_001/seed_run002

/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/inventory_credibility_real_anchors.py \
  --output artifacts/credibility_screening_001/real_inventory_run001.json
```

主要产物：

- `artifacts/credibility_screening_001/seed_run002/summary.json`：故障类型、命令、结果。
- `artifacts/credibility_screening_001/seed_run002/baseline/report.json`：逐用例／帧的原图哈希、解析期望与重新测量。
- `artifacts/credibility_screening_001/seed_run002/measurement_qualification.json`：132 个独立二维资格图对。
- `artifacts/credibility_screening_001/seed_run002/baseline_submission.json`：可复用的提交格式实例。
- `artifacts/credibility_screening_001/real_inventory_run001.json`：96 张真实图片的逐项完整性结果与来源缺口。

测试集范围、NuRec 方法适用性和其他仿真器接入说明见
[筛查集说明](../credibility_screening_set_001.md)。
