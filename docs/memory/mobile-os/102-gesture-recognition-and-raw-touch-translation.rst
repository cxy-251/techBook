第102章：Gesture Recognition and Raw Touch Translation
======================================================

核心知识点
----------

* Raw Touch 只描述触点序列；Gesture Recognition 才把一段触点变化解释成 tap、long press、drag、swipe、pinch 等 UI 语义。
* 手势识别本质上是状态机：根据时间、距离、速度、方向、触点数量和目标状态，从 possible 进入 recognized/began/changed/ended，或进入 failed/cancelled。
* Tap 依赖短时间和低位移；Long Press 依赖持续时间与有限移动；Drag 依赖越过位移阈值；Swipe 依赖方向、速度和距离；Pinch 依赖多指距离与中心变化。
* 多点触控要求稳定 Pointer ID / touch identity。若触点身份在序列中错乱，缩放、旋转、拖动都会出现跳变。
* Hit Test 决定触摸最初落在哪个 View；Gesture Recognizer 决定这一段序列被解释成什么；业务层再把手势转换成页面动作。
* 同一触摸序列可能被多个 recognizer 同时观察，因此需要 priority、failure dependency、simultaneous recognition、parent interception 等竞争规则。
* Scroll、Nested Gesture、系统返回手势和 App 自定义 drag 都可能争夺同一段 MOVE 序列；竞争结束后，失败方通常收到 cancel 或进入 failed 状态。
* 手势问题的稳定排查顺序是 ``事件完整性 → Hit Test → Recognizer 状态 → 手势竞争 → 业务回调``。

关键路径
--------

::

   Raw Touch Sequence
      → Framework Event Object
      → Hit Test
      → Candidate Recognizers
      → threshold / timing / pointer relation
      → competition / failure dependency
      → recognized gesture
      → View / Control state
      → business UI intent

以图片缩放页面为例：

::

   单指 DOWN
      → Tap / LongPress / Pan 同时进入 possible
      → 小幅移动：Tap 仍可能成立
      → 越过 slop：Pan began，Tap failed
      → 第二指加入：Pinch 进入竞争
      → 手势结束：生成缩放 / 平移 / 点击等最终意图

概念辨析
--------

* **Raw Touch vs Gesture**：前者是坐标与触点状态；后者是框架根据一段序列推导出的交互语义。
* **Pointer ID vs Pointer Index**：ID 代表触点身份；Index 只是当前事件中的位置。
* **Hit Test vs Gesture Recognition**：Hit Test 决定“谁有资格接收”；Gesture Recognition 决定“这段事件意味着什么”。
* **Drag vs Scroll**：二者都由连续移动构成，区别主要来自目标控件、方向、阈值和父子容器竞争规则。
* **Cancel vs Failure**：Cancel 表示正在处理的序列被外部条件中止；Failure 表示 recognizer 自己判断当前序列不满足目标手势。

本章结论
--------

Gesture 是对 Raw Touch 的二次解释。真正稳定的交互模型需要同时管理触点身份、阈值、目标 View 和 recognizer 竞争。出现“点击没反应”“滚动抢事件”“双指缩放跳变”时，应先检查序列和识别状态，再检查业务代码。