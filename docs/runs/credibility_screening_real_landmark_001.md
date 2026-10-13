# 真实图片路灯杆位置筛查

日期：2026 年 10 月 13 日。整体裁决：`down-weighted`。

本轮新增三个真实 CAM_FRONT 图片成员，并生成九张 HUGSIM 图像。发布版配置的
三帧杆身位置候选区间均与冻结的真实图参考相交；主动偏转相机视角的三帧均被
粗位置判题排除。样本初始相机记录的三帧也与参考区间分离，暴露了位姿记录
选择与坐标配对需要核对的问题。**这是图片候选参考诊断，尚不是物理标定或
严格真实等效验证。**

## 新真实窗口与题目修订

看新图片前，固定选择此前真实清单最大帧号 102 之后的三个步长六时刻：108、
114、120，约 9.000521、9.500945、10.000825 s，800×450。三个成员来自已有
官方样本 ZIP，每张 CRC、长度、SHA-256 和完整解码均通过。新提取 JPEG 共
360,558 字节；完整归档哈希仍只有提供方声明，不写成我们已计算验证。

三张原图没有可辨认车辆，原定车辆位置题保持未测。未继续搜索同场景窗口以
凑车辆正样本；保留该选择，并在新渲染前把本题收窄为同一根灰色金属路灯杆
的粗水平位置。此修订和原选样结果均保留于[预注册](credibility_screening_real_landmark_preregistration_001.md)
及[原选样记录](../../artifacts/credibility_screening_real_vehicle_001/selection_run001/selection.json)。

这是同场景新窗口，不是新场景或已证明的重建训练留出。此前清点的 144 张
不同真实成员增加为 147 张；新增的只有前相机，完整六相机时刻仍为 24 个。

![三张实际道路采集的预处理图片 没有可辨认车辆](../../artifacts/credibility_screening_real_landmark_001/annotation_evaluation_run001/real_window_overview.png)

## 冻结参考与实际控制

[真实图参考](../../configs/credibility_real_landmark_reference_001.json)、
[配置](../../configs/credibility_screening_real_landmark_001.json)和代码在 GPU 前
冻结于 Git `b5cd375fa88c9de58f6dd94af039ccdf2f7639de`；执行时工作区干净。
HUGSIM commit 为 `adeca402cad4af8635e13d0a105e2fee6a14de85`。

观察量为像素行 `[200,240)` 内杆身可见外轮廓的水平中点，不是最暗竖条或三维
位置。两份只看真实 RGB 的 Codex 候选读数先取保守包络，形成事前参考区间。
它们共享图像来源，没有人类真值资格，也没有校准过的统计误差界。

每个时刻仅渲染前相机，保留静态重建和全部原生动态状态，执行三个条件：

- `released`：发布 checkpoint 附带的相机记录。
- `source_init`：官方样本初始相机记录；用于诊断记录选择，不称严格物理同位姿。
- `wrong_yaw`：在发布版记录基础上将前相机局部 Y 轴旋转 -5°。平移、内参、
  时刻和动态姿态不变。它是主动错误视角对照，不是 HUGSIM 自发缺陷。

本轮没有向场景添加人工标靶或修改 HUGSIM 渲染器。单相机调用仍先核验完整
六相机元数据组，默认六相机流程保留。三次 GPU 帧处理均完成，共九张新 RGB。

## 候选位置比较

九张新图由 root 读图，并额外打乱成匿名图片交给不知道条件名、帧号、真实
参考坐标的 Codex 读者复核。全部可辨认同一类灰色杆身观察量，两份候选区间
均有交叠；最终使用保守包络，不选择更容易通过的一份。此盲复核减少了按
期望填读数的风险，但不增加独立现实证据，也不替代人类或标定资格。

| 帧 | 真实参考区间（px） | 发布版候选区间 | 初始记录候选区间 | 错视角候选区间 |
|---|---|---|---|---|
| 108 | [104,114] | [103,113] | [140,151] | [171,182] |
| 114 | [199,210] | [197,208] | [234,245] | [255,267] |
| 120 | [304,315] | [302,313] | [344,357] | [359,373] |

固定判题不添加额外容差：区间相交仅表示此粗参考未排除该输入，保持
`down-weighted`；严格分离则拒绝“该候选位置与参考相容”的主张，并保留
`tested=true / annotation_interval_conflict`。

发布版三帧均相交。错视角三个区间与参考的最小间隔为 **57、45、44 px**；
初始记录的最小间隔为 **26、24、29 px**。这些是候选区间之间的距离，不是
实际相机误差、精确位置残差或驾驶安全门。root、盲读和最终包络分别判题，
九张图的相交／分离结论一致，报告复用不算额外测试样本。

![黄色为冻结真实图区间 蓝色为图像候选读数](../../artifacts/credibility_screening_real_landmark_001/annotation_evaluation_run001/landmark_position_comparison.png)

判题器只处理附有可查图像的候选标注，没有自动识别自然杆身。未知、无法确认
或未经资格的缺失读数保留未测；缺图、错时间、哈希错误与位置矛盾分开。
七项区间／完整性检查和九项单相机渲染接口检查通过。

## 裁决与未解决问题

三个真实成员的提取完整性，以及区间判题的实现行为为 `accepted`。发布版
粗位置相容和候选图片参考诊断为 `down-weighted`。初始记录与错视角的候选
区间相容主张为 `rejected`，均连接单独诊断，不自动升级为 HUGSIM 组件缺陷。
各项主张、拒绝上下文、读数和产物哈希见[机器记录](credibility_screening_real_landmark_001.json)。

Source Availability Gate 仍未通过：原 nuScenes 身份、ASAP 转换、发布配对、
原校准及训练留出仍不完整。初始与发布记录还具有坐标系统依赖，不能把两份
数值位姿直接相减认作实际相机误差。已有源侧 mask 也没有被替代为真值。
因此，这次看到的初始记录冲突只能要求审计记录选择和坐标转换，不能定位
物理相机、重建或渲染哪个组件失效。

本轮仍缺独立人类／传感器标注资格、自然车辆正样本和任务容许误差。没有
检验 AD、深度或闭环结果，也没有证明区间相交者具有现实正确性。
下一步先核对相机记录及坐标转换、复核真实参考的标注资格，再决定车辆题
所需样本；暂不扩展更多同场景图片或更换 NuRec。

## 复现与保存

完整渲染命令见预注册，每次使用新输出路径。候选读数已经记录，按固定参考
重算其中一个条件如下：

```bash
/home/yawei/HUGSIM/.pixi/envs/default/bin/python \
  scripts/evaluate_landmark_interval_screening.py \
  --reference configs/credibility_real_landmark_reference_001.json \
  --submission artifacts/credibility_screening_real_landmark_001/annotation_evaluation_run001/hull_released_submission.json \
  --output artifacts/credibility_screening_real_landmark_001/NEW_EVALUATION
```

`credibility_screening_real_landmark_001/` 下保存前置资格、GPU 运行、匿名复核图、
root／盲读／包络标注、逐条件报告及结果图。原选样和无车辆资格结果另存于
`credibility_screening_real_vehicle_001/selection_run001`；真实成员及 CRC／哈希
清单位于 `hugsim_source_anchor/scene-0383-basic-real-vehicle-window-run001`。
所有路径均在 `artifacts/` 下，没有覆盖旧成功运行。
