# 基础可信性筛查：遮挡后标靶身份 001

日期：2026 年 10 月 12 日。整体裁决：`down-weighted`。

新增的 HUGSIM 实验已执行：两种背景下，六个正常图对正确保留可见标靶身份；
四个主动换错编码的图对虽然数量、可见位置正确，却被身份门拒绝。
**本轮补上“只数剩几个、不认剩下谁”的测试盲区，没有发现 HUGSIM 自身身份缺陷。**

## 固定条件与独立读数

[预注册](credibility_screening_identity_preregistration_001.md)、
[配置](../../configs/credibility_screening_identity_001.json)和读数代码在新渲染前冻结于
Git `051d108412d0fc59cfdd5a032c2f8ff8b616a5a9`；执行时工作区干净。
HUGSIM commit 为 `adeca402cad4af8635e13d0a105e2fee6a14de85`。
本轮没有改动 HUGSIM 渲染器、下载新真实图片或运行 AD。

继续使用 CAM_FRONT、800×450，两个标靶相机坐标为
`(0.7, -0.65, 23.5)`、`(2.3, -0.65, 23.5)` m。身份是预先规定的 RGB
差分编码：`left` 仅红通道变化，`right` 仅蓝通道变化。它们是身份名称，
不是按当前画面左右位置猜出来的标签；互换编码后，右侧点也可以读为 `left`。

读数遍历整幅 RGB 差分图，只依据连通分量的通道质量比例读身份，不读取规定
位置、渲染 semantic、depth 或提交方声称的身份。正确通道比例门为 **0.85**；
不明确或未知编码保留 `identity=null`、`tested=false`、
`measurement_unqualified`，不能冒充已测物理错误。
随后才按独立投影检查身份对应位置：每坐标 **0.25 px**；双靶完整间距预算
**0.5 px**。单靶必须保留完整间距 `null`，不补出被遮挡端点。

独立 CPU 资格直接指定二维中心、红蓝编码、相位、尺寸、背景及有限通道混合，
不使用 HUGSIM。288/288 图对身份正确，最大位置误差 **0.039720 px**，最大
宽度误差 0.076887 px，最低正确通道比例 0.936389。模糊红蓝、未知绿色和
边界截断三项对照均阻断。GPU 前重复同一资格得到相同记录，不算额外覆盖。
这是有限人工标靶网格的仪器资格，不是任意通道混合、自然目标或真实相机误差界。

## 新 HUGSIM 遮挡结果

遮挡体位于目标前方 2 m、沿同一相机射线，sigma 0.45 m、opacity 0.9999。
目标 opacity 始终为 0.9；没有通过关闭目标来替代遮挡。八个遮挡条件的独立
射线对齐误差均为 `5.684e-14 px`，深度前后关系正确，标靶 opacity 未改变。
“不可见”指低于本合同差分测量门，不宣称 Gaussian 完全没有透射或验证了
自然实体的所有遮挡行为。

两背景各产生五个图对，共 **10 图对、20 张 RGB**。每个提交含三个必测 case；
错误对照只替换对应遮挡 case，其他图像不变。多个报告复用这些图像，不重复
计为新实验样本。

| 背景 | 条件 | 期望身份 | 实测身份 | 可见点位置最大误差（px） | 身份判定 |
|---|---|---|---|---:|---|
| 孤立 | 两靶可见 | left、right | left、right | 0.034957 | `accepted` |
| 孤立 | 遮左靶 | right | right | 0.033123 | `accepted` |
| 孤立 | 遮右靶 | left | left | 0.012214 | `accepted` |
| 孤立 | 遮左靶、换错编码 | right | left | 0.033123 | `rejected`，已测身份矛盾 |
| 孤立 | 遮右靶、换错编码 | left | right | 0.012214 | `rejected`，已测身份矛盾 |
| scene-0383 静态 | 两靶可见 | left、right | left、right | 0.044980 | `accepted` |
| scene-0383 静态 | 遮左靶 | right | right | 0.045153 | `accepted` |
| scene-0383 静态 | 遮右靶 | left | left | 0.014771 | `accepted` |
| scene-0383 静态 | 遮左靶、换错编码 | right | left | 0.034405 | `rejected`，已测身份矛盾 |
| scene-0383 静态 | 遮右靶、换错编码 | left | right | 0.010957 | `rejected`，已测身份矛盾 |

表中位置误差不带身份，刻意与身份错误分开。四个错误图对都在位置预算内，
也都通过旧数量／间距门；新门均以 `tested=true / contradiction` 拒绝。
没有把缺文件或身份无法测量算成检出。最低 HUGSIM 实测正确编码通道比例
0.893634，仍高于事先固定的 0.85；没有根据结果降低比例门或放宽位置预算。

按实际下达的编码身份重评，十图对全部通过身份及其对应位置，最大位置误差
**0.045153 px**。全部八个单靶图对的完整间距均为 `null`。
这些对照资格化测试器，不能算四种 HUGSIM 缺陷或总体错误检出率。

![绿叉及文字来自 RGB 实测；右两列可见数量与位置正确，但编码身份错误](../../artifacts/credibility_screening_identity_001/hugsim_run001/identity_screening.png)

## 裁决与剩余范围

有限编码读数资格、此次正常遮挡后的编码身份／位置，以及指定身份错误的检出
为 `accepted`。“数量和不带身份位置足以证明剩余身份”为 `rejected`，有独立
诊断相连。整体仍为 `down-weighted`：只覆盖一个相机、一个位置、两种背景、
两种人工编码和规定 Gaussian 遮挡，不证明普通车辆身份、部分遮挡、真实相机
或智驾任务等效。具体主张、拒绝上下文及哈希见[机器记录](credibility_screening_identity_001.json)。

十三项相关实现检查通过，其中双靶编码互换位置也被身份对应位置门拒绝，模糊
和未知身份不补造读数。旧种子 11 用例／35 图对及上一题六图对的判定、测量
与 RGB 哈希保持一致，没有为新题修改旧裁决。

下一题先确定一个自然车辆位置或可见性问题的独立参考和误差界，再按冻结规则
选取一个此前未用于测试集开发的真实短窗口；该项尚未执行。同场景新窗口
不等于独立场景或重建训练留出。

## 复现与产物

在仓库目录、现有 HUGSIM 环境和 approved GPU-visible context 中运行；每次
使用新的输出路径：

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/run_credibility_screening_identity.py \
  --config configs/credibility_screening_identity_001.json \
  --output artifacts/credibility_screening_identity_001/NEW_RUN
```

同一命令添加 `--qualify-only` 只执行 CPU 前置资格。
现有成功目录均位于 `artifacts/credibility_screening_identity_001/`：

- `qualification_run001`：冻结前独立 CPU 资格及环境。
- `hugsim_run001`：新 RGB、资格、遮挡几何、完整提交、正常／实际编码／旧数量
  三种报告、运行健康、哈希和结果图。
- `legacy_compatibility_run001`：旧种子和绝对位置题的兼容重评。

没有覆盖既有成功运行；没有将历史通过数、新渲染数和报告复用次数相加评分。
