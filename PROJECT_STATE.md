# Research Commander — LogSim Credibility Audit 状态总结

## 1. 项目定位

本项目研究 **日志驱动型反事实闭环仿真可信验证**。

研究对象不是普通 open-loop planning benchmark，也不是 motion-only simulation 或纯 CARLA 合成仿真，而是：

真实驾驶日志  
→ 可反事实修改  
→ 传感器级观测生成  
→ sensor-input E2E agent / 自动驾驶模型  
→ 输出轨迹或控制  
→ 闭环状态更新  
→ 连续 rollout  
→ 评估自动驾驶系统表现

核心问题不是“仿真器能不能生成好看的图像”，而是：

> 这些仿真器生成的闭环测试结果是否可信，是否足以支撑端到端自动驾驶模型的评估结论？

---

## 2. 当前最高优先级调整

当前第一阶段审计对象调整为：

**HUGSIM 这一类真实日志重建型闭环仿真器**

理由：

HUGSIM 是 3DGS-based、真实日志/真实数据集驱动、传感器级、闭环、代码公开的自动驾驶仿真工作。相比 OmniDreams / Cosmos，它更适合作为当前阶段的 runnable target，用来先打通 credibility audit workflow。

当前不再以 OmniDreams / Cosmos 为第一运行目标。OmniDreams 被移入 future work，作为未来生成式世界模型闭环仿真的对照对象。

当前主线是：

> 先审计 HUGSIM 的自证机制和最小可运行链路，再用 NeuroNCAP / UniSim / AdvSim / OmniDreams 作为历史脉络和横向对照。

---

## 3. 对照对象定位

以下工作作为对照对象和历史脉络：

- NeuroNCAP
- UniSim
- AdvSim
- OmniDreams
- Cosmos

它们用于回答：

- 早期日志驱动 / 反事实 / 传感器级闭环仿真如何自证可信；
- 它们使用了哪些自证指标；
- 这些指标实际证明了什么；
- 这些指标没有证明什么；
- HUGSIM 相比 NeRF / earlier log-driven simulators 是否推进了可信评估；
- OmniDreams / Cosmos 作为生成式世界模型方向，未来是否能继承或替代 HUGSIM 类审计流程。

---

## 4. 主线研究问题

当前主线问题如下：

### RQ1

HUGSIM 如何证明自己的仿真结果可信？

### RQ2

HUGSIM 的指标是在验证仿真器可信性，还是只是在验证自动驾驶模型表现？

### RQ3

HUGSIM 是否能发现低可信反事实样本、3DGS 重建 artifact、遮挡错误、深度错误、几何关系不一致、时序关系不一致？

### RQ4

NeuroNCAP / UniSim / AdvSim / OmniDreams 的自证指标，能否迁移到 HUGSIM 上？

### RQ5

是否仍然需要一个 credibility audit layer，用来判断闭环测试证据应被：

- accepted；
- down-weighted；
- rejected。

---

## 5. 当前理论判断

真实日志驱动反事实闭环仿真是必要方向，但它不是天然可信。

端到端自动驾驶 / sensor-input E2E agent 的趋势使评估问题从 motion-level planning 推进到 sensor-to-action closed-loop evaluation。

3DGS-based reconstruction simulator 比 NeRF-based simulator 更接近当前实时可运行路线，但实时渲染和视觉逼真度不等于可信闭环评估。

因此，本项目的关键判断是：

> sensor-level closed-loop evaluation 变得不可回避；  
> counterfactual simulation 使 credibility audit 变得不可回避；  
> 3DGS / NeRF / world model 都必须接受 source availability 与 relation-level consistency 审计。

---

## 6. 当前工作原则

当前阶段坚持最小化，不走太远。

不急于：

- 提出完整 verifier；
- 复现所有系统；
- 生成大而全综述；
- 一次性写完所有 simulator cards；
- 跑完整 HUGSIM benchmark；
- 重新训练所有 3DGS 场景；
- 继续推进 Cosmos / OmniDreams 大模型运行。

当前只做一件事：

> 审计 HUGSIM 的自证机制，并设计最小 smoke test 来打通 credibility audit workflow。

---

## 7. 当前文件结构

核心文件：

- `README.md`
- `PROJECT_STATE.md`
- `SOURCE_AVAILABILITY_GATE.md`
- `docs/hugsim_audit.md`
- `docs/runnable_target_selection.md`
- `docs/hugsim_smoke_test_plan.md`
- `docs/comparison_notes.md`

辅助文件：

- `docs/literature_matrix.md`
- `docs/codex_workflow.md`
- `docs/future/omnidreams_audit.md`

其中当前第一优先级是：

- `docs/hugsim_audit.md`

---

## 8. HUGSIM 审计模板

`docs/hugsim_audit.md` 应优先回答：

1. HUGSIM 的基本 pipeline 是什么？
2. 它如何从真实日志 / 真实数据集重建场景？
3. 它如何使用 3D Gaussian Splatting 表示静态背景、地面和动态 actor？
4. 它如何支持反事实或 stress-case 场景修改？
5. 它生成哪些传感器级观测？
6. 它是否支持闭环 rollout？
7. 它如何更新 ego / actor 世界状态？
8. 它支持什么类型的 sensor-input E2E agent？
9. 它使用哪些自证指标？
10. 这些指标证明了什么？
11. 这些指标没有证明什么？
12. 它相比 NeuroNCAP / UniSim / AdvSim 的推进在哪里？
13. 它仍然缺失哪些 credibility evidence？

---

## 9. 需要重点审计的可信性缺口

重点不是 photorealism，而是 task-relevant relational consistency。

需要关注：

- front / rear / left / right 是否稳定；
- same-lane / adjacent-lane / off-road 是否正确；
- approaching / receding 是否可信；
- occluding / occluded-by 是否一致；
- actor scale / orientation 是否稳定；
- extrapolated views 是否出现 lane / drivable area artifact；
- risk-increasing / risk-decreasing 是否由传感器、几何、地图、时序证据支持；
- collision / near-miss 是模型真实失败，还是仿真 artifact；
- 高风险关系是否有足够证据支撑。

---

## 10. 长期工作流

不依赖单个超长聊天窗口。

推荐结构：

ChatGPT Project / Custom GPT  
+ `PROJECT_STATE.md`  
+ GitHub / Codex 仓库  
+ 文献矩阵  
+ 最小文档集合

聊天窗口负责研究判断，长期记忆落到项目文件中。

每轮讨论结束，应更新：

- 当前研究判断；
- 主线问题；
- 支线问题；
- 暂缓问题；
- 下一步最小行动。

---

## 11. 当前下一步最小行动

下一步只做：

> 完成 HUGSIM Source Availability Gate 与 pipeline / closed-loop mechanism 的第一轮抽取。

不要同时展开 OmniDreams / Cosmos。

OmniDreams / Cosmos 只用于回答：

> 未来生成式世界模型仿真是否能继承 HUGSIM / NeuroNCAP 类审计流程，还是需要新的 credibility evidence？
