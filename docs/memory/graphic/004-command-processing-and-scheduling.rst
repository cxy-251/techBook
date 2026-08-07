第004章：GPU 命令处理与调度
===========================

核心知识点
----------

图形 API 提交的是命令流
   CPU 记录的 draw、dispatch、copy、状态绑定、资源转换和同步命令，经运行时与驱动整理后进入 GPU queue。命令的粒度高于 shader 指令；command processor 负责推进工作，shader 执行单元只处理其中的图形或计算阶段。

CPU 与 GPU 位于不同时间线
   command buffer 录制完成只表示 CPU 已描述工作，queue submit 完成只表示命令进入提交路径，fence 或完成回调到达才表示 GPU 越过指定位置。资源回收与复用必须依据 GPU 完成进度，不能依据 CPU 已提交这一事实。

command buffer 有明确生命周期
   显式 API 中，命令对象通常经历分配、recording、executable、pending、completed 和 reset/reuse。command pool、allocator、descriptor、上传区域及其引用资源在 GPU pending 期间必须保持有效，并在对应完成信号后才能复用。

同步对象职责不同
   barrier 描述资源访问顺序、阶段和可见性；semaphore、event 或 queue wait 连接不同队列的 GPU 时间线；fence 把 GPU 进度暴露给 CPU。用 CPU wait 代替 GPU 资源依赖会破坏并行，用 barrier 代替生命周期保护又无法阻止 CPU 过早复用。

隐式与显式 API 分配不同责任
   OpenGL 由 driver 根据当前 context 状态构建内部命令并处理大量隐式转换；Vulkan、Metal 与 Direct3D 12 让应用显式组织 command buffer、pipeline、resource state 和同步。显式 API 提供控制能力，不会自动修复过碎提交、错误生命周期或频繁运行时创建。

多线程 recording 需要清晰所有权
   scene traversal、culling、resource preparation、pass building 和 command recording 可以并行；worker 应独占自己的 command pool、allocator 和 transient memory，共享的 pipeline cache、descriptor arena 与 resource state tracker 需要分片、锁或集中合并。最终 submit 通常收敛到统一位置维护全局 frame timeline。

多队列只有存在重叠窗口才有收益
   copy queue 适合可提前完成的上传，compute queue 适合能与 graphics 独立推进的计算。若计算结果马上被下一 graphics pass 使用，额外 signal/wait 可能只增加同步成本；是否异步应由 queue timeline 的实际重叠证明。

命令流应由资源图组织
   先描述每个 ``pass`` 读写哪些 texture、buffer 和 attachment，再推导 pass 顺序、barrier、queue 依赖与资源生命周期；之后才在 pass 内按 pipeline、material、descriptor 和 mesh 排序 draw。提交粒度需要在并行 recording、CPU submit 成本和可调试性之间平衡。

关键路径
--------

一帧命令从 CPU 到 GPU：

::

   CPU 建立 scene snapshot 与可见集
   → 构建 pass 输入输出和资源依赖
   → worker 录制 draw、dispatch、copy 与 barrier
   → submission point 按 queue 依赖组合命令
   → queue submit 进入 GPU 时间线
   → GPU 依次执行并在同步点等待
   → signal fence 或 completion value
   → CPU 回收对应 frame slot 资源

跨队列上传路径：

::

   CPU 写入 staging 或 upload buffer
   → copy command buffer 复制到目标资源
   → copy queue signal 完成值
   → graphics queue 在首次读取前 wait
   → 目标资源转为 shader-readable 状态
   → draw 使用新资源
   → fence 完成后复用 staging 区域

由资源依赖生成命令流：

::

   shadow pass 写 shadow map
   → barrier 转为 shader read
   → main pass 读取 shadow map 并写 color target
   → barrier 转为 shader read
   → post-process 读取 color target 并写 post target
   → UI 写 backbuffer
   → backbuffer 转为 present 状态
   → present 与 frame fence 完成

概念辨析
--------

* **command buffer 与 queue**：command buffer 保存待执行命令序列；queue 接收可执行工作并形成 GPU 时间线。录制对象本身不会自动执行。
* **录制完成、提交完成与执行完成**：录制完成是 CPU 状态；提交完成表示命令已交给队列；执行完成才允许回收 GPU 仍可能读取的资源。
* **barrier 与 fence**：barrier 约束 GPU 内部访问顺序和可见性；fence 让 CPU 观察 GPU 进度并保护资源生命周期。
* **queue wait 与 CPU wait**：queue wait 让一条 GPU 队列等待另一条队列的 signal；CPU wait 会阻塞主机线程，只应在资源复用、读回或帧节流确有需要时使用。
* **多线程 recording 与多线程 submit**：多个线程并行生成局部命令有助于降低 CPU 构建时间；多个调用点无序 submit 会分散全局依赖，通常应由统一提交点排序。
* **多 command buffer 与多 queue**：多个 command buffer 可以提交到同一 queue，用于并行录制或分 pass 组织；多 queue 表示独立 GPU 时间线，需要额外同步并不必然并行执行。
* **状态排序与资源依赖**：pipeline/material 排序减少局部绑定成本；资源读写依赖决定全局 pass 顺序。任何排序都不能破坏透明混合、stencil 或写后读正确性。

本章结论
--------

命令调度问题应同时沿 CPU 命令生成和 GPU queue 执行两条时间线观察。阅读引擎代码时，先建立 pass 资源图，再检查 command buffer 生命周期、barrier、queue signal/wait 和 frame fence；排查卡顿时，通过 CPU recording、submit、GPU marker 与 queue bubble 区分提交过晚、执行过慢和同步过强，最后才调整并行 recording、提交粒度、状态排序或异步队列。