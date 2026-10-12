# 基础可信性筛查：绝对投影位置 001

日期：2026 年 10 月 12 日。整体裁决：`down-weighted`。

已执行一个新的 HUGSIM 标靶位置，在孤立背景与 scene-0383 静态背景中各渲染
正常、整体横移、整体纵移，共六图对、十二张 RGB。正确位置通过；四个主动
错移图对都通过旧间距门，却被新增绝对位置门拒绝。**本轮补上测试集盲区，
没有发现 HUGSIM 自身把标靶放错。**

## 固定条件与独立判题

[预注册](credibility_screening_position_preregistration_001.md)与
[配置](../../configs/credibility_screening_position_001.json)在新 HUGSIM 输出产生前，
冻结于 Git `bfe721356e4f6d11076d346285ee2e15e8f1811a`；GPU 执行时工作区干净。
相机为 CAM_FRONT、800×450，端点相机坐标为 `(0.7, -0.65, 23.5)`、
`(2.3, -0.65, 23.5)` m。实际 HUGSIM commit 为
`adeca402cad4af8635e13d0a105e2fee6a14de85`。

独立 CPU 针孔投影给出两个端点的横、纵位置；测量只读取明暗 RGB 差分质心。
像素中心为列／行索引加 0.5，未拟合坐标补偿。位置按图像从左到右对应，
没有验证语义身份。新位置预算事先定为每端点每坐标 0.25 px，由本轮二维图
资格支持；不是自动搬用旧宽度预算，也不是现实相机或驾驶安全容许误差。

CPU 资格采用直接指定的二维中心、横纵亚像素相位、三种标靶尺寸及两种背景：
288/288 图对可测，最大位置误差 **0.033649 px**，最大宽度误差 0.066327 px。
GPU 运行前重复同一资格检查，结果相同；没有把重复计算当额外覆盖。

## 新 HUGSIM 结果

两种错误输入均保持端点深度、间距与相机不变：共同横移 +0.75 m，或共同纵移
+0.50 m。仍按正常位置判题；这相当于提交“间距正确、位置错误”的输入。

| 背景 | 提交条件 | 间距残差（px） | 最大位置误差（px） | 新位置判定 |
|---|---|---:|---:|---|
| 孤立 | 正常 | 0.008554 | 0.021930 | `accepted` |
| 孤立 | 共同横移 | −0.018169 | 20.243620 | `rejected`，已测矛盾 |
| 孤立 | 共同纵移 | 0.031128 | 13.457556 | `rejected`，已测矛盾 |
| scene-0383 静态 | 正常 | 0.014389 | 0.018821 | `accepted` |
| scene-0383 静态 | 共同横移 | −0.017711 | 20.244212 | `rejected`，已测矛盾 |
| scene-0383 静态 | 共同纵移 | 0.039932 | 13.470899 | `rejected`，已测矛盾 |

全部六图对都通过旧宽度门：间距残差绝对值最大 0.039932 px，低于 0.5 px。
新位置门接受两个正常图对，拒绝四个错移图对，拒绝原因均为
`tested=true / contradiction`，没有把缺图或测量失败算成位置检出。

再按实际下达的端点坐标检查，六图对全部符合 0.25 px，最大误差
**0.035426 px**，相机—世界坐标往返也通过 `1e-5 m` 门。它们证明渲染符合
实际命令，主动构造的错移只用于资格化测试器。

![绿加号为规定位置，红叉为 RGB 实测；共同错移保持间距但改变绝对位置](../../artifacts/credibility_screening_position_001/hugsim_run001/position_screening.png)

## 裁决与剩余范围

有限二维位置测量、此次新标靶投影与指定错移检出为 `accepted`。
“间距通过足以证明位置正确”为 `rejected`，与独立诊断记录相连。
窄合同通过不能证明一般智驾测试适用性或真实 AD 等效，整体仍为 `down-weighted`。
具体主张、拒绝上下文、诊断和产物哈希见[机器记录](credibility_screening_position_001.json)。

本轮只验证一个位置、一种小型 Gaussian 标靶、一个相机和两个背景。没有测试
普通车辆轮廓、遮挡后身份、真实相机、AD 输出或闭环结果，也没有新增真实数据。
四个错移对照不是四种 HUGSIM 缺陷，不构成总体错误检出率的抽样分母。

旧种子兼容检查保留 11/11 用例、35/35 图对的原判定，宽度、残差和 RGB 哈希
完全一致；九项相关单元检查通过。没有为通过新题而放宽预算或修改渲染器。
下一题考虑遮挡后剩余标靶身份，尚未执行。

## 复现与产物

在仓库目录、现有 HUGSIM 环境和 approved GPU-visible context 中运行；必须
选择新的输出路径：

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/run_credibility_screening_position.py \
  --config configs/credibility_screening_position_001.json \
  --output artifacts/credibility_screening_position_001/NEW_RUN
```

已有成功目录：

- `qualification_run001`：GPU 前的独立 CPU 资格。
- `hugsim_run001`：新 RGB、逐条件正常／实际状态／旧宽度三种报告、环境、哈希和汇总。
- `legacy_compatibility_run001`：旧 11 用例的兼容重评。

以上目录都位于 `artifacts/credibility_screening_position_001/`，没有覆盖旧实验。
