第025章：Compute Shader
======================

核心知识点
----------

Compute Shader 是脱离固定图形阶段的并行数据处理路径
   它由 dispatch 启动，以 work group 和 invocation 组成执行网格，主要读写 storage buffer、storage texture、UAV 或等价资源。它的输出通常不是直接像素，而是被后续 graphics、copy、readback 或下一次 compute pass 消费的 GPU 数据。

适合 Compute 的任务具有稳定的数据并行结构
   粒子更新、GPU culling、prefix sum、compaction、image filter、tile/cluster light list、simulation 和程序化生成都能把大量同构元素映射为 invocation。若任务规模很小、依赖复杂 CPU 对象图、频繁 I/O 或结果立即需要 CPU 逐项读取，dispatch 与同步成本可能超过收益。

Dispatch 数与 group size 共同决定实际 invocation 数
   API 提交 work group 数，shader 声明 group 内线程数，总执行量是二者乘积。元素数量通常无法整除 group size，因此必须向上取整 dispatch，并在 shader 中用 count 做越界保护。

Work group size 是调度、资源占用和内存访问的联合决策
   选择要同时考虑设备 limit、wave/subgroup 粒度、register/shared memory 占用、occupancy 和访问连续性。64、128、256 常作为起点，但最终值应由目标硬件 profiler 证明，而不是固定经验值。

Shared memory 只在组内数据复用时有价值
   邻域滤波、局部归约、tile 算法和 prefix sum 常先把数据搬进 shared memory，再由组内线程重复使用。普通逐元素粒子积分若每个线程只访问自己的元素，引入 shared memory 反而增加同步与搬运。

变量输出需要显式处理写入竞争
   多个 invocation 写同一位置会产生 race。Atomic 适合简单计数，append 适合变量数量输出，prefix sum 可生成稳定唯一 offset，compaction 再把有效元素写成连续列表。算法选择取决于输出规模、竞争程度和后续读取需求。

Compute 与 graphics 的连接点是资源依赖
   Compute 写入 particle/visible/indirect buffer 后，后续 vertex、fragment 或 indirect draw 读取前必须有执行顺序和内存可见性保证。Shader 内 barrier 不能替代 API 层 compute-write → graphics-read 的 resource barrier。

Resource state transition 描述的是用途变化
   Storage write 后可能转为 vertex read、sampled read、indirect argument read 或 copy read。API 名称不同，稳定维度始终是资源对象、前一访问、后一访问和消费者 stage。

Async compute 只有在依赖允许重叠时才有收益
   Compute queue 与 graphics queue 能并行，不代表一定更快。若 compute 结果马上被下一 draw 读取，重叠空间很小；若结果服务更晚 pass 或下一帧，才更可能通过跨队列调度隐藏成本。

关键路径
--------

粒子 Compute 到绘制：

::

   CPU 更新 simulation params
   → 计算 groupCount = ceil(elementCount / groupSize)
   → 绑定 compute pipeline 与 particle buffer
   → dispatch
   → invocation 按 global id 更新元素
   → compute 写 particle buffer
   → 插入 compute-write → graphics-read 依赖
   → render pass 读取同一 buffer
   → draw/indirect draw
   → frame 输出

变量数量输出：

::

   每个 invocation 计算 valid/count
   → 写 flag/count buffer
   → prefix sum 生成唯一 offset
   → compaction 写连续结果
   → 得到最终 count
   → 写 indirect args
   → barrier
   → graphics pass 消费紧凑列表

Compute 错误排查：

::

   对齐数据规模、group size 与 dispatch
   → 检查 global id 到数据 index 映射
   → 检查越界保护
   → 检查 descriptor/bind group 与资源尺寸
   → 检查 atomic/race/prefix sum
   → 检查输出 buffer 内容
   → 检查跨 pass barrier 和 resource state
   → 最后检查 render consumer

概念辨析
--------

* **Dispatch group 与 invocation**：dispatch 指定 work group 数；shader 的 workgroup size 指定每组线程数；global invocation 是两者展开后的实际执行单元。
* **Work group 与 wave/subgroup**：work group 是 shader 可同步和共享内存的编程单元；wave/subgroup 是硬件执行粒度，二者大小不一定相同。
* **Shared memory 与 global buffer**：shared memory 生命周期局限于单个 work group，速度快且容量小；global/storage buffer 跨 group 和 pass 持久存在。
* **Atomic 与 prefix sum**：atomic 通过竞争一个或多个计数器分配位置；prefix sum 多阶段计算稳定 offset，额外 dispatch 更多但扩展性和可解释性更强。
* **Compaction 与 culling**：culling 产生是否保留的判断；compaction 把保留元素重新排列为连续数组。
* **Shader barrier 与 resource barrier**：前者解决组内或 shader 内同步；后者解决 pass、stage、queue 之间的数据可见性。
* **Compute pipeline 与 graphics pipeline**：compute 由 dispatch 驱动并写显式资源；graphics 由 draw 驱动并经过固定图形阶段，二者通过资源依赖连接。
* **Async compute 与免费并行**：async compute 只是允许重叠，实际收益受资源依赖、队列同步和硬件执行资源竞争限制。

本章结论
--------

Compute Shader 应围绕“数据规模—线程映射—输出写入—资源同步—后续消费者”设计。先判断任务是否真正数据并行，再由元素数量推出 dispatch 和 group size，处理竞争与 compaction，最后明确 compute 写入如何对 graphics 或下一 pass 可见；多数 Compute 错误不在公式，而在执行范围、写入竞争和跨 pass 资源依赖。