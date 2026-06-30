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

当前第一审计对象调整为：

**OmniDreams**

理由：

OmniDreams 更接近最新一代生成式闭环仿真 / 世界模型仿真方向，可能代表未来自动驾驶仿真从“神经重建仿真”走向“生成式世界模型闭环仿真”的趋势。

因此当前不再先从 NeuroNCAP / HUGSIM / UniSim / AdvSim 开始逐个铺开，而是：

> 先审计 OmniDreams 的自证机制，再用 NeuroNCAP / HUGSIM / UniSim / AdvSim 作为历史脉络和横向对照。

---

## 3. 对照对象定位

以下工作作为对照对象和历史脉络：

- NeuroNCAP
- HUGSIM
- UniSim
- AdvSim

它们用于回答：

- 早期日志驱动 / 反事实 / 传感器级闭环仿真如何自证可信；
- 它们使用了哪些自证指标；
- 这些指标实际证明了什么；
- 这些指标没有证明什么；
- OmniDreams 是否解决了旧问题，还是只是换成了生成式世界模型表达。

---

## 4. 主线研究问题

当前主线问题如下：

### RQ1

OmniDreams 如何证明自己的仿真结果可信？

### RQ2

OmniDreams 的指标是在验证仿真器可信性，还是只是在验证自动驾驶模型表现？

### RQ3

OmniDreams 是否能发现低可信反事实样本、生成 artifact、遮挡错误、深度错误、几何关系不一致、时序关系不一致？

### RQ4

NeuroNCAP / HUGSIM / UniSim / AdvSim 的自证指标，能否迁移到 OmniDreams 上？

### RQ5

是否仍然需要一个 credibility audit layer，用来判断闭环测试证据应被：

- accepted；
- down-weighted；
- rejected。

---

## 5. 当前理论判断

真实日志驱动反事实闭环仿真是必要方向，但它不是天然可信。

端到端自动驾驶 / sensor-input E2E agent 的趋势使评估问题从 motion-level planning 推进到 sensor-to-action closed-loop evaluation。

传统两段式或模块化系统可以支撑受限自动驾驶能力，但存在结构性信息瓶颈：

- 中间接口会丢失任务相关但难以人工定义的信息；
- 感知指标和驾驶目标存在错配；
- open-loop benchmark 可能无法反映 closed-loop 安全表现；
- sensor-input agent 的真正能力必须在闭环反事实环境中评估。

因此，本项目的关键判断是：

> E2E 使 sensor-level closed-loop evaluation 变得不可回避；  
> counterfactual simulation 使 credibility audit 变得不可回避。

---

## 6. 当前工作原则

当前阶段坚持最小化，不走太远。

不急于：

- 提出完整 verifier；
- 复现所有系统；
- 生成大而全综述；
- 一次性写完所有 simulator cards；
- 让聊天窗口变成长期记忆。

当前只做一件事：

> 审计 OmniDreams 的自证机制。

---

## 7. 当前最小文件结构

当前项目只需要维护以下最小文件：

- `README.md`
- `PROJECT_STATE.md`
- `docs/omnidreams_audit.md`
- `docs/comparison_notes.md`

其中第一优先级是：

- `docs/omnidreams_audit.md`

---

## 8. OmniDreams 审计模板

`docs/omnidreams_audit.md` 应优先回答：

1. OmniDreams 的基本 pipeline 是什么？
2. 它是否真实日志驱动？
3. 它如何支持反事实修改？
4. 它生成哪些传感器级观测？
5. 它是否支持闭环 rollout？
6. 它如何更新世界状态？
7. 它支持什么类型的 sensor-input E2E agent？
8. 它使用哪些自证指标？
9. 这些指标证明了什么？
10. 这些指标没有证明什么？
11. 它相比 NeuroNCAP / HUGSIM / UniSim / AdvSim 的推进在哪里？
12. 它仍然缺失哪些 credibility evidence？

---

## 9. 需要重点审计的可信性缺口

重点不是 photorealism，而是 task-relevant relational consistency。

需要关注：

- front / rear / left / right 是否稳定；
- same-lane / adjacent-lane / off-road 是否正确；
- approaching / receding 是否可信；
- occluding / occluded-by 是否一致；
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

> 写 `docs/omnidreams_audit.md` 的第一版。

不要同时展开 NeuroNCAP / HUGSIM / UniSim / AdvSim。

对照对象只用于回答：

> OmniDreams 相比这些历史工作，是否真的推进了日志驱动反事实闭环仿真的可信评估问题？
