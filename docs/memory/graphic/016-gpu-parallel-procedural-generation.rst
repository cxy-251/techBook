第016章：GPU 并行程序化生成
===========================

核心知识点
----------

GPU 生成的前提是任务可稳定拆分
   大任务必须映射为大量独立或弱依赖 work item，由 thread group 组织局部协作，并明确每个线程读取的候选元素和写入的输出区域。候选点、chunk、vertex/index/instance buffer 与 indirect draw 构成最小工程对象。

固定输出适合直接地址写入
   每个候选元素输出固定数量顶点或实例时，可由 global id 直接计算写入 offset，线程之间无需竞争。它实现简单且吞吐稳定；大量候选被拒绝或输出数量变化时，会产生空洞和容量浪费。

变量输出需要分配与压缩
   Append buffer 用 atomic counter 获取连续写入位置，适合原型和中等规模；prefix sum 先计算每个元素的输出数量，再生成稳定 offset；compaction 把有效元素搬到连续区域。选择取决于输出规模、原子竞争、额外 dispatch 和后续消费需求。

Indirect draw 让生成数量停留在 GPU
   Compute pass 根据 counter 或 scan 结果写入 vertex/instance count 和 draw args，图形队列直接消费 buffer。CPU 只提交参数和少量命令，避免每帧读回生成数量；args 布局、counter reset 和资源状态必须与 API 合同一致。

同步分为组内同步与管线同步
   Group barrier 只保证同一 thread group 的共享内存和执行进度；API resource barrier 保证不同 dispatch、队列以及 compute 写入到 graphics 读取之间的可见性。组内算法正确不能替代跨 pass 状态转换。

输出形式决定带宽与更新频率
   直接生成完整顶点最直观但写入量大；生成 instance description 更紧凑，可由 vertex shader 展开草叶、碎石等重复几何；生成中间参数适合道路、建筑和多级规则继续处理。静态 chunk 应缓存，时间和风场变化尽量留在 shader。

Chunk 与生命周期支撑大场景扩展
   每个 chunk 应记录 bounds、seed、输入版本、状态、容量、LOD、buffer offset 和统计。CPU 任务系统筛选活跃 chunk、准备参数和 streaming 优先级，GPU 处理候选生成、culling、compaction 和 args；成本应跟可见和变化区域相关，而非世界总规模。

Async compute 的价值来自可重叠依赖
   Compute queue 可以提前生成远处 chunk 或下一帧资源，前提是资源依赖允许与 graphics 重叠。跨队列同步、ownership 转换和执行单元竞争可能抵消收益；“使用异步队列”本身不是优化结论。

性能调试必须同时记录规模和空间分布
   Marker 和 timer 应绑定 active chunk、candidate、accepted instance、dispatch 和 buffer 字节数；validation buffer 记录 capacity、overflow、LOD 和 error code；heatmap 把计数与耗时映射回场景位置。工具名称不能代替明确的资源路径证据。

关键路径
--------

Compute 生成并绘制：

::

   CPU 筛选活跃 chunk 并上传少量参数
   → 清零 counter、statistics 与 indirect args
   → dispatch 让每个 work item 处理候选元素
   → 固定输出直接写入，变量输出生成 count/flag
   → append 或 prefix sum + compaction 形成连续结果
   → compute 写入 draw indirect args
   → 插入 compute-write 到 graphics-read barrier
   → draw indirect 消费 vertex/index/instance 与 args
   → validation buffer 和 heatmap 验证数量、容量和画面

变量数量输出：

::

   每个候选计算输出数量
   → 输出 count 或 valid flag
   → 对 count 做 prefix sum
   → 得到每个候选的唯一连续 offset
   → 写入紧凑 instance、vertex 或 index buffer
   → 最后一个 scan 结果得到总数量
   → 写入 indirect args 并执行绘制

Chunk 生命周期：

::

   Unloaded
   → CPU 创建元数据并进入 CPUReady
   → 参数上传进入 UploadQueued
   → dispatch 提交进入 GPUQueued
   → 生成完成并成为 Resident
   → 输入改变进入 Dirty 并局部重建
   → 超出 streaming 预算进入 EvictQueued
   → 等待 GPU 不再使用后回收 buffer offset

性能定位：

::

   用 marker 分隔 reset、generate、scan、compact、args 和 draw
   → 为每段记录 GPU 时间和输入规模
   → 检查 dispatch 数量、occupancy、atomic 与带宽
   → 检查 counter、capacity、overflow 和 args 内容
   → 检查 barrier 与队列等待
   → 用 chunk heatmap 定位空间热点
   → 按候选规模、分配方式、输出宽度或跨帧调度逐项优化

概念辨析
--------

* **Work item 与 thread group**：work item 处理单个逻辑元素；thread group 组织一批线程并提供组内共享内存与同步。
* **固定写入与 append**：固定写入从 id 直接推导地址，无原子竞争；append 适合变量数量，但依赖共享计数器和容量管理。
* **Append 与 prefix sum**：append 单 pass 表达简单，可能产生 atomic 热点；prefix sum 需要多阶段和临时 buffer，但输出 offset 稳定且易于大规模压缩。
* **Compaction 与 culling**：culling 判断元素是否保留；compaction 把保留元素重新排列为连续结果，二者通常串联使用。
* **Direct draw 与 indirect draw**：direct draw 的数量由 CPU 命令参数确定；indirect draw 从 GPU buffer 读取参数，适合生成、剔除和 LOD 结果留在 GPU。
* **Group barrier 与 resource barrier**：前者只作用于组内协作；后者管理 pass、stage 或 queue 之间的资源可见性与状态。
* **生成顶点与生成实例**：生成顶点提供最大自由度但带宽高；生成实例保留共享模板 mesh，以较小描述驱动重复对象。
* **并行执行与确定性顺序**：GPU 线程完成顺序不固定；只要输出地址、随机种子和归约规则稳定，结果仍可设计为确定性。
* **Async compute 与并行收益**：async compute 是调度能力；真实收益取决于可重叠区间、资源依赖和硬件竞争。

本章结论
--------

GPU 程序化生成应围绕“任务粒度—输出分配—同步—消费—证据”设计。先把规则拆成可并行候选，按固定或变量输出选择直接写入、append 或 prefix sum，再通过 barrier 和 indirect draw 让结果留在 GPU；大场景以 chunk、容量和跨帧 streaming 控制规模，并用 marker、统计、validation 与 heatmap 验证。缺少任一边界，GPU 生成都会退化为难以控制的 buffer 更新。