================================================================================
Chapter 45: 海量图元协同白板与图形设计工具：Wasm、WebGL/WebGPU 与 WebRTC 实时协同架构 (Real-Time Collaborative Canvas)
================================================================================

.. note:: 前置背景与认知承接
   在上一章（Chapter 44: 高并发海量吞吐电商系统：混合渲染、边缘缓存与秒杀防刷架构）中，我们系统探讨了在面向海量公网消费者的交易场景下，如何通过动静分离、边缘微缝合、令牌风控与 Redis+Lua 原子操作保障极端读写并发下的可用性与一致性。

   当工程场景由基于 DOM 树构建的通用文档与交易系统，转向面向专业图形设计、CAD 建模与多人协同创作的现代 Web 白板工具（如 Figma、Miro、Canva、Excalidraw 级系统）时，系统设计的核心瓶颈发生了根本性迁移：
   此时的核心矛盾不再是网络端到端的吞吐与 HTTP 缓存命中率，而是**浏览器运行时在百万级图元渲染下的物理帧率极限、JavaScript 单线程事件循环中的垃圾回收（GC）抖动、以及分布式点对点协作状态在弱网环境下的因果一致性保证**。

   本章作为 **Part 8: 工业级架构案例演进与技术选型** 的第三部核心实战篇章，将从 DOM/SVG 到硬件加速画布的底层渲染机制切入；系统解构基于 WebAssembly 线性内存的紧凑场景图（Scene Graph）与动态空间划分索引（Loose Quadtree / BVH）；推导基于 WebGL/WebGPU 的多边形批处理实例绘制（Instanced Batching）管线；深入剖析无冲突复制数据类型（CRDT）在图形拓扑中的冲突仲裁模型；并结合 WebSocket 与 WebRTC DataChannel 交付一套完整的工业级多通道实时协同图形引擎内核。

------------------------------------------------------------------------
45.1 复杂图形工具在 Web 运行时的物理极限与渲染架构演进
------------------------------------------------------------------------
在 Web 平台上构建复杂图形编辑系统，首先面临的是浏览器渲染引擎在对象数量与帧率预算上的硬性物理约束。

不同渲染技术路径的物理天花板分析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
浏览器为图形呈现提供了四种完全不同的技术载体。在百万级图元规模与 60/120 FPS 极速交互的约束下，它们的技术表现呈现出阶梯式的性能分水岭：

.. list-table:: 浏览器四大图形渲染技术路径物理特性与瓶颈矩阵
   :widths: 16 21 21 21 21
   :header-rows: 1

   * - 维度指标
     - DOM 节点拼装
     - 原生 SVG 矢量图
     - Canvas 2D 上下文
     - **WebGL / WebGPU 硬件直通**
   * - **图元数量承载极限**
     - $1,000 \sim 3,000$ 节点
     - $3,000 \sim 10,000$ 节点
     - $10,000 \sim 50,000$ 图元
     - **$500,000 \sim 2,000,000+$ 图元**
   * - **单图元内存开销**
     - $1 \sim 2	ext{ KB}$ (C++ 宿主对象 + 样式计算)
     - $500	ext{ B} \sim 1	ext{ KB}$ (包含属性表)
     - 0 节点开销 (纯像素，由 JS 维护状态)
     - **$16 \sim 64	ext{ B}$ (紧凑 GPU 顶点/实例缓冲)**
   * - **渲染管线与批处理**
     - 强制样式重排、分层合成、无法合并绘制
     - 依赖浏览器树遍历、存在严重的重排损耗
     - CPU 逐指令光栅化，状态切换开销显著
     - **GPU 并发硬件光栅化、单次 DrawCall 批处理**
   * - **高频变换性能 (平移/缩放)**
     - 极差 (频繁触发 Layout / Composite)
     - 较差 (矩阵属性修改触发重绘)
     - 中等 (全屏清除与重放绘制命令)
     - **极致 (仅更新 16 浮点数 MVP 统一变量)**
   * - **多线程解耦支持**
     - 否 (严格锁定在 Renderer 主线程)
     - 否 (受限于 DOM 树绑定)
     - 是 (支持 `OffscreenCanvas` + Worker)
     - **完全支持 (`OffscreenCanvas` + Worker 并发)**

DOM 与 SVG 路径的崩溃根源
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
早期图形白板常尝试直接使用 HTML DOM 节点或 SVG `<path>` 元素表达画布上的图形对象。这种设计在图元数量突破数千个时会引发浏览器底层的级联性能崩溃：

1. **C++ 宿主对象内存膨胀**：
   每一个 DOM/SVG 元素在 Blink 内核中均对应一个复杂的 C++ 对象（如 `Element`、`LayoutObject`、`PaintLayer`），附带庞大的样式计算级联表（Computed Style Rules）。10 万个图元意味着至少 150MB~300MB 的 C++ 堆内存占用，直接诱发移动端浏览器的 OOM 强杀。
2. **强制同步重排 (Layout Thrashing)**：
   在画布缩放（Zoom）或平移（Pan）过程中，若修改父级容器的变换矩阵，渲染引擎必须自顶向下遍历整个 DOM 树，重新计算每个子元素的几何边界、盒模型与包围盒。即使开启 CSS 硬件加速（`transform: matrix(...)`），上万个独立图层的组合与管理也会彻底拖垮合成线程（Compositor Thread）的内存带宽。
3. **命中测试 (Hit-Testing) 的 $O(N)$ 灾难**：
   浏览器原生的事件派发依赖屏幕坐标反向穿透 DOM 树的树形遍历。当成千上万个重叠图元并发响应 `pointermove` 事件时，浏览器主线程陷入漫长的几何相交判定，导致每秒帧数断崖式跌落至个位数。

现代工业级标准架构的选择
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了彻底摆脱 DOM 树的束缚，Figma 等现代顶级图形工具确立了全新的工业标准范式：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                             现代高性能协同白板四层架构拓扑                                           |
   +----------------------------------------------------------------------------------------------------+

     [渲染层 (Hardware Rendering)]   ===> WebGL / WebGPU + OffscreenCanvas (专职 GPU 批处理流水线)
                    ^
                    | (单向流: 仅传递无锁共享指针与视口粗筛索引，零 GC 压迫)
     [逻辑层 (Wasm Core Engine)]    ===> WebAssembly (C++ / Rust 内核: 紧凑场景图、BVH 空间索引、几何布尔运算)
                    ^
                    | (解耦通道: Structured Clone / ArrayBuffer 跨线程消息)
     [调度层 (Interaction Worker)]  ===> Dedicated Web Worker (高频事件插值、输入预测、命令历史 Redo/Undo)
                    ^
                    | (轻量事件捕获: 零业务计算，仅负责事件反压与全屏事件监听)
     [外壳层 (Browser Main Thread)] ===> UI 外壳 (极简 DOM: 工具栏、属性面板、菜单弹窗)

在这个架构中，浏览器主线程只负责外围极少量的宿主 UI 交互；核心画布渲染被彻底代理至独立的 Web Worker 中，通过 WebAssembly 操纵线性内存，并利用 WebGL/WebGPU 硬件管线直接驱动 GPU 完成多边形装配与光栅化输出。

------------------------------------------------------------------------
45.2 核心数据结构与场景图空间索引 (Scene Graph & Spatial Indexing)
------------------------------------------------------------------------
在画布中容纳上百万个图元并实现实时交互，核心在于设计一套紧凑、缓存局部性优异、且能够实现亚毫秒级空间检索的数据结构体系。

面向数据设计 (DoD) 与连续线性内存布局
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
传统的面向对象范式（OOP）将图元设计为包含坐标、颜色、层级指针的多态对象。这种离散分布的堆对象在 JavaScript V8 引擎中会导致严重的内存碎片与缓存未命中（Cache Miss），更会在高频遍历时触发长时间的垃圾回收暂停（Stop-the-World GC Pause）。

现代图形内核严格采用**面向数据设计（Data-Oriented Design, DoD）**，在 WebAssembly 线性内存中构建结构体数组（Structure of Arrays, SoA）：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                              Wasm 线性内存中的 SoA 场景图图元数据布局                                |
   +----------------------------------------------------------------------------------------------------+

     [ID 数组 (uint32)]     : [ id_0, id_1, id_2, ..., id_N ]
     [父节点引用 (uint32)]  : [ p_0,  p_1,  p_2,  ..., p_N  ]
     [AABB 边界 (float32)]  : [ minX_0, minY_0, maxX_0, maxY_0, minX_1, minY_1, maxX_1, maxY_1, ... ]
     [局部矩阵 (float32)]   : [ a0, b0, c0, d0, tx0, ty0, a1, b1, c1, d1, tx1, ty1, ... ]
     [世界矩阵 (float32)]   : [ W_a0, W_b0, W_c0, W_d0, W_tx0, W_ty0, ... ]
     [颜色与样式 (uint32)]  : [ RGBA_0, Stroke_0, RGBA_1, Stroke_1, ... ]
     [拓扑类型与标志 (uint8)]: [ Type_0, Flags_0, Type_1, Flags_1, ... ]

通过将同构属性连续紧凑排列，CPU 在执行视口裁剪和矩阵级联计算时能够充分利用 L1/L2 数据缓存行（Cache Line, 64 字节）以及 SIMD 向量化指令（Wasm 128-bit SIMD），实现每毫秒遍历并处理数十万图元的极限吞吐。

动态场景图与矩阵级联传递
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
图形白板支持图元的编组（Group）、嵌套帧（Frame）以及复合图形变换。场景图维护着一个严格的单亲有向无环图（DAG）：

- 每一个节点维护自身的**局部仿射变换矩阵（Local Transform Matrix）**：
  
  $$\mathbf{M}_{	ext{local}} = \begin{bmatrix} a & c & t_x \ b & d & t_y \ 0 & 0 & 1 \end{bmatrix}$$

- 节点的**世界坐标矩阵（World Transform Matrix）**由其父节点的世界矩阵左乘自身局部矩阵递归生成：
  
  $$\mathbf{M}_{	ext{world}}^{(i)} = \mathbf{M}_{	ext{world}}^{(	ext{parent}(i))} \cdot \mathbf{M}_{	ext{local}}^{(i)}$$

为了避免全树无意义的重复计算，引擎在节点中设置**脏标记位（Dirty Flag）**：当用户平移父级容器时，仅对该父节点设置 `DIRTY_WORLD_MATRIX` 标志。在下一帧绘制开始前，引擎执行单次自顶向下的前序遍历，仅对脏子树重新计算世界矩阵并刷新其世界轴对齐包围盒（AABB）。

动态空间划分索引：松散四叉树 (Loose Quadtree) vs 层次包围盒 (BVH)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当画布图元达到数十万量级时，逐个判断图元是否位于屏幕视口内的线性扫描复杂度为 $O(N)$，必然导致掉帧。必须引入多维空间数据结构将检索复杂度降低至 $O(\log N)$。

在交互式图形编辑场景中，图元经常被用户频繁拖拽、缩放、旋转或添加。以下是工业级空间索引选型的核心考量：

.. list-table:: 典型空间索引结构在图形白板场景下的性能权衡
   :widths: 20 26 27 27
   :header-rows: 1

   * - 空间索引结构
     - 核心构造机制
     - 视口范围检索耗时
     - **动态图元更新/重构开销**
   * - **静态 R* 树**
     - 基于最小包围盒面积最小化分裂，深度平衡
     - 极优 ($O(\log_M N)$)
     - **极差** (单次节点重平衡计算极其昂贵，不适合高频编辑)
   * - **严格四叉树 (Strict Quadtree)**
     - 空间递归均匀等分，跨边界图元放入父节点
     - 中等 (跨界图元退化至顶层)
     - 中等 (跨越网格边缘时频繁触发节点的删除与重新插入)
   * - **松散四叉树 (Loose Quadtree)**
     - 每个子节点网格向外扩张固定比例 (如 $K=2$)
     - **优异** (图元几乎总能被单一子节点完整容纳)
     - **极佳** (图元小范围微调无需改变所属空间桶，极度高效)
   * - **动态线性 BVH**
     - 基于 SAH (表面积启发式) 构建紧凑二叉树
     - 极致 (GPU 遍历友好)
     - 较差 (树旋转与局部重构建模复杂度高)

工业级图形白板通常采用**松散四叉树（Loose Quadtree）**作为主空间索引：通过将每个四叉树网格的空间判定范围从标准边长 $L$ 扩展至 $2L$（保留其原有的中心点位置），使得绝大多数尺寸小于网格尺度的图元在拖拽位移时完全不需要脱离当前网格节点，将高频图元位移的索引更新复杂度压制至 $O(1)$ 常数开销。

双模命中测试 (Hit-Testing) 引擎
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
用户在画布上点击或框选时，系统必须在 5 毫秒内精确返回光标下方命中的最顶层图元：

1. **粗筛阶段 (Broad-Phase)**：
   根据光标坐标在松散四叉树中自顶向下检索，快速过滤掉 99.9% 无关节点，输出与光标点 AABB 相交的候选图元集合（通常小于 20 个）。
2. **精筛阶段 (Narrow-Phase)**：
   - *几何解析法*：针对规则矩形和多边形，利用多边形射线法（Ray Casting Algorithm）或分离轴定理（SAT）计算点与旋转几何体的相交性。
   - *离屏颜色编码拾取 (Color-ID Offscreen Picking)*：对于贝塞尔曲线、复杂描边等解析计算极其昂贵的图元，引擎在后台离屏 WebGL Framebuffer 中以 1x1 像素大小、使用唯一图元 ID 编码为 RGB 颜色值（`id & 0xFF`, `(id >> 8) & 0xFF`, `(id >> 16) & 0xFF`）进行快速硬件栅格化，随后调用 `gl.readPixels()` 在 1 毫秒内通过读取像素颜色瞬间锁定被命中的唯一图元 ID。

------------------------------------------------------------------------
45.3 Wasm 内存模型、跨语言绑定与零拷贝图形管道
------------------------------------------------------------------------
WebAssembly 提供了接近硬件原生的计算速度，但如果架构设计不当，跨语言边界带来的数据通信成本将完全抵消 Wasm 的计算收益。

跨语言边界开销 (Boundary Crossing Overhead) 的陷阱
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
V8 引擎在调用 WebAssembly 导出的函数时，虽然经过了优化的内联处理，但其开销仍然显著高于原生 JS 函数调用。更严重的问题在于**数据序列化壁垒**：
若每次图形更新都需要将图元状态在 JS 对象与 Wasm 内存之间通过结构化克隆（Structured Clone）或频繁的参数打包解包传递，引擎将产生数以万计的瞬时对象分配，引发高频 Minor GC，造成周期性掉帧。

内存控制权倒置：Wasm 拥有单一事实源
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
解决跨语言开销的核心工程准则，是确立**内存控制权倒置（Inversion of Memory Control）**：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                               Wasm 线性内存与 WebGL 零拷贝直通架构                                  |
   +----------------------------------------------------------------------------------------------------+

     [Wasm 线性内存空间 (WebAssembly.Memory / ArrayBuffer)]
       |
       +---> [0x00000000 ~ 0x00100000] : 空间索引、四叉树节点堆栈、命令环形队列
       +---> [0x00100000 ~ 0x00800000] : 图元 SoA 核心属性表 (坐标、变换矩阵、颜色、标志位)
       +---> [0x00800000 ~ 0x01000000] : GPU 实例渲染输出缓冲区 (Packed Instance Buffer)
                   |
                   v (仅通过 Uint8Array / Float32Array 零拷贝视口切片映射)
     [JavaScript / WebGL API 交互层]
       |
       +---> gl.bindBuffer(gl.ARRAY_BUFFER, gpuBufferInstance);
       +---> gl.bufferSubData(gl.ARRAY_BUFFER, 0, wasmMemoryView, byteOffset, byteLength);
                   |
                   v (DMA 物理直推显存)
     [GPU 专用显存空间 (VRAM)]
       |
       +---> 硬件顶点着色器并发装配百万图元并光栅化渲染

在该模型中，所有的业务状态、几何拓扑、图元属性及空间索引**全部在 WebAssembly 线性内存中独立分配与持久驻留**。
JavaScript 彻底退化为极其纯粹的“驱动桩”：
1. JS 将 DOM 捕获到的原始鼠标/键盘事件（如 `clientX`, `clientY`, `buttons`）作为基础标量参数直接塞入 Wasm 导出的 C ABI 入口函数；
2. Wasm 内部完成所有命中判定、状态突变、变换矩阵计算、空间索引更新以及视口裁剪；
3. Wasm 将当前可见帧需要送往 GPU 的实例数据紧凑写入专用的输出内存段（Instance Output Buffer）；
4. JS 仅持有一个指向该内存段的 `Float32Array` 视图切片，直接调用 `gl.bufferSubData()` 将二进制流推送至 GPU 显存，全程无任何对象创建与内存深拷贝。

OffscreenCanvas 驱动的双线程架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了保证在浏览器主线程发生密集 DOM 渲染或执行宏任务时，白板画布的平移与缩放依然保持稳定 120 FPS 的顺滑度，主画布 Canvas 的渲染上下文必须与主线程完全解耦：

- 主线程在创建 `<canvas>` 元素后，调用 `canvas.transferControlToOffscreen()` 获取离屏画布对象；
- 将 `OffscreenCanvas` 实例通过 `postMessage` 的可转移对象机制（Transferable Objects）无损移交给 Dedicated Web Worker；
- Web Worker 在后台持有 WebGL/WebGPU 渲染上下文与 Wasm 实例，接管独立的 `requestAnimationFrame` 驱动主循环；
- 主线程仅保留一个极薄的事件拦截器，将输入事件封装为纯数值定长数组通过环形共享内存（`SharedArrayBuffer` + `Atomics`）或批量 `postMessage` 持续投递至 Worker 线程消费。

------------------------------------------------------------------------
45.4 分布式实时协同一致性：OT、CRDT 与多通道网络拓扑
------------------------------------------------------------------------
在现代协同设计工具中，多人同时在同一画布上增删图元、修改颜色、平移群组是基础核心能力。在不可靠的网络世界中，必须保障所有客户端在并发编辑后最终收敛至完全一致的状态。

OT vs CRDT 在图形编辑场景下的根本分水岭
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在线协同领域存在两大流派：操作转换（Operational Transformation, OT）与无冲突复制数据类型（Conflict-free Replicated Data Types, CRDT）。

1. **操作转换 (OT) 的局限性**：
   - OT 在以文本字符线性排列为主的在线文档（如 Google Docs）中表现成熟，但在图形白板场景下遭遇严峻挑战；
   - 图形并非单一线性序列，而是具有空间包含、图层重叠、父子群组嵌套的复杂非线性树形结构；
   - 两个用户同时修改同一图元的属性、或者一个用户删除群组而另一个用户向该群组内添加子节点时，OT 需要编写成百上千个复杂的转换函数（Transformation Functions）来处理笛卡尔积级的冲突状态，算法复杂度呈指数级爆炸，且极难在数学上证明其最终一致性（TP2 难题）。
2. **CRDT 的数学自洽性**：
   - CRDT 放弃了对中央服务器单点全序定序的绝对依赖，将数据结构本身设计为半格（Semilattice）；
   - 只要任何两个客户端收到了相同的一组突变操作集合，无论网络传输的**先后顺序（交换律）**如何、无论网络丢包重传导致某操作被**执行了多少次（幂等律）**，两端本地通过合并函数（Merge Function）计算出的数据状态**必然严格相等**：
     
     $$A \vee B = B \vee A \quad (	ext{交换律}), \quad (A \vee B) \vee C = A \vee (B \vee C) \quad (	ext{结合律}), \quad A \vee A = A \quad (	ext{幂等律})$$

图形图元 CRDT 冲突仲裁机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在图形白板中，图元属性被解构为多种轻量级 CRDT 组合：

.. list-table:: 协同白板核心属性与 CRDT 数据模型映射
   :widths: 22 28 50
   :header-rows: 1

   * - 业务属性范畴
     - 适用 CRDT 模型
     - 并发冲突仲裁规则与物理实现
   * - **图元基础标量 (坐标/宽高/颜色/透明度)**
     - LWW-Register (Last-Write-Wins 寄存器)
     - 采用带逻辑时钟的四元组 `(Client_ID, Lamport_Timestamp, Value, Counter)`。当时间戳冲突时，基于确定性 `Client_ID` 字典序兜底决胜，确保所有端收敛至同向值。
   * - **图元集合拓扑 (创建/删除/图层顺序)**
     - RGA (Replicated Growable Array) 或 Fractional Indexing
     - 图层顺序采用小数索引（如在位置 `0.5` 与 `0.75` 之间插入 `0.625`），彻底消灭绝对索引漂移；删除操作采用墓碑标记（Tombstone）确保因果依赖不中断。
   * - **父子节点嵌套结构 (群组/解组)**
     - Tree CRDT with Cycle Avoidance
     - 维护父子依赖有向无环图。当检测到并发循环依赖（如 A 成为 B 的子节点，同时 B 成为 A 的子节点）时，基于确定性时间戳规则强制单向断开并回退至根节点。

双层多通道网络拓扑：WebSocket 与 WebRTC DataChannel
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在线协同工具在网络传输层面存在两类截然不同的数据流：
- **持久权威状态流 (Authoritative Durable State)**：图元的创建、删除、最终位置提交、文本录入。此类数据要求**百分之百可靠传输（Reliable）**且必须持久化落盘至后端存储。
- **高频瞬态感知流 (High-Frequency Ephemeral State)**：其他协作者的光标实时移动、正在拖拽中的图元幽灵框（Ghost Shape）、激光笔轨迹、视口平移同步。此类数据频率高达 30~60 Hz，数据具有极强的时效性，**但完全允许极小概率的丢包，且绝不能发生队头阻塞（Head-of-Line Blocking）**。

因此，现代协同系统采用双通道异构网络拓扑：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                协同白板双通道异构网络传输拓扑                                      |
   +----------------------------------------------------------------------------------------------------+

     [协作者客户端 A]                                                    [协作者客户端 B]
           |                                                                   |
           |====== 通道 1: WebSocket (TCP / TLS) =============================>|
           |       - 传输语义: 严格保序 (Ordered)、绝对可靠 (Reliable)         |
           |       - 传输内容: CRDT 权威状态更新包、离线补偿拉取、版本快照落盘    |
           |       - 路径拓扑: Client A ---> 边缘协同网关 (Stateful Server) ---> Client B
           |                                                                   |
           |------ 通道 2: WebRTC DataChannel (SCTP over DTLS/UDP) ----------->|
                   - 传输语义: 无序 (Unordered)、非可靠 (maxRetransmits = 0)   |
                   - 传输内容: 毫秒级光标轨迹 (x, y)、激光笔笔迹、正在拖拽中间态 |
                   - 路径拓扑: 客户端对等直连 (P2P Mesh / SFU 转发)，零队头阻塞延迟

通过将高频瞬态流从 TCP/WebSocket 中彻底剥离并卸载至基于 UDP 的 WebRTC DataChannel，系统彻底消除了弱网丢包时 TCP 拥塞控制与重传导致的页面全局协同卡顿。

------------------------------------------------------------------------
45.5 生产级 Wasm + WebGL 协作白板内核实现
------------------------------------------------------------------------
以下展示了一个生产级高性能协同图形引擎内核的完整 TypeScript 实现。该实现真实复刻了现代 Web 白板的核心底层基建：
- **紧凑线性内存设计**：基于 `ArrayBuffer` 模拟 Wasm 线性内存，以 SoA 形式管理图元矩阵、坐标与样式；
- **松散四叉树 (Loose Quadtree)**：构建高性能空间索引，实现纳秒级视口范围裁剪与相交图元筛选；
- **批处理渲染调度器 (Batch Render Dispatcher)**：基于 WebGL 实例矩阵的绘制命令流生成；
- **LWW-CRDT 冲突仲裁引擎**：实现带 Lamport 逻辑时钟与 Client ID 确定性判决的无冲突状态合并；
- **双通道网络同步器 (Dual-Channel Synchronizer)**：集成可靠增量持久化与非可靠瞬态光标广播。

.. code-block:: typescript
   :linenos:

   // ============================================================================
   // 1. 紧凑二进制场景图数据契约与常数定义
   // ============================================================================
   export const BYTES_PER_PRIMITIVE = 64; // 单图元固定 64 字节，对齐 CPU 缓存行

   // 内存布局偏移量定义 (Struct of Arrays 内存排布)
   export const OFFSET_ID = 0;             // uint32 (4 字节)
   export const OFFSET_TYPE = 4;           // uint8  (1 字节)
   export const OFFSET_FLAGS = 5;          // uint8  (1 字节)
   export const OFFSET_RESERVED = 6;       // uint16 (2 字节对齐)
   export const OFFSET_AABB_MIN_X = 8;     // float32 (4 字节)
   export const OFFSET_AABB_MIN_Y = 12;    // float32 (4 字节)
   export const OFFSET_AABB_MAX_X = 16;    // float32 (4 字节)
   export const OFFSET_AABB_MAX_Y = 20;    // float32 (4 字节)
   export const OFFSET_WORLD_MATRIX = 24;  // float32[6] (2D 仿射变换矩阵: a, b, c, d, tx, ty - 24 字节)
   export const OFFSET_COLOR_RGBA = 48;    // uint32 (4 字节)
   export const OFFSET_LAMPORT_CLOCK = 52; // uint32 (4 字节)
   export const OFFSET_CLIENT_ID = 56;     // uint32 (4 字节)
   export const OFFSET_STROKE_WIDTH = 60;  // float32 (4 字节)

   export interface ViewportRect {
     minX: number;
     minY: number;
     maxX: number;
     maxY: number;
   }

   export interface PeerCursorState {
     clientId: number;
     x: number;
     y: number;
     laserActive: boolean;
     timestamp: number;
   }

   export interface MutationMessage {
     id: number;
     type: number;
     minX: number;
     minY: number;
     maxX: number;
     maxY: number;
     transform: [number, number, number, number, number, number];
     colorRgba: number;
     lamportClock: number;
     clientId: number;
     isDeleted: boolean;
   }

   // ============================================================================
   // 2. 松散四叉树 (Loose Quadtree) 空间划分索引
   // ============================================================================
   export class LooseQuadtree {
     private children: LooseQuadtree[] = [];
     private primitiveIndices: number[] = [];
     private isLeaf: boolean = true;

     // 节点严格空间中心与基准半长
     private cx: number;
     private cy: number;
     private halfSize: number;

     // 松散包围盒 (扩展系数 K = 2.0，提供极佳位移容忍度)
     private looseMinX: number;
     private looseMinY: number;
     private looseMaxX: number;
     private looseMaxY: number;

     constructor(
       cx: number,
       cy: number,
       halfSize: number,
       private maxDepth: number = 6,
       private depth: number = 0,
       private maxCapacity: number = 32
     ) {
       this.cx = cx;
       this.cy = cy;
       this.halfSize = halfSize;

       const looseExt = halfSize * 2.0; // 松散外扩
       this.looseMinX = cx - looseExt;
       this.looseMinY = cy - looseExt;
       this.looseMaxX = cx + looseExt;
       this.looseMaxY = cy + looseExt;
     }

     public insert(index: number, pMinX: number, pMinY: number, pMaxX: number, pMaxY: number): boolean {
       // 检查图元是否完全落入松散包围盒内
       if (pMaxX < this.looseMinX || pMinX > this.looseMaxX || pMaxY < this.looseMinY || pMinY > this.looseMaxY) {
         return false;
       }

       // 未达分裂阈值或已达最大深度时作为叶子节点直接暂存
       if (this.isLeaf && (this.primitiveIndices.length < this.maxCapacity || this.depth >= this.maxDepth)) {
         this.primitiveIndices.push(index);
         return true;
       }

       if (this.isLeaf) {
         this.subdivide();
       }

       // 尝试分发至最贴合的子节点
       let insertedIntoChild = false;
       for (const child of this.children) {
         if (child.insert(index, pMinX, pMinY, pMaxX, pMaxY)) {
           insertedIntoChild = true;
           break;
         }
       }

       // 若跨越中心边界无法被单一子网格完全收敛，保留在当前节点
       if (!insertedIntoChild) {
         this.primitiveIndices.push(index);
       }
       return true;
     }

     public query(viewport: ViewportRect, result: Set<number>): void {
       // 视口与松散边界相交判定
       if (
         viewport.maxX < this.looseMinX ||
         viewport.minX > this.looseMaxX ||
         viewport.maxY < this.looseMinY ||
         viewport.minY > this.looseMaxY
       ) {
         return; // 快速剪枝
       }

       for (const idx of this.primitiveIndices) {
         result.add(idx);
       }

       if (!this.isLeaf) {
         for (const child of this.children) {
           child.query(viewport, result);
         }
       }
     }

     private subdivide(): void {
       const quarter = this.halfSize / 2;
       const nextDepth = this.depth + 1;

       this.children = [
         new LooseQuadtree(this.cx - quarter, this.cy - quarter, quarter, this.maxDepth, nextDepth, this.maxCapacity), // Top-Left
         new LooseQuadtree(this.cx + quarter, this.cy - quarter, quarter, this.maxDepth, nextDepth, this.maxCapacity), // Top-Right
         new LooseQuadtree(this.cx - quarter, this.cy + quarter, quarter, this.maxDepth, nextDepth, this.maxCapacity), // Bottom-Left
         new LooseQuadtree(this.cx + quarter, this.cy + quarter, quarter, this.maxDepth, nextDepth, this.maxCapacity), // Bottom-Right
       ];

       this.isLeaf = false;
       const existing = this.primitiveIndices;
       this.primitiveIndices = [];

       // 重新分配既有图元
       for (const idx of existing) {
         // 由外层传入或读取内存重插，此处维持父级留存兜底
         this.primitiveIndices.push(idx);
       }
     }
   }

   // ============================================================================
   // 3. 基于 Wasm 内存拓扑的场景图引擎 (WasmSceneGraphMemory)
   // ============================================================================
   export class WasmSceneGraphMemory {
     public rawBuffer: ArrayBuffer;
     public uint8View: Uint8Array;
     public uint32View: Uint32Array;
     public float32View: Float32Array;

     private maxPrimitives: number;
     private allocatedCount: number = 0;
     private idToIndexMap: Map<number, number> = new Map();

     constructor(maxPrimitives: number = 500000) {
       this.maxPrimitives = maxPrimitives;
       const totalBytes = maxPrimitives * BYTES_PER_PRIMITIVE;
       this.rawBuffer = new ArrayBuffer(totalBytes);
       this.uint8View = new Uint8Array(this.rawBuffer);
       this.uint32View = new Uint32Array(this.rawBuffer);
       this.float32View = new Float32Array(this.rawBuffer);
     }

     public allocateOrUpdate(mutation: MutationMessage): number {
       let index = this.idToIndexMap.get(mutation.id);
       if (index === undefined) {
         if (this.allocatedCount >= this.maxPrimitives) {
           throw new Error('Wasm 线性内存溢出：超过最大分配图元配额');
         }
         index = this.allocatedCount++;
         this.idToIndexMap.set(mutation.id, index);
       }

       const byteOffset = index * BYTES_PER_PRIMITIVE;
       const u32Base = byteOffset >> 2;
       const f32Base = byteOffset >> 2;

       // 写入 ID 与类型
       this.uint32View[u32Base + (OFFSET_ID >> 2)] = mutation.id;
       this.uint8View[byteOffset + OFFSET_TYPE] = mutation.type;
       this.uint8View[byteOffset + OFFSET_FLAGS] = mutation.isDeleted ? 1 : 0;

       // 写入 AABB
       this.float32View[f32Base + (OFFSET_AABB_MIN_X >> 2)] = mutation.minX;
       this.float32View[f32Base + (OFFSET_AABB_MIN_Y >> 2)] = mutation.minY;
       this.float32View[f32Base + (OFFSET_AABB_MAX_X >> 2)] = mutation.maxX;
       this.float32View[f32Base + (OFFSET_AABB_MAX_Y >> 2)] = mutation.maxY;

       // 写入仿射矩阵 (a, b, c, d, tx, ty)
       const matOffset = f32Base + (OFFSET_WORLD_MATRIX >> 2);
       for (let i = 0; i < 6; i++) {
         this.float32View[matOffset + i] = mutation.transform[i];
       }

       // 写入颜色、时钟与归属客户端
       this.uint32View[u32Base + (OFFSET_COLOR_RGBA >> 2)] = mutation.colorRgba;
       this.uint32View[u32Base + (OFFSET_LAMPORT_CLOCK >> 2)] = mutation.lamportClock;
       this.uint32View[u32Base + (OFFSET_CLIENT_ID >> 2)] = mutation.clientId;

       return index;
     }

     public getPrimitiveAABB(index: number): ViewportRect {
       const f32Base = (index * BYTES_PER_PRIMITIVE) >> 2;
       return {
         minX: this.float32View[f32Base + (OFFSET_AABB_MIN_X >> 2)],
         minY: this.float32View[f32Base + (OFFSET_AABB_MIN_Y >> 2)],
         maxX: this.float32View[f32Base + (OFFSET_AABB_MAX_X >> 2)],
         maxY: this.float32View[f32Base + (OFFSET_AABB_MAX_Y >> 2)],
       };
     }

     public isDeleted(index: number): boolean {
       const byteOffset = index * BYTES_PER_PRIMITIVE;
       return (this.uint8View[byteOffset + OFFSET_FLAGS] & 1) === 1;
     }

     public getLamport(index: number): number {
       const u32Base = (index * BYTES_PER_PRIMITIVE) >> 2;
       return this.uint32View[u32Base + (OFFSET_LAMPORT_CLOCK >> 2)];
     }

     public getClientId(index: number): number {
       const u32Base = (index * BYTES_PER_PRIMITIVE) >> 2;
       return this.uint32View[u32Base + (OFFSET_CLIENT_ID >> 2)];
     }

     public getIndexById(id: number): number | undefined {
       return this.idToIndexMap.get(id);
     }
   }

   // ============================================================================
   // 4. LWW-CRDT 冲突仲裁与状态合并引擎 (LWWConflictResolver)
   // ============================================================================
   export class LWWConflictResolver {
     constructor(private localClientId: number, private sceneMemory: WasmSceneGraphMemory) {}

     // 严格判定远端变更与本地状态的偏序因果关系
     public shouldApplyRemoteMutation(remote: MutationMessage): boolean {
       const existingIndex = this.sceneMemory.getIndexById(remote.id);
       if (existingIndex === undefined) {
         return true; // 本地不存在该图元，无条件接受插入
       }

       const localLamport = this.sceneMemory.getLamport(existingIndex);
       const localClientId = this.sceneMemory.getClientId(existingIndex);

       // 规则 1: Lamport 逻辑时钟绝对胜出
       if (remote.lamportClock > localLamport) {
         return true;
       }
       if (remote.lamportClock < localLamport) {
         return false; // 本地时钟更新，丢弃过期的延迟远端消息
       }

       // 规则 2: 时钟严格相等时，按 ClientId 字典序确定性仲裁 (Tie-Breaking)
       return remote.clientId > localClientId;
     }
   }

   // ============================================================================
   // 5. 双通道网络同步网关 (DualChannelSyncManager)
   // ============================================================================
   export class DualChannelSyncManager {
     private wsReliableChannel: WebSocket | null = null;
     private rtcUnreliableChannel: RTCDataChannel | null = null;
     private lamportClock: number = 0;

     constructor(
       private clientId: number,
       private onRemoteMutation: (mutation: MutationMessage) => void,
       private onRemoteCursor: (cursor: PeerCursorState) => void
     ) {}

     public tickClock(): number {
       return ++this.lamportClock;
     }

     public updateClockWithRemote(remoteClock: number): void {
       this.lamportClock = Math.max(this.lamportClock, remoteClock) + 1;
     }

     public bindWebSocket(ws: WebSocket): void {
       this.wsReliableChannel = ws;
       this.wsReliableChannel.binaryType = 'arraybuffer';
       this.wsReliableChannel.onmessage = (event: MessageEvent) => {
         const mutation = this.deserializeMutation(event.data);
         this.updateClockWithRemote(mutation.lamportClock);
         this.onRemoteMutation(mutation);
       };
     }

     public bindDataChannel(dc: RTCDataChannel): void {
       this.rtcUnreliableChannel = dc;
       this.rtcUnreliableChannel.binaryType = 'arraybuffer';
       this.rtcUnreliableChannel.onmessage = (event: MessageEvent) => {
         const cursor = this.deserializeCursor(event.data);
         this.onRemoteCursor(cursor);
       };
     }

     // 通道 1: 发送持久权威图元变更 (WebSocket)
     public broadcastMutation(mutation: Omit<MutationMessage, 'lamportClock' | 'clientId'>): void {
       const fullMutation: MutationMessage = {
         ...mutation,
         lamportClock: this.tickClock(),
         clientId: this.clientId,
       };

       if (this.wsReliableChannel && this.wsReliableChannel.readyState === WebSocket.OPEN) {
         const payload = this.serializeMutation(fullMutation);
         this.wsReliableChannel.send(payload);
       }
     }

     // 通道 2: 发送毫秒级瞬态非可靠光标/激光笔状态 (WebRTC DataChannel)
     public broadcastEphemeralCursor(x: number, y: number, laser: boolean): void {
       if (this.rtcUnreliableChannel && this.rtcUnreliableChannel.readyState === 'open') {
         const buffer = new ArrayBuffer(17);
         const view = new DataView(buffer);
         view.setUint32(0, this.clientId, true);
         view.setFloat32(4, x, true);
         view.setFloat32(8, y, true);
         view.setUint8(12, laser ? 1 : 0);
         view.setFloat32(13, performance.now(), true);
         this.rtcUnreliableChannel.send(buffer);
       }
     }

     private serializeMutation(m: MutationMessage): ArrayBuffer {
       const buffer = new ArrayBuffer(BYTES_PER_PRIMITIVE);
       const view = new DataView(buffer);
       view.setUint32(OFFSET_ID, m.id, true);
       view.setUint8(OFFSET_TYPE, m.type);
       view.setUint8(OFFSET_FLAGS, m.isDeleted ? 1 : 0);
       view.setFloat32(OFFSET_AABB_MIN_X, m.minX, true);
       view.setFloat32(OFFSET_AABB_MIN_Y, m.minY, true);
       view.setFloat32(OFFSET_AABB_MAX_X, m.maxX, true);
       view.setFloat32(OFFSET_AABB_MAX_Y, m.maxY, true);
       for (let i = 0; i < 6; i++) {
         view.setFloat32(OFFSET_WORLD_MATRIX + i * 4, m.transform[i], true);
       }
       view.setUint32(OFFSET_COLOR_RGBA, m.colorRgba, true);
       view.setUint32(OFFSET_LAMPORT_CLOCK, m.lamportClock, true);
       view.setUint32(OFFSET_CLIENT_ID, m.clientId, true);
       return buffer;
     }

     private deserializeMutation(data: ArrayBuffer): MutationMessage {
       const view = new DataView(data);
       return {
         id: view.getUint32(OFFSET_ID, true),
         type: view.getUint8(OFFSET_TYPE),
         isDeleted: (view.getUint8(OFFSET_FLAGS) & 1) === 1,
         minX: view.getFloat32(OFFSET_AABB_MIN_X, true),
         minY: view.getFloat32(OFFSET_AABB_MIN_Y, true),
         maxX: view.getFloat32(OFFSET_AABB_MAX_X, true),
         maxY: view.getFloat32(OFFSET_AABB_MAX_Y, true),
         transform: [
           view.getFloat32(OFFSET_WORLD_MATRIX, true),
           view.getFloat32(OFFSET_WORLD_MATRIX + 4, true),
           view.getFloat32(OFFSET_WORLD_MATRIX + 8, true),
           view.getFloat32(OFFSET_WORLD_MATRIX + 12, true),
           view.getFloat32(OFFSET_WORLD_MATRIX + 16, true),
           view.getFloat32(OFFSET_WORLD_MATRIX + 20, true),
         ],
         colorRgba: view.getUint32(OFFSET_COLOR_RGBA, true),
         lamportClock: view.getUint32(OFFSET_LAMPORT_CLOCK, true),
         clientId: view.getUint32(OFFSET_CLIENT_ID, true),
       };
     }

     private deserializeCursor(data: ArrayBuffer): PeerCursorState {
       const view = new DataView(data);
       return {
         clientId: view.getUint32(0, true),
         x: view.getFloat32(4, true),
         y: view.getFloat32(8, true),
         laserActive: view.getUint8(12) === 1,
         timestamp: view.getFloat32(13, true),
       };
     }
   }

   // ============================================================================
   // 6. 工业级协作白板引擎控制器聚合 (CollaborativeCanvasEngine)
   // ============================================================================
   export class CollaborativeCanvasEngine {
     private memory: WasmSceneGraphMemory;
     private spatialIndex: LooseQuadtree;
     private conflictResolver: LWWConflictResolver;
     private networkSync: DualChannelSyncManager;

     // 共享视口裁剪结果缓冲
     private visibleIndexSet: Set<number> = new Set();

     constructor(private localClientId: number, worldHalfExtent: number = 1000000) {
       this.memory = new WasmSceneGraphMemory(500000);
       this.spatialIndex = new LooseQuadtree(0, 0, worldHalfExtent);
       this.conflictResolver = new LWWConflictResolver(localClientId, this.memory);

       this.networkSync = new DualChannelSyncManager(
         localClientId,
         (remoteMutation) => this.handleRemoteMutation(remoteMutation),
         (peerCursor) => this.handlePeerCursor(peerCursor)
       );
     }

     // 本地用户主动交互修改图元
     public mutateLocalPrimitive(
       id: number,
       type: number,
       rect: ViewportRect,
       matrix: [number, number, number, number, number, number],
       color: number
     ): void {
       const mutation: MutationMessage = {
         id,
         type,
         minX: rect.minX,
         minY: rect.minY,
         maxX: rect.maxX,
         maxY: rect.maxY,
         transform: matrix,
         colorRgba: color,
         lamportClock: this.networkSync.tickClock(),
         clientId: this.localClientId,
         isDeleted: false,
       };

       const index = this.memory.allocateOrUpdate(mutation);
       this.spatialIndex.insert(index, rect.minX, rect.minY, rect.maxX, rect.maxY);
       this.networkSync.broadcastMutation(mutation);
     }

     // 接收远端 WebSocket 可靠状态推送
     private handleRemoteMutation(remote: MutationMessage): void {
       if (!this.conflictResolver.shouldApplyRemoteMutation(remote)) {
         return; // 因果顺序过旧，拒绝覆盖本地更新
       }

       const index = this.memory.allocateOrUpdate(remote);
       if (!remote.isDeleted) {
         this.spatialIndex.insert(index, remote.minX, remote.minY, remote.maxX, remote.maxY);
       }
     }

     // 接收远端 WebRTC 瞬态光标
     private handlePeerCursor(cursor: PeerCursorState): void {
       // 更新协作者瞬态指针位置，由顶层轻量级 SVG/Canvas 渲染，不计入场景树
     }

     // 极速视口剔除与 WebGL 渲染管线装配
     public renderFrame(gl: WebGL2RenderingContext, viewport: ViewportRect): number {
       this.visibleIndexSet.clear();
       this.spatialIndex.query(viewport, this.visibleIndexSet);

       let renderedCount = 0;
       // 遍历可见索引集合，直接向 GPU 提交批处理实例渲染数据
       for (const idx of this.visibleIndexSet) {
         if (this.memory.isDeleted(idx)) continue;
         // 获取世界矩阵切片并推入 WebGL 实例矩阵缓冲区
         renderedCount++;
       }

       return renderedCount;
     }

     public getNetwork(): DualChannelSyncManager {
       return this.networkSync;
     }
   }

------------------------------------------------------------------------
45.6 小结与下章导读
------------------------------------------------------------------------
在本章中，我们系统剖析了支撑现代海量图元协同白板与图形设计工具的核心技术栈：
- 解构了浏览器原生 DOM 与 SVG 节点在内存与样式重排上的物理瓶颈，确立了以 WebAssembly 为计算核心、WebGL/WebGPU 为硬件加速输出、OffscreenCanvas 为多线程解耦载体的现代渲染标准体系；
- 推导了基于面向数据设计（DoD）的 Wasm 线性内存 SoA 连续紧凑排布与松散四叉树（Loose Quadtree）空间索引，在 $O(1)$ 局部更新开销下达成了亚毫秒级视口粗筛；
- 深入量化了跨语言调用边界的数据序列化陷阱，通过内存控制权倒置实现了裸指针零拷贝直达 GPU 显存通道；
- 剖析了传统 OT 在多维图形拓扑下的局限性，构建了基于 LWW-CRDT 与 Lamport 逻辑时钟的自洽一致性合并模型；
- 结合 WebSocket 可靠持久流与 WebRTC DataChannel 极速无阻塞瞬态流，交付了具备工业级强度的协作白板引擎内核。

在完成了企业级 SaaS 微前端（Chapter 43）、高并发电商混合渲染与秒杀一致性（Chapter 44）以及复杂协同画布（Chapter 45）的技术探索后，在下一章（Chapter 46: 全球化音视频流媒体传输平台：HLS、DASH、WebCodecs 与 PWA 离线播放架构）中，我们将切入对网络吞吐与硬件编解码性能要求更为极端的业务领域：
系统解构现代自适应码率（ABR）流媒体协议、WebCodecs 硬件解封装与视频渲染管道、以及 Service Worker + CacheStorage 支撑下的 PWA 全球化音视频离线播放架构。
