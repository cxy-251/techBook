========================================================================
Chapter 37: 显存管理与资源屏障：虚拟显存分页、UAV 冒险、Pipeline Barriers 与内存别名
========================================================================

.. note:: 前置背景与认知承接
   在 Chapter 36 中，我们系统解构了现代显式图形 API（Direct3D 12、Vulkan 与 Metal）的架构范式转移。通过将设备、多引擎硬件队列、多线程命令列表与不可变管线状态对象（PSO）全盘暴露，显式 API 终结了传统驱动黑盒中沉重的状态脏检查与全局锁同步，赋予了应用程序近乎原生的硬件控制能力。

   然而，这种底层控制权的反转带来了一项极为严苛的系统级责任：**硬件不再提供任何自动的“保姆式”安全保障**。在传统 Direct3D 11 或 OpenGL 中，驱动程序会在后台隐式追踪每个缓冲区的读写依赖，自动执行资源重命名（Ghosting）以规避危害，并在上下文内部自动插入流水线排空与缓存同步。而在现代显式 API 中，如果应用程序未在正确的时机、正确的管线阶段向 GPU 发送精确的**资源屏障（Resource Barriers）**与**内存可见性指令（Memory Visibility Operations）**，GPU 乱序高度并发的硬件着色核心与分级缓存拓扑将立即引发写后读（RAW）、写后写（WAW）数据冒险，导致画面闪烁、贴图黑块、几何拓扑破损乃至显卡驱动崩溃（TDR）。此外，频繁调用操作系统内核接口分配显存不仅会导致巨额 CPU 耗时，更会引发严重的虚拟地址空间碎片化。

   本章作为现代底层 API 演进的核心深水区，将深入 GPU 内存子系统内部，全面剖析 GPU 虚拟内存分页、工业级子分配器（Suballocator）架构、流水线屏障与缓存刷新的物理本质、UAV 读写冒险规避，以及利用内存别名（Memory Aliasing）大幅压缩帧峰值显存的工业实战。

------------------------------------------------------------------------
37.1 GPU 虚拟内存架构与物理显存分页模型 (GVM & Suballocation)
------------------------------------------------------------------------

GPU 内存管理单元 (GMMU) 与多级页表
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
现代独立显卡与移动 SoC 内部均集成了专用的硬件**图形内存管理单元（Graphics MMU - GMMU）**。正如 CPU 操作系统通过虚拟内存隔离各个进程，GPU 同样构建于**GPU 虚拟地址空间（GPU Virtual Address - GPU VA）**之上（现代桌面 GPU 通常支持 48 位或 49 位虚拟地址空间）：

- **GMMU 多级页表拓扑**：GMMU 采用 4 级或 5 级分页结构（包含页全局目录 PGD、上级目录 PUD、中级目录 PMD 与页表 PT）。
- **页面尺寸（Page Size）**：标准基本页为 4KB，而对于大体积贴图与连续缓冲区，GMMU 广泛支持 64KB、2MB 甚至更大尺寸的大页（Huge Pages），以大幅提高 GPU TLB（Translation Lookaside Buffer）的命中率，降低访存发散时的页表遍历（Page Walk）时延。
- **设备物理内存分类**：物理显存池在硬件层面被精确划分为不同物理属性的堆（Heaps）：
  1. **Device-Local 堆**：直接位于板载高带宽显存（GDDR6 / HBM2e）中，GPU 拥有数 TB/s 的吞吐访问权限，但 CPU 无法直接寻址（除非通过 ReBAR 窗口）；
  2. **Host-Visible / Upload 堆**：物理驻留在主机系统内存（Host RAM）中，或者通过 PCIe 总线的 **Resizable BAR (ReBAR)** 机制直接暴露给 CPU 物理寻址，用于 CPU 向 GPU 频繁推送常量、骨骼变换矩阵与动态顶点；
  3. **Host-Cached / Readback 堆**：支持 CPU 缓存读取的系统内存，用于 GPU 向主机回读计算结果、包围盒碰撞测试数据或屏幕截图。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     GPU 虚拟内存 (GVM) 多级页表与物理堆拓扑               |
   +-------------------------------------------------------------------------+

      [ 着色器核心发出的 48-bit GPU Virtual Address (GPU VA) ]
             |
             v
      [ 片上 GMMU TLB 缓存 ] ===(命中)===> 直接获取物理显存帧地址 (Physical Frame)
             |
             v (TLB 未命中，触发硬件 Page Walk)
      +---------------------------------------------------------------------+
      | 4 级页表遍历: PML4 -> PDPT -> Page Directory (PDE) -> Page Table (PTE) |
      +---------------------------------------------------------------------+
             |
             +-----------------------+-----------------------+
             |                       |                       |
             v (映射物理页)           v (映射物理页)           v (跨 PCIe 映射)
      [ 板载 VRAM: Device-Local ] [ 开启 ReBAR 的 VRAM ]   [ 主机内存: Host-Visible ]
      - 纹理 / G-Buffer / 深度   - 动态常量 / 每帧几何     - Staging Upload 缓冲区
      - 峰值带宽: 1~3 TB/s       - CPU/GPU 均可直接读写    - 穿透 PCIe 总线: 32~64 GB/s

为什么必须自建子分配器 (Suballocator)？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在显式 API 中，直接向系统驱动申请显存（Vulkan 的 `vkAllocateMemory` 或 D3D12 的 `CreateHeap`）存在致命的工程物理限制：

1. **操作系统内核调用开销巨额**：每次显存分配都会穿透用户态驱动（UMD）陷入内核态驱动（KMD），触发操作系统的显存虚拟内存映射、VRAM 物理页分配与安全擦除（Zero-filling）。单次调用耗时通常在几十微秒到数毫秒不等；
2. **底层分配次数存在硬性上限**：Vulkan 规范明确规定，硬件设备允许的最大分配句柄总数（`maxMemoryAllocationCount`）通常被限制在 **4096** 甚至更低。如果一个大型 3D 场景为成千上万个网格、材质贴图各自分配独立的内存块，API 将迅速耗尽配额崩溃；
3. **显存碎片化（External Fragmentation）**：频繁申请和销毁不同尺寸的物理内存块，会导致 GPU 虚拟地址空间与物理 VRAM 产生严重的不可利用碎片。

工业级两级显存分配架构 (Two-Level Suballocation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
现代工业级渲染引擎（如 Unreal Engine、Frostbite 或自研 3D 引擎）普遍在引擎底层实现自建的显存管理子系统（如集成 **Vulkan Memory Allocator (VMA)** 或 **D3D12MemoryAllocator (D3D12MA)**）：

- **巨页块池化（Block Pooling）**：引擎首先向底层 API 一次性申请若干块体积巨大的连续物理内存堆（例如每个 Block 为 64MB、128MB 或 256MB）；
- **TLSF / Buddy 算法细粒度切分**：在应用层用户态内存中，采用 **双层分离适合（Two-Level Segregated Fit - TLSF）** 或 **伙伴分配器（Buddy Allocator）**，在几纳秒的时间内将大块内存切分出满足特定对齐要求（如 256B 对齐、64KB 纹理对齐）的细小子区间（Sub-allocations）；
- **环形缓冲区（Ring / Linear Staging Buffer）**：针对每帧更新后立刻废弃的临时数据（如骨骼蒙皮矩阵、UI 顶点），构建专用的环形队列，仅通过推移指针实现零碎片、常数级时延的极速分配。

.. list-table:: 现代底层显存分配策略与微架构特征
   :widths: 20 25 30 25
   :header-rows: 1
   :class: tight-table

   * - 显存分配模式
     - 适用资源类型
     - 算法架构与物理开销
     - 碎片化与对齐风险
   * - **专用系统分配 (Dedicated Allocation)**
     - 全屏 G-Buffer、主深度缓冲区、巨型虚拟纹理物理池
     - 直接调用 `vkAllocateMemory`，完全独占底层页表，驱动开销大
     - 零内部碎片，由 GPU 驱动独占优化
   * - **TLSF 通用子分配 (TLSF Suballocation)**
     - 静态网格顶点/索引缓冲区、普通材质纹理、骨骼网格
     - $O(1)$ 查找时间，位图二分索引，在 128MB 物理 Block 内动态划分
     - 极低外部碎片，需严格保障 64KB 纹理或 256B 缓冲区物理对齐
   * - **线性环形分配 (Ring / Linear Buffer)**
     - 每帧动态常量（Per-Frame CBV）、动态粒子顶点流
     - 纯指针累加与环形取模，配合三缓冲 Fence 批量复用，零内存锁
     - 零碎片；需严格防止 CPU 写入覆盖 GPU 正在读取的在途帧区间

------------------------------------------------------------------------
37.2 显存冒险物理机理：RAW、WAR、WAW 与缓存拓扑
------------------------------------------------------------------------

GPU 内部读写冒险的物理诱因
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为什么现代 GPU 极易产生数据冒险？其根本原因在于 GPU 硬件的**高度异步并行微架构**与**分级无一致性缓存网络**：

1. **执行重叠与乱序完成（Out-of-Order Execution）**：
   GPU 内部的数千个流处理器核心（ALU）是由成百上千个硬件线程束调度器（Warp/Wavefront Schedulers）自主驱动的。在管线中先后发射的两个绘制调用（Draw Call A 与 Draw Call B），其底层的线程束完全可能在硬件计算单元（SM/CU）中**交错重叠执行**。即使 Draw A 先进入硬件，Draw B 涉及的某些像素也有可能先于 Draw A 计算完毕并写回内存。
2. **多级专用缓存缺乏硬件全相干协议**：
   与 CPU 拥有庞大复杂的 MESI 硬件缓存一致性嗅探总线不同，GPU 为了将数十亿晶体管集中用于浮点算力与海量寄存器堆，**放弃了全硬件维护的跨引擎/跨核心缓存强一致性**。每个 SM 拥有私有的 L1 缓存、纹理缓存（Texture Cache）与共享内存（Shared Memory）；光栅化后端拥有私有的 ROP 颜色/深度缓存；而跨核心共享的 L2 缓存仅负责基础的聚合寻址。当一个阶段向 L2 写入数据时，另一个阶段私有 L1 缓存中保存的旧副本并不会被自动作废！

数据冒险的三大形式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当多个渲染或计算阶段先后访问同一块物理显存时，会产生以下三种危险模式：

- **写后读冒险（Read-After-Write - RAW）**：
  **图形系统中最致命、发生最频繁的冒险**。前序阶段负责写入数据，后序阶段负责读取该数据。例如：
  - Compute Shader 写入一张 Bloom 模糊高光纹理，后续像素着色器必须采样该纹理；
  - 阴影 Pass 写入 Shadow Map 深度缓冲，后续主场景光照着色器必须采样该深度贴图。
  **物理后果**：若无同步，后序读取阶段将启动于前序写入阶段完成之前，或者后序读取阶段从尚未刷新的旧缓存中读到了过期的脏数据，导致画面呈现剧烈的噪点闪烁或上一帧的残留残影。
- **写后写冒险（Write-After-Write - WAW）**：
  两个独立的管线阶段试图向同一块显存区域写入数据。
  **物理后果**：由于线程束调度时序的波动，后序阶段的数据可能先写入，随后被迟到的前序写入覆盖，导致最终存储状态完全颠倒混乱。
- **读后写冒险（Write-After-Read - WAR）**：
  前序阶段正在读取某缓冲区，后序阶段需要向该缓冲区写入新数据。
  **物理后果**：若后序写入过早执行并冲刷了物理内存，前序阶段的线程将读取到已被破坏的新数据。

缓存刷新（Flush）与作废（Invalidate）的物理本质
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
解决数据冒险必须在硬件电路上执行两个独立维度的同步动作：**执行依赖（Execution Dependency）**与**内存可见性（Memory Visibility）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             显存屏障 (Pipeline Barrier) 的硬件电路双重动作               |
   +-------------------------------------------------------------------------+

      [ 前序阶段: Compute Shader (SM 0) ]
        |-- 写入数据至本地 L1 Cache
        `-- (执行指令完成)
                 |
                 v 1. 执行依赖 (Execution Sync): 等待所有前序 SM 线程执行完毕
      ========================================================================
                 [ 屏障执行点: 硬件触发缓存冲刷与作废 (Cache Flush & Invalidate) ]
                 - Cache Flush: 将 SM 0 局部 L1/L2 脏数据写回全局内存 (Make Available)
                 - Cache Invalidate: 作废后续读取 SM 的 L1/Texture Cache (Make Visible)
      ========================================================================
                 |
                 v 2. 内存可见性 (Memory Visibility): 确保新数据进入统一物理层
      [ 后序阶段: Pixel Shader (SM 1) ]
        |-- 发现本地 L1 缓存已作废，强制从全局 L2/DRAM 加载最新数据
        `-- 正确采样读取，零冒险！

1. **执行同步（Execution Dependency）**：
   通知硬件调度器，暂停执行被标记为目标阶段（`dstStageMask`）的任务，直到所有标记为源阶段（`srcStageMask`）的在途指令完全执行完毕并退出管线。
2. **使数据可用（Make Available / Cache Flush）**：
   将源阶段所在计算核心或写出单元私有缓存（如 SM L1 缓存、ROP 颜色缓存）中的脏数据块（Dirty Cache Lines）**强制冲刷写回至全局可见的共享 L2 缓存或系统显存**中。
3. **使数据可见（Make Visible / Cache Invalidate）**：
   将目标阶段即将读取的计算核心私有缓存（如纹理缓存 Texture Cache、标量 L1 缓存）中的旧缓存行**强制标记为作废（Invalidate）**。当目标阶段发起读取请求时，硬件发现缓存失效，被迫重新从全局 L2 缓存或物理显存拉取最新数据。

------------------------------------------------------------------------
37.3 管线屏障 (Pipeline Barriers) 深度拆解
------------------------------------------------------------------------

阶段掩码 (Stage Mask) 与访问掩码 (Access Mask) 的精准契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在现代 API 中（如 Vulkan 1.3 的 `VkDependencyInfo` / Synchronization2，以及 Direct3D 12 的 Enhanced Barriers），管线屏障不再是一个模糊的“全局等待”，而是要求开发者精确声明四个物理参数：
- `srcStageMask`：必须在何种管线硬件阶段**全部完成**之后？
- `srcAccessMask`：前序阶段产生了何种类型的**内存写入**？
- `dstStageMask`：在何种管线硬件阶段**启动之前**进行拦截？
- `dstAccessMask`：后序阶段即将执行何种类型的**内存读取或写入**？

.. list-table:: 典型渲染场景下的工业级阶段与访问掩码对照矩阵
   :widths: 25 25 25 25
   :header-rows: 1
   :class: tight-table

   * - 典型渲染交互场景
     - 源阶段与源访问掩码 (src)
     - 目标阶段与目标访问掩码 (dst)
     - 对应布局流转 (Layout Transition)
   * - **深度预通到阴影采样**
     - `EARLY/LATE_FRAGMENT_TESTS`
       `DEPTH_STENCIL_WRITE`
     - `FRAGMENT_SHADER`
       `SHADER_SAMPLED_READ`
     - `DEPTH_ATTACHMENT_OPTIMAL`
       $	o$ `SHADER_READ_ONLY_OPTIMAL`
   * - **Compute 生成纹理至 PS**
     - `COMPUTE_SHADER`
       `SHADER_STORAGE_WRITE`
     - `FRAGMENT_SHADER`
       `SHADER_SAMPLED_READ`
     - `GENERAL`
       $	o$ `SHADER_READ_ONLY_OPTIMAL`
   * - **CPU 上传至顶点缓冲区**
     - `COPY / TRANSFER`
       `TRANSFER_WRITE`
     - `VERTEX_INPUT`
       `VERTEX_ATTRIBUTE_READ`
     - *(Buffer 仅需内存可见性，无布局)*
   * - **主场景渲染至 Present**
     - `COLOR_ATTACHMENT_OUTPUT`
       `COLOR_ATTACHMENT_WRITE`
     - `BOTTOM_OF_PIPE / NONE`
       `NONE`
     - `COLOR_ATTACHMENT_OPTIMAL`
       $	o$ `PRESENT_SRC_KHR`

过度同步的代价：管线气泡 (Pipeline Bubbles)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
如果开发者偷懒，将 `srcStageMask` 随意设置为 `ALL_COMMANDS` 或 `ALL_GRAPHICS`，并将 `dstStageMask` 同样设置为 `ALL_COMMANDS`，虽然绝对不会发生数据冒险，但会导致**灾难性的性能崩溃**。

这种“大锤式”屏障会强制 GPU 清空整条流水线的所有硬件单元，在前后两批工作之间造成巨大的**管线气泡（Pipeline Bubble）**。GPU 所有计算单元在此期间只能空转等待，完全丧失了指令重叠与延迟隐藏的能力。优秀的引擎架构师必须将屏障的等待范围收缩至最小的必要物理窗口。

图像布局转换 (Image Layout Transition) 的微架构本质
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为什么图像资源（Image/Texture）在改变用途时，除了内存屏障还必须指定 `oldLayout` 与 `newLayout`？这并非纯粹的 API 形式主义，而是由 GPU 纹理硬件存储格式决定的：

1. **平铺排布（Tiling / Swizzling Mode）**：
   - 线性布局（Linear）：按扫描线顺序排列，方便 CPU 内存拷贝，但对 2D/3D 空间局部性极差；
   - 最优瓦片布局（Optimal Tiling）：按照莫顿 Z 序曲线（Morton Order）或厂商私有的多级微瓦片（Micro-tiles）排列，保障任意方向的双线性插值均能命中同一缓存行。
2. **硬件无损色彩与深度压缩标记（DCC / Hi-Z Metadata）**：
   现代 GPU（如 AMD RDNA 的 DCC 或 NVIDIA 的 Memory Compression）在写入渲染目标或深度缓冲区时，会在专用的高速片上内存中写入压缩元数据（Metadata）。当纹理被转为 Shader 采样时，如果后续着色器无法直接解析特定写入阶段生成的压缩块，驱动必须在 Layout Transition 期间**调用专用微代码执行解压或元数据状态解离（Decompress / Expand）**。如果不声明转换，着色器将直接读出彻底乱码的压缩二进制数据！

------------------------------------------------------------------------
37.4 UAV / 存储缓冲区冒险与细粒度同步
------------------------------------------------------------------------

无序访问视图 (UAV) 的并发写冲突
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 Direct3D 12 中，**无序访问视图（Unordered Access View - UAV）** 与 Vulkan 中的 **存储缓冲区/存储图像（Storage Buffer / Storage Image）** 允许着色器（尤其是 Compute Shader）突破光栅化限制，向任意显存地址执行散射写入（Scatter Writes）。

当连续两个 Compute Pass 操作同一个 UAV 时，例如：
1. **Pass A**：执行高斯横向模糊，写入 `g_BlurBuffer`；
2. **Pass B**：执行高斯纵向模糊，读取并覆盖写入 `g_BlurBuffer`。

此时，两个 Pass 均在同一个硬件异步计算队列上执行，甚至使用完全相同的资源状态（`D3D12_RESOURCE_STATE_UNORDERED_ACCESS`）。常规的资源状态流转屏障无法捕捉这一变化。此时必须显式插入 **UAV 屏障（UAV Barrier）**：

.. code-block:: cpp

   // Direct3D 12 UAV 屏障声明
   D3D12_RESOURCE_BARRIER uavBarrier = {};
   uavBarrier.Type                  = D3D12_RESOURCE_BARRIER_TYPE_UAV;
   uavBarrier.Flags                 = D3D12_RESOURCE_BARRIER_FLAG_NONE;
   uavBarrier.UAV.pResource         = m_blurIntermediateBuffer.Get();
   cmdList->ResourceBarrier(1, &uavBarrier);

UAV 屏障通知底层 GPU 硬件：**挂起后续计算任务的派发，等待当前正在所有 SM 核心上执行的前序 UAV 写入指令全部提交至 L2 缓存，完成跨线程数据排空**。如果传入 `pResource = nullptr`，则代表对当前命令列表中发生的所有 UAV 写入执行全局同步。

跨队列资源所有权转移 (Queue Family Ownership Transfer)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 Vulkan 架构中，当多个物理队列（如专用的 Transfer Queue 与主 Graphics Queue）需要接力处理同一块资源时，由于不同队列可能挂载在不同的硬件调度器与 DMA 控制器上，资源必须经历显式的**所有权转移（Ownership Transfer）**：

- **第一步：源队列释放（Release Barrier）**：
  在 Transfer 队列上提交屏障，指定 `srcQueueFamilyIndex = TransferFamily`，`dstQueueFamilyIndex = GraphicsFamily`。此时仅执行写出缓存冲刷（Flush），不等待任何后续阶段；
- **第二步：队列间信号（Queue Semaphore）**：
  向硬件队列插入二进制信号量（`VkSemaphore`），通知目标队列前序操作在硬件上已经就绪；
- **第三步：目标队列获取（Acquire Barrier）**：
  在 Graphics 队列的命令缓冲区头部提交对等屏障，保持完全相同的源/目标队列索引，在此处执行缓存作废（Invalidate），将新所有权安全接入图形流水线。

------------------------------------------------------------------------
37.5 显存别名 (Memory Aliasing) 与瞬态资源复用
------------------------------------------------------------------------

瞬态资源（Transient Resources）的生命周期痛点
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在一帧典型的现代 3A 渲染流水线中，充斥着数十个生命周期极其短暂的**瞬态中间资源（Transient Resources）**：
- 级联阴影贴图（CSM）：仅在场景几何光栅化与前向/延迟阴影投射阶段存活，随后整帧再无访问；
- 延迟渲染 G-Buffer（WorldNormal, BaseColor, MaterialParams, Depth）：在光照合成完成后即宣告生命周期终结；
- SSAO / SSR 临时计算图层、后处理 Bloom 多级降采样链、景深模糊半分辨率缓冲区。

如果为每个瞬态资源在整个生命周期内分配独占的物理显存，一个 4K 分辨率的现代游戏在极端情况下需要消耗超过 **8GB ~ 12GB** 的运行时渲染目标显存！然而，分析各资源的生命周期区间图可以发现：**阴影贴图的生命周期与后处理渲染的生命周期在时间线上完全互斥！**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             基于显存别名 (Memory Aliasing) 的物理堆复用模型               |
   +-------------------------------------------------------------------------+

      [ 物理显存堆: ID3D12Heap / VkDeviceMemory (例如统一分配 256 MB) ]
      |=======================================================================|
      | Offset 0MB --------------------------------------------> Offset 256MB |
      |=======================================================================|
          |                                                               |
          +-------------------------------+-------------------------------+
          | (前半帧占用)                   | (后半帧复用同一块物理显存)
          v                               v
      [ 资源 A: 级联阴影图 CSM (256MB) ]     [ 资源 B: 后处理 HDR 模糊缓冲 (256MB) ]
      - Pass: Shadow Generation           - Pass: Post-Processing Bloom
      - 写入阴影深度并采样完毕后生命周期终结     - 重新解释这块物理显存为颜色格式
                                          - 必须插入 ALIASING BARRIER 消除硬件冲突！

放置资源 (Placed Resources) 与别名屏障 (Aliasing Barrier)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 Direct3D 12 中，通过调用 `CreatePlacedResource`，在 Vulkan 中通过将多个不同的 `VkImage` 绑定到同一个 `VkDeviceMemory` 的相同起始偏移处，应用程序即可实现**显存物理别名（Memory Aliasing）**。

为了确保物理显存复用的绝对安全性，API 引入了**别名屏障（Aliasing Barrier）**：
- 在 D3D12 中表现为 `D3D12_RESOURCE_BARRIER_TYPE_ALIASING`，包含 `pResourceBefore` 与 `pResourceAfter`；
- **物理硬件动作**：通知驱动与 GPU 缓存系统，`ResourceBefore` 占用的物理显存页已被正式注销，作废其挂接的所有硬件解压缩元数据（如 DCC/Hi-Z Flags），并通知后续硬件单元以 `ResourceAfter` 的全新格式、尺寸与解压规则重新解释该物理显存。

帧图 (Render Graph) 驱动的自动显存图着色重用
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在顶级游戏引擎中，开发者不会手动去计算成百上千个资源的物理偏移，而是由 **渲染架构层（Render Graph / Frame Graph）** 自动化求解：
1. 遍历渲染管线拓扑，精确追踪每个 Render Target 与 Buffer 在有向无环图（DAG）中的创建 Pass 与最后读取 Pass，构建出资源生命周期时间线（Interval Timelines）；
2. 将显存分配问题形式化为**区间图着色算法（Interval Graph Coloring）**；
3. 将时间上互斥且内存特征相符的资源，自动打包进同一物理显存块进行别名复用。通过这种机制，现代引擎能够将全局渲染目标物理显存峰值**压缩 40% 至 60%**！

------------------------------------------------------------------------
37.6 工业级显存同步与两阶段屏障实战范例 (Vulkan Synchronization2)
------------------------------------------------------------------------

以下给出遵循 **Vulkan 1.3 现代 Synchronization2（`VK_KHR_synchronization2`）** 规范的工业级完整核心代码。示例完整演示了一个通用的后处理管线中，Compute Shader 生成 HDR 模糊掩码、随后通过流水线屏障精确流转，提供给 Fragment Shader 进行全屏采样的全链路同步逻辑：

.. code-block:: cpp

   // =========================================================================
   // File: VulkanSynchronization2_PipelineBarrier.cpp
   // Standard: Modern C++17, Vulkan 1.3+ (VK_KHR_synchronization2 core)
   // Architecture: Two-stage Pipeline Barrier & Image Layout Transition
   // =========================================================================

   #include <vulkan/vulkan.h>
   #include <iostream>
   #include <cassert>

   class VulkanBarrierSystem {
   public:
       // =====================================================================
       // 工业级图像屏障：从 Compute Shader 写入跃迁至 Fragment Shader 采样读取
       // 完美解决 RAW 数据冒险，执行缓存 Flush (可用性) 与 Invalidate (可见性)
       // =====================================================================
       static void TransitionStorageToSampled(
           VkCommandBuffer commandBuffer,
           VkImage         image,
           VkImageAspectFlags aspectMask = VK_IMAGE_ASPECT_COLOR_BIT)
       {
           // 1. 构建细粒度图像内存屏障 (VkImageMemoryBarrier2)
           VkImageMemoryBarrier2 imageBarrier{};
           imageBarrier.sType               = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2;
           imageBarrier.pNext               = nullptr;

           // 源阶段与源访问：必须等待计算着色器完成无序写入
           imageBarrier.srcStageMask        = VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT;
           imageBarrier.srcAccessMask       = VK_ACCESS_2_SHADER_STORAGE_WRITE_BIT;

           // 目标阶段与目标访问：在片元着色器发起纹理采样之前进行拦截
           imageBarrier.dstStageMask        = VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT;
           imageBarrier.dstAccessMask       = VK_ACCESS_2_SHADER_SAMPLED_READ_BIT;

           // 布局流转：从计算写入通用的 GENERAL 转为最优采样只读布局
           // 触发底层硬件完成可能的无损压缩元数据 (DCC) 状态更新
           imageBarrier.oldLayout           = VK_IMAGE_LAYOUT_GENERAL;
           imageBarrier.newLayout           = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;

           // 同队列内操作，忽略队列族所有权转移
           imageBarrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
           imageBarrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;

           // 绑定目标物理图像及其子资源范围 (全部 Mipmap 与阵列层)
           imageBarrier.image               = image;
           imageBarrier.subresourceRange.aspectMask     = aspectMask;
           imageBarrier.subresourceRange.baseMipLevel   = 0;
           imageBarrier.subresourceRange.levelCount     = VK_REMAINING_MIP_LEVELS;
           imageBarrier.subresourceRange.baseArrayLayer = 0;
           imageBarrier.subresourceRange.layerCount     = VK_REMAINING_ARRAY_LAYERS;

           // 2. 组装全局依赖描述结构 (VkDependencyInfo)
           VkDependencyInfo dependencyInfo{};
           dependencyInfo.sType                    = VK_STRUCTURE_TYPE_DEPENDENCY_INFO;
           dependencyInfo.pNext                    = nullptr;
           dependencyInfo.dependencyFlags          = 0; // 局部依赖，避免插入全局管线气泡
           dependencyInfo.memoryBarrierCount       = 0;
           dependencyInfo.pMemoryBarriers          = nullptr;
           dependencyInfo.bufferMemoryBarrierCount = 0;
           dependencyInfo.pBufferMemoryBarriers    = nullptr;
           dependencyInfo.imageMemoryBarrierCount  = 1;
           dependencyInfo.pImageMemoryBarriers     = &imageBarrier;

           // 3. 向命令流中发射现代第二代管线屏障指令 (vkCmdPipelineBarrier2)
           // 纯粹由驱动转译为针对片上 GMMU 与缓存控制器的几个寄存器打包写入，耗时极低
           vkCmdPipelineBarrier2(commandBuffer, &dependencyInfo);
       }

       // =====================================================================
       // 渲染目标向呈现状态转换屏障：Color Attachment 写入 -> Swapchain Present
       // =====================================================================
       static void TransitionRenderTargetToPresent(
           VkCommandBuffer commandBuffer,
           VkImage         swapchainImage)
       {
           VkImageMemoryBarrier2 barrier{};
           barrier.sType               = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2;
           barrier.srcStageMask        = VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT;
           barrier.srcAccessMask       = VK_ACCESS_2_COLOR_ATTACHMENT_WRITE_BIT;
           barrier.dstStageMask        = VK_PIPELINE_STAGE_2_BOTTOM_OF_PIPE_BIT;
           barrier.dstAccessMask       = VK_ACCESS_2_NONE; // Present 仅需显示控制器读取，无管线访问掩码
           barrier.oldLayout           = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
           barrier.newLayout           = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
           barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
           barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
           barrier.image               = swapchainImage;
           barrier.subresourceRange.aspectMask     = VK_IMAGE_ASPECT_COLOR_BIT;
           barrier.subresourceRange.baseMipLevel   = 0;
           barrier.subresourceRange.levelCount     = 1;
           barrier.subresourceRange.baseArrayLayer = 0;
           barrier.subresourceRange.layerCount     = 1;

           VkDependencyInfo depInfo{};
           depInfo.sType                   = VK_STRUCTURE_TYPE_DEPENDENCY_INFO;
           depInfo.imageMemoryBarrierCount = 1;
           depInfo.pImageMemoryBarriers    = &barrier;

           vkCmdPipelineBarrier2(commandBuffer, &depInfo);
       }
   };

------------------------------------------------------------------------
小结与 Chapter 38 导读
------------------------------------------------------------------------

本章系统解构了现代图形底层最核心也最具挑战性的基石——显存管理与同步机制：
1. **虚拟显存与子分配模型**：剖析了 GPU 内存管理单元（GMMU）的多级页表结构与大页机制，揭示了驱动底层分配配额限制，推导了 TLSF 与环形缓冲区实现微秒级无碎片分配的算法架构；
2. **读写冒险与物理缓存网络**：深入探讨了 GPU SIMT 乱序执行与缺乏硬件全相干总线所引发的 RAW、WAW、WAR 危害，明确了执行同步（Execution Dependency）、数据可用性冲刷（Make Available）与可见性作废（Make Visible）三者的物理电路分工；
3. **管线屏障与布局转换**：解构了 Vulkan 1.3 Synchronization2 与 D3D12 Enhanced Barriers 的设计精髓，剖析了粗粒度屏障引发的管线气泡开销，揭示了 Image Layout Transition 调整片上瓦片格式与无损压缩元数据（DCC / Hi-Z）的硬件深意；
4. **UAV 冒险与所有权转移**：分析了无序访问视图的写入冲突与专用 UAV 屏障排空流水线的机理，推导了跨队列（Transfer $	o$ Graphics）二阶段 Release/Acquire 所有权转移契约；
5. **显存别名与瞬态复用**：阐释了利用生命周期互斥重叠物理内存的技术路径，结合渲染架构层（Render Graph）的图着色算法实现了 40%~60% 的帧峰值显存缩减。

至此，我们已经牢牢掌握了显式资源生命周期与数据一致性屏障。然而，在管理数以万计的材质贴图与全局光照缓存时，传统的“将每个描述符逐槽位绑定到管线”的方式依然会带来沉重的绑定开销与变体膨胀。
在下一章（**Chapter 38: 描述符与无绑定 (Bindless) 架构：Root Signature、Descriptor Indexing 与 SM6.6**）中，我们将彻底告别槽位绑定的历史枷锁，深入现代渲染工业的终极基建——全场景无绑定（Bindless）与 GPU-Driven 资源索引架构！敬请期待！
