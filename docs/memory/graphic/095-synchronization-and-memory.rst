第095章：同步与内存
==================

核心知识点
----------

显式同步必须回答具体依赖
   Fence 回答 CPU 何时能复用资源；semaphore/event 回答 GPU queue 何时能接续另一条执行流；barrier 回答前一次资源访问如何对后一次访问可见；image layout 描述图像当前访问形态；queue ownership transfer 描述资源归哪个 queue family 使用。

CPU/GPU 同步与 GPU/GPU 同步是两层问题
   CPU 等待 frame fence 是主机侧资源复用控制；queue 之间通过 semaphore/timeline/event 建立 GPU 执行依赖；同一命令流内的 RAW/WAW/WAR hazard 再由 barrier 和访问范围解决。不能用一个层级的对象推断另一个层级已经安全。

Barrier 的核心字段是前后访问关系
   Vulkan 中要写清 src stage/access、dst stage/access、资源或 subresource range，以及 image old/new layout。Stage 过宽会扩大等待，过窄会漏依赖；access 不匹配则会出现数据未可见或 validation hazard。

RAW、WAW、WAR 是资源依赖的基础分类
   Compute 写 bloom 后 fragment 采样属于 RAW；两个 pass 写同一 storage image 属于 WAW；读后再覆盖属于 WAR。同步设计先写出“哪一资源、哪一范围、前序谁访问、后序谁访问”，再选择 API 对象。

Image Layout 是访问形态，不只是标签
   Upload 常用 transfer destination，shader sampling 常用 shader-read，color attachment 写入使用 attachment layout，present 使用 present layout。Layout transition 要和真实 stage/access 一起变化，只改布局名并不能自动建立数据可见性。

跨 Queue 交接需要执行依赖和资源所有权同时成立
   Transfer queue 上传 texture、graphics queue 随后采样时，通常需要源 queue release、目标 queue acquire、合适的 layout/access transition，以及 semaphore/timeline value 连接两个 submit。Semaphore 不能替代 ownership barrier，barrier 也不能替代 queue wait。

Frame Graph 是生成同步关系的最佳输入
   Pass graph 已经包含资源 read/write、queue、subresource 与生命周期。先从图中推导 Upload→Compute→Graphics→Present，再生成 barrier、queue wait 与 layout transition，比在各 pass 手写零散同步更容易验证。

Fence 应放在资源真正需要回收的时间线上
   Frame fence 保护 command buffer、descriptor、uniform/upload slice 和 transient resource 的复用。每帧 submit 后立刻 CPU wait 会把多帧并行压扁；正确做法是在即将复用对应 frame slot 前等待或查询。

Timeline Semaphore/Event 适合多提交的连续进度
   用递增 value 表达 copy、compute、graphics 等多个工作完成点，可减少大量二元同步对象并让依赖更易记录。它仍然需要和资源 barrier、ownership 与生命周期配合。

Metal 隐藏部分 Vulkan 式 Layout，但不取消 Hazard
   Command buffer/encoder 顺序、resource usage、fence/shared event、storage mode 与 blit synchronization 共同表达写后读、跨 encoder、跨 queue 与 CPU/GPU 可见性。排查重点从 layout 字段转为 encoder 顺序和 resource ownership。

内存类型应从访问模式反推
   GPU 高频读取的静态 texture/vertex buffer 优先 device-local/private；CPU 高频更新的小常量使用 host-visible/shared ring；大资源上传使用 staging→device-local/private；readback 使用 CPU 可见内存并等待 GPU 完成。

Staging 是 CPU 与 GPU 高性能内存之间的桥
   CPU 把数据写入 host-visible/shared staging buffer，transfer/blit copy 到 device-local/private resource，随后 barrier/encoder dependency 把目标交给 shader 使用。这样把 CPU 写友好和 GPU 读友好两种内存职责分开。

Flush/Invalidate 只解决 Cache 可见性，不解决 GPU 执行顺序
   非 coherent host-visible memory 可能要求 flush CPU 写入、invalidate CPU 读取；这些操作不能证明 GPU 已执行到正确点，仍需 fence/semaphore/barrier 等执行同步。

Suballocation 与 Transient Alias 应按生命周期管理
   大块 device memory/heap 可切分给多个 buffer/image，减少频繁分配与碎片。不同 transient resource 复用同一内存只有在生命周期不重叠且 aliasing/hazard 规则满足时才安全。

同步性能问题通常来自“同步范围过大”
   ``ALL_COMMANDS``、全资源 barrier、每 pass queue wait、每帧 CPU fence wait 都可能制造 bubble。优化前先确认正确性，再把 stage/access/subresource 和等待位置收缩到最小充分范围。

关键路径
--------

Upload → Shader Read：

::

   CPU writes staging memory
   → flush if required
   → transfer/blit copy
   → transfer write completes
   → barrier/layout transition
   → optional queue ownership + semaphore wait
   → shader read

Compute → Graphics：

::

   compute dispatch writes UAV/storage image
   → shader-write completion
   → barrier: compute write → fragment/graphics read
   → layout/resource usage transition
   → graphics draw samples result

Frame Resource Reuse：

::

   submit frame N
   → signal fence/timeline value
   → GPU executes asynchronously
   → CPU prepares later frames
   → before reusing slot N, query/wait completion
   → reset command/descriptor/upload/transient resources

同步排查：

::

   identify resource + subresource
   → prior pass / stage / access
   → next pass / stage / access
   → same queue or cross queue?
   → layout / ownership state
   → barrier / semaphore / fence placement
   → validation / capture queue timeline

概念辨析
--------

* **Fence 与 Semaphore**：fence 主要让 CPU 观察 GPU 完成，semaphore/event 主要连接 GPU 执行流。
* **Barrier 与 Semaphore**：barrier描述资源访问/可见性，semaphore描述提交之间的执行依赖。
* **Layout 与 Access Mask**：layout描述 image 访问形态，access描述具体读写类型，二者应和 stage 一起匹配。
* **Queue Ownership 与 Resource Lifetime**：ownership说明当前哪个 queue family可使用资源，lifetime说明资源是否还能存在；两者不同。
* **Flush/Invalidate 与 Fence**：前者处理 host cache 可见性，后者证明 GPU 执行进度。
* **Device-Local 与 Host-Visible**：前者通常优化 GPU 访问，后者服务 CPU 写读；真实选择应基于设备 memory property 与 usage。
* **同步正确 与 同步高效**：先保证所有真实依赖存在，再逐步缩小同步范围；少 barrier 本身不是目标。

本章结论
--------

同步与内存应按“Resource—Prior Access—Next Access—Queue—Layout/Ownership—Synchronization—Allocation Policy”理解。随机闪烁先查 RAW/layout/frame-slot 复用，GPU bubble 再查 barrier 与 queue wait 是否过宽，CPU 读回旧数据则同时查 GPU completion 与 cache 可见性。显式 API 的同步质量，取决于每个等待是否都能回答一个具体资源依赖，而不是 barrier、fence 越多越安全。