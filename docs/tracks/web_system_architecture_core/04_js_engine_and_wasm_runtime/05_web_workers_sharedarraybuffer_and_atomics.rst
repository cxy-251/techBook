================================================================================
Chapter 22: Web 多线程并发架构：Worker 线程模型、SharedArrayBuffer 共享内存与 Atomics 原语
================================================================================

.. note:: 前置背景与认知承接
   在上一章中，我们系统解构了现代浏览器的事件循环（Event Loop）微架构（Chapter 21：Task 队列多源调度、Microtask Checkpoint 级联清空机制、渲染帧 VSync 时钟对齐与高精度计时量化）。事件循环虽然通过协作式切片（Time Slicing）和异步 I/O 保障了单线程上下文下的交互流畅性，但其物理计算上限始终受制于单个 CPU 核心的执行周期。在 3D 物理模拟、音视频实时编解码、大型图表布局计算或本地机器学习推理等高吞吐场景下，任何单次连续计算若耗时超过 50ms，都将直接导致长任务（Long Task）并击穿 INP 交互指标。

   为了释放现代多核 CPU 的并行计算能力，Web 平台从早期的单线程模型演进出完整的并发多线程体系。本章将深入剖析 Web 多线程的底层微架构：追踪 Dedicated Worker、Shared Worker、Service Worker 与 Worklet 的操作系统线程映射与 V8 Isolate 内存隔离拓扑；对比结构化克隆（Structured Clone）、所有权转移（Transferable Objects）与共享内存（SharedArrayBuffer）三种跨线程通信模式的数据流向与内存开销；解析防范微架构侧信道攻击（Spectre）下的跨域隔离（Cross-Origin Isolation）安全基线；推导硬件级原子操作（`Atomics`）在 CPU 缓存一致性协议（MESI）下的内存顺序语义；剖析 Linux Futex 机制在 Web 平台映射的 `Atomics.wait` 与 `Atomics.notify` 同步原语；最后基于共享内存构建高吞吐、零内存拷贝的跨线程无锁环形队列（Lock-Free Ring Buffer）。

------------------------------------------------------------------------
22.1 Web 线程拓扑与 Worker 家族微架构
------------------------------------------------------------------------

首先必须确立 Web 平台多线程的物理本质：**Web Worker 并非操作系统进程的克隆，而是宿主环境在操作系统层面创建的真实内核级线程（OS Native Threads，如 Linux 下通过 `clone()` 系统调用创建的 `pthread`）**。

每个 Worker 内部都封装了完整的独立执行环境。在 Google V8 引擎中，每个 Worker 对应一个完全独立的 **V8 Isolate（隔离实例）**。每个 Isolate 拥有属于自己的堆内存空间（Heap）、自己的垃圾回收器（GC）、自己的调用栈以及专属的事件循环（Worker Event Loop）。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                                浏览器渲染进程内部多线程与 Isolate 拓扑                            |
   +---------------------------------------------------------------------------------------------------+

   +---------------------------------------------------------------------------------------------------+
   | 浏览器渲染进程 (OS Process: PID 4812)                                                              |
   |                                                                                                   |
   |  +------------------------------------+      +------------------------------------+                |
   |  | 主线程 (Main Thread: TID 4812)     |      | Dedicated Worker 线程 (TID 4813)   |                |
   |  |                                    |      |                                    |                |
   |  | [ V8 Isolate A ]                   |      | [ V8 Isolate B ]                   |                |
   |  | * 独立堆内存 (Heap A: 512MB)       |      | * 独立堆内存 (Heap B: 128MB)       |                |
   |  | * 独立调用栈 (Callstack)           |      | * 独立调用栈 (Callstack)           |                |
   |  | * 独立 Minor/Major GC              |      | * 独立 Minor/Major GC              |                |
   |  |                                    |      |                                    |                |
   |  | [ 宿主上下文: Window / DOM ]       |      | [ 宿主上下文: DedicatedWorkerScope] |                |
   |  | * DOM 树、CSSOM、布局对象          |      | * 无 DOM、无 window、无 UI 操作     |                |
   |  | * 渲染流水线 (Style, Layout, Paint)|      | * 支持 fetch, IndexedDB, WASM      |                |
   |  | * 主线程事件循环                   |      | * Worker 专属事件循环              |                |
   |  +------------------------------------+      +------------------------------------+                |
   |                   ^                                            ^                                  |
   |                   |                                            |                                  |
   |                   +============== [ 通信机制: postMessage / IPC ] =+                              |
   |                                                |                                                  |
   |                                                v                                                  |
   |                                  +---------------------------+                                    |
   |                                  | 跨线程共享内存 (SAB)      |                                    |
   |                                  | [ SharedArrayBuffer ]     |                                    |
   |                                  | 虚拟内存页跨线程映射      |                                    |
   |                                  +---------------------------+                                    |
   +---------------------------------------------------------------------------------------------------+

Worker 家族的运行时分层
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代 Web 平台针对不同计算与生命周期需求，分化出不同形态的 Worker 运行时：

.. list-table:: Web Worker 家族微架构特征与执行边界对比
   :widths: 18 20 22 20 20
   :header-rows: 1
   :class: tight-table

   * - Worker 类型
     - 宿主全局作用域
     - 线程映射与生命周期
     - 适用场景
     - 通信接口
   * - **Dedicated Worker**
     - `DedicatedWorkerGlobalScope`
     - 单个文档拥有，与创建页面生命周期绑定。
     - CPU 密集型任务（图像处理、大数据解析、算法推演）。
     - `worker.postMessage()`、`self.postMessage()`
   * - **Shared Worker**
     - `SharedWorkerGlobalScope`
     - 同源多个浏览上下文共享，所有连接断开后回收。
     - 跨标签页状态同步、单一 WebSocket 链接复用。
     - `port.postMessage()` (基于 `MessagePort`)
   * - **Service Worker**
     - `ServiceWorkerGlobalScope`
     - 独立于页面，按事件唤醒与挂起，由浏览器调度。
     - 网络请求拦截、离线缓存管理、后台推送通知。
     - `postMessage()`、Fetch Event
   * - **AudioWorklet / Worklet**
     - `WorkletGlobalScope`
     - 专用底层管线线程（如 Web Audio 实时渲染线程）。
     - 纳秒/微秒级极低延迟音频处理、自定义绘制（Paint）。
     - `MessagePort` 驱动的低频参数同步

Worklet 的极致轻量化设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

与 Dedicated Worker 相比，**Worklet（如 AudioWorklet、PaintWorklet）** 的核心区别在于：它专为浏览器核心渲染/音频管线中的高频循环服务。
- 普通 Worker 拥有通用事件循环并处理各种宏任务与微任务；
- AudioWorklet 直接嵌入操作系统的实时音频驱动线程（Audio IO Thread），以固定的 128 采样点（约 2.9ms @ 44.1kHz）为周期硬时钟同步调用 `process()` 回调；
- 为了保障实时性，AudioWorklet 内部禁用了几乎所有耗时的通用 I/O API，杜绝任何可能导致主线程或音频线程阻塞的操作。

------------------------------------------------------------------------
22.2 数据跨线程通信的三种物理模式
------------------------------------------------------------------------

在 JavaScript 默认的**无共享内存（Share-Nothing）**模型中，主线程与 Worker 之间不能直接传递普通的 JavaScript 对象引用。如果允许跨线程传递可变对象引用，两个线程同时读写同一个 JS 对象的属性将直接破坏 V8 内部的隐藏类（Hidden Class）和指针标签，导致内存破坏。

为此，Web 平台提供了三种截然不同的跨线程数据交换模式。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                               跨线程数据通信的三种物理流向对比                                    |
   +---------------------------------------------------------------------------------------------------+

   模式一: 结构化克隆 (Structured Clone) - 深拷贝 (内存双倍, 涉及序列化开销)
   [ Thread A: Isolate A ]                                              [ Thread B: Isolate B ]
   原对象 { a: 1, buf: ... }  -- (序列化) -> 二进制连续内存 -> (反序列化) -> 新建独立对象副本 { a: 1, ... }
   * 堆内存 A 保留数据                                                  * 堆内存 B 分配新空间

   模式二: 所有权转移 (Transferable Objects) - 零拷贝指针交接 (源端即刻剥离失效)
   [ Thread A: Isolate A ]                                              [ Thread B: Isolate B ]
   ArrayBuffer (指针 0x7FFF00) -- (直接传递物理内存指针 0x7FFF00) --------> ArrayBuffer (指针 0x7FFF00)
   * 立即被 Detached, byteLength 归零                                  * 获得底层内存的完整所有权

   模式三: 共享内存 (SharedArrayBuffer) - 物理页共享 (多线程零拷贝并发并发访问)
   [ Thread A: Isolate A ]                                              [ Thread B: Isolate B ]
   Int32Array 视图 ----------------------+                      +-------- Int32Array 视图
                                         |                      |
                                         v                      v
                               +----------------------------------+
                               | 操作系统共享物理内存页 (RAM Page)|
                               | 地址: 0xA000 ~ 0xB000           |
                               +----------------------------------+

模式一：结构化克隆算法 (Structured Clone)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当调用 `postMessage(data)` 且未指定转移列表时，浏览器底层调用 HTML 标准规定的 **结构化克隆算法（Structured Clone Algorithm）**。

在 Chromium/V8 的实现中，底层核心类是 `v8::ValueSerializer` 与 `v8::ValueDeserializer`：
1. **递归遍历对象图**：序列化器深度优先遍历待发送对象，支持循环引用（通过对象字典表记录已访问对象）；
2. **生成连续二进制数据流**：将 JavaScript 基础类型、`Date`、`RegExp`、`Map`、`Set`、`ArrayBuffer` 编码为内部二进制格式；
3. **跨线程投递**：将生成的内存缓冲区通过操作系统的线程间消息队列投递至目标线程；
4. **目标端重建对象树**：目标线程的 V8 Isolate 从二进制流中逐字节反序列化，在目标堆内存中分配全新内存并重建完整的对象结构。

物理开销分析：
- **CPU 周期损耗**：对于包含数万个节点的深层嵌套对象，序列化与反序列化将消耗数十毫秒 CPU 计算，产生不可忽视的主线程耗时；
- **内存占用翻倍**：传输过程中，数据在源 Isolate、中间二进制缓冲区以及目标 Isolate 中同时存在，瞬时内存占用达到数据本体尺寸的 2~3 倍；
- **GC 压力剧增**：目标端反序列化瞬间在新生代（New Space）创建海量对象，直接诱发新生代垃圾回收频繁发生。

模式二：可转移对象 (Transferable Objects)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了彻底消除大体积二进制数据跨线程复制的 CPU 与内存开销，HTML 规范引入了 **可转移对象（Transferable Objects）**。最典型的可转移对象是 `ArrayBuffer`、`MessagePort`、`ImageBitmap` 与 `OffscreenCanvas`。

语法范式：

.. code-block:: javascript

   const largeBuffer = new ArrayBuffer(64 * 1024 * 1024); // 64MB 二进制大对象
   const u8View = new Uint8Array(largeBuffer);
   u8View[0] = 42;

   console.log("转移前 byteLength:", largeBuffer.byteLength); // 67108864

   // 第二个参数为 Transfer List 数组
   worker.postMessage({ type: "PROCESS_DATA", buffer: largeBuffer }, [largeBuffer]);

   // 转移后: 原 buffer 立即被剥离 (Detached)
   console.log("转移后 byteLength:", largeBuffer.byteLength); // 0!
   console.log("试图访问被剥离内存:", u8View[0]); // undefined 或抛出 TypeError

V8 底层执行机制（Detached Buffer）：
1. V8 的 `ArrayBuffer` 在 C++ 层由 `v8::internal::JSArrayBuffer` 与内部的 `v8::internal::BackingStore` 构成；
2. 执行转移时，V8 将 `JSArrayBuffer` 的内部物理内存指针置为 `nullptr`，并将 `byte_length` 字段重置为 0，标记该对象处于 **Detached** 状态；
3. 原 `BackingStore`（指向 64MB 物理内存）的所有权被打包放入消息，直接转移给目标线程的 V8 Isolate；
4. 目标线程接收后，仅需分配一个轻量的 `JSArrayBuffer` 壳对象，将其内部指针直接挂接至该 `BackingStore`。
5. **整个传输过程耗时小于 0.05ms，与传输数据体积完全无关（$O(1)$ 复杂度），实现绝对的零拷贝传递**。

模式三：共享内存 (SharedArrayBuffer)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

可转移对象虽然实现了零拷贝，但其语义是“所有权的单向交接”，发送方在转移后便失去对数据的访问权。如果在图像渲染或物理模拟中，主线程与多个 Worker 需要**同时**对同一块数据进行高频协同读写，所有权交接模式将因频繁往返投递而产生严重的通道开销。

`SharedArrayBuffer`（简称 SAB）彻底打破了 Isolate 之间内存互斥的藩篱：**它允许多个线程的 V8 Isolate 将同一段由操作系统分配的物理内存映射到各自的虚拟地址空间**。任何一个线程对内存的修改，其他线程在微处理器流水线刷新后立即物理可见。

.. list-table:: 跨线程数据传输模式特性全景对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 通信模式
     - 内存开销与拷贝行为
     - CPU 时间复杂度
     - 数据所有权归属
   * - **结构化克隆**
     - 完整深拷贝，内存占用增加 100%~200%，诱发垃圾回收。
     - $O(N)$，与数据节点数量及深度严格正相关。
     - 两端各自拥有独立副本，互不干扰。
   * - **可转移对象**
     - **零内存拷贝**，仅转移底层 `BackingStore` 指针。
     - **$O(1)$ 常数级**，与数据体积（即使数 GB）完全无关。
     - 源端立即剥离失效（Detached），目标端独占所有权。
   * - **SharedArrayBuffer**
     - **零内存拷贝**，物理内存页映射共享。
     - **$O(1)$ 常数级**，构建视图后直接进行内存寻址。
     - **多线程永久共享**，需配合 Atomics 治理数据争用。

------------------------------------------------------------------------
22.3 Spectre 漏洞与跨域隔离 (Cross-Origin Isolation)
------------------------------------------------------------------------

`SharedArrayBuffer` 曾于 ECMAScript 2017 首次进入规范，但在 2018 年被各大浏览器厂商全面紧急下线并封禁。其根本原因不在于软件本身的缺陷，而在于现代微处理器的硬件微架构漏洞：**Spectre（幽灵漏洞，CVE-2017-5753）**。

微架构侧信道攻击机理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Spectre 攻击利用了现代 CPU 提升流水线性能的两大硬件特性：**分支预测（Branch Prediction）** 与 **推测执行（Speculative Execution）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  Spectre 侧信道攻击与高精度时钟探测逻辑                 |
   +-------------------------------------------------------------------------+

   if (untrusted_index < array1_length) { // CPU 分支预测假设条件为真
       uint8_t value = secret_data[untrusted_index]; // 越权推测读取秘密数据
       uint8_t probe = array2[value * 4096];         // 将秘密数据作为索引访问 probe 数组
   }
   // 随后 CPU 发现分支预测失败, 回滚寄存器状态, 但 array2 对应缓存行已被载入 L1/L2!

   [ 攻击者测量访问 array2 各位置的耗时 ]
   * array2[k * 4096] 访问耗时 200 个 CPU 周期 -> Cache Miss (未被推测执行触碰)
   * array2[5 * 4096] 访问耗时  10 个 CPU 周期 -> Cache Hit! 推断 secret_data 值为 5!

在浏览器中，JavaScript 原生并没有能够测量单个 CPU 缓存行命中（约数纳秒级）的指令。然而，如果允许恶意代码创建一个后台 Worker 线程，该线程在一个共享的 `SharedArrayBuffer` 计数器上执行 `while(true) { counter++; }` 死循环；主线程便可以通过连续读取该计数器，**构建出一个精度达到数纳秒级的软件高精度物理时钟**。借助该时钟，攻击者能够在网页中轻而易举地分辨 Cache Hit 与 Cache Miss，进而读取到同一进程沙箱内其他标签页的密码、私钥或通信数据。

跨域隔离（Cross-Origin Isolation）安全基座
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了重新启用 `SharedArrayBuffer`，现代浏览器构建了操作系统进程级的物理隔离模型。浏览器要求页面必须显式声明 **跨域隔离（Cross-Origin Isolation）**，确保当前页面独占一个专属的操作系统进程，禁止跨域未知内容同进程执行。

页面必须在服务端配置以下两项硬性 HTTP 响应头：

.. code-block:: http

   Cross-Origin-Opener-Policy: same-origin
   Cross-Origin-Embedder-Policy: require-corp

1. **COOP (Cross-Origin-Opener-Policy: same-origin)**：切断当前窗口与其他不同源窗口（如通过 `window.open` 打开或被打开）的 `window.opener` 引用关系，强迫浏览器将不同源的窗口放入不同的操作系统物理进程；
2. **COEP (Cross-Origin-Embedder-Policy: require-corp)**：强迫页面加载的所有子资源（图像、音频、脚本、iframe）必须显式声明跨域资源授权（如包含 `Cross-Origin-Resource-Policy: cross-origin` 或通过 CORS 校验），彻底阻断未经许可的第三方敏感数据被加载进当前进程内存空间。

环境检查与状态判断：

.. code-block:: javascript

   if (crossOriginIsolated) {
     // 安全环境建立, SharedArrayBuffer 可安全实例化
     const sab = new SharedArrayBuffer(1024);
   } else {
     // 未开启跨域隔离: 试图创建 SharedArrayBuffer 将直接抛出 ReferenceError
     console.warn("当前环境未开启跨域隔离, SharedArrayBuffer 不可用");
   }

------------------------------------------------------------------------
22.4 SharedArrayBuffer 内存拓扑与 TypedArray 视图
------------------------------------------------------------------------

`SharedArrayBuffer` 对象本身仅仅是一段连续物理内存的抽象句柄，它不提供任何直接读写内部数据的 JavaScript 属性或方法。若要操作这块内存，必须在其之上构建 **TypedArray（类型化数组）** 或 `DataView` 视图。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                             SharedArrayBuffer 多视图重叠寻址模型                                  |
   +---------------------------------------------------------------------------------------------------+

   底层连续物理内存 (SharedArrayBuffer: 16 字节)
   [ 0x00 ] [ 0x01 ] [ 0x02 ] [ 0x03 ] [ 0x04 ] [ 0x05 ] [ 0x06 ] [ 0x07 ] [ 0x08 ] ... [ 0x0F ]
   |                                 | |                                 |
   +---------------------------------+ +---------------------------------+
                    |                                   |
                    v                                   v
   [ Int32Array 视图: 4 个元素 (每个 4 字节, 32位) ]
   ta32[0] = 0x12345678               ta32[1] = 0x00000001 ...

   [ Uint8Array 视图: 16 个元素 (每个 1 字节, 8位) ]
   u8[0]   u8[1]   u8[2]   u8[3]   ...  u8[7]

结构体重叠与二进制协议布局
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

通过在同一块 `SharedArrayBuffer` 上建立不同偏移量（Offset）与不同类型尺寸的 TypedArray 视图，可以在 JavaScript 跨线程体系中精确模拟 C/C++ 的内存结构体（Struct）。

以跨线程控制块（Control Block）为例：

.. code-block:: javascript

   // 分配 64 字节共享内存
   const sharedBuffer = new SharedArrayBuffer(64);

   // 前 16 字节定义为控制头 (Header): 包含 4 个 32位整型状态字段
   // 偏移量 0 字节, 长度 4 个 int32
   const controlHeader = new Int32Array(sharedBuffer, 0, 4);
   const IDX_STATUS = 0;      // 0: 运行状态
   const IDX_WRITE_PTR = 1;   // 1: 环形队列写指针
   const IDX_READ_PTR = 2;    // 2: 环形队列读指针
   const IDX_LOCK = 3;        // 3: 互斥锁标志

   // 剩余 48 字节作为有效负载数据区 (Payload): 按字节寻址
   const payloadData = new Uint8Array(sharedBuffer, 16, 48);

这种内存排布为无拷贝、极低延迟的高性能跨线程架构奠定了坚实的数据组织底座。

------------------------------------------------------------------------
22.5 Atomics 硬件级原子操作微架构与内存一致性
------------------------------------------------------------------------

当多个线程同时持有指向同一块 `SharedArrayBuffer` 的 TypedArray 视图并执行读写时，立即面临多核并行计算中最经典的挑战：**数据争用（Data Race）与内存乱序（Memory Reordering）**。

数据争用与内存屏障的硬件根源
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

考虑以下极简的跨线程自增操作：

.. code-block:: javascript

   // 线程 A 与 线程 B 同时执行:
   sharedInt32Array[0]++;

在底层 CPU 微架构层面，`sharedInt32Array[0]++` 并非单条不可分割的原子指令，而是由三条离散的汇编指令构成：
1. **读（Read）**：将内存地址的内容加载到 CPU 寄存器（`MOV EAX, [mem]`）；
2. **改（Modify）**：在寄存器内执行自增计算（`ADD EAX, 1`）；
3. **写（Write）**：将寄存器的结果写回内存（`MOV [mem], EAX`）。

若线程 A 与线程 B 在不同的 CPU 物理核心上同时启动，它们将同时读取到旧值（例如 10），各自计算出 11 并写回内存。最终结果为 11，导致原本应为 12 的计数发生严重的数据丢失。

此外，为了最大化指令吞吐，现代 CPU（尤其是 ARM 弱内存模型芯片）和 JIT 编译器在执行指令时，会在不改变单线程语义的前提下自由进行**指令重排（Instruction Reordering）**，并利用 CPU 内部的写缓冲（Store Buffer）延迟刷入 L1/L2 缓存。这使得一个线程写入的数据，无法保证立即按照代码书写顺序被另一个线程观测到。

Atomics 原语的底层硬件映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在 JavaScript 中实现无竞争的并发控制，ECMAScript 规范引入了全局 **`Atomics` 对象**。`Atomics` 提供的所有方法都是静态方法，其底层直接映射到现代 CPU 架构的专用硬件原子指令与内存屏障（Memory Barriers）：

.. list-table:: Atomics 核心操作与 CPU 硬件指令映射表
   :widths: 22 25 25 28
   :header-rows: 1
   :class: tight-table

   * - Atomics API
     - 操作语义与保证
     - x86-64 硬件实现
     - ARM64 硬件实现
   * - **`Atomics.load(ta, idx)`**
     - 原子读取。具备 Acquire 屏障，防止后续读写重排至本操作之前。
     - 原生内存对齐的 `MOV` 指令（x86 强内存模型自然保障加载顺序）。
     - `LDAR` 指令（Load-Acquire Register，强制内存流水线刷新）。
   * - **`Atomics.store(ta, idx, val)`**
     - 原子写入。具备 Release 屏障，确保前序所有写操作在此之前全部落盘。
     - `XCHG` 或 `MOV` 伴随写屏障（Store-Release）。
     - `STLR` 指令（Store-Release Register，清空 Store Buffer）。
   * - **`Atomics.add / sub / and / or`**
     - 原子读-修改-写（RMW）。强顺序一致性。
     - `LOCK ADD`、`LOCK SUB`（触发 MESI 缓存总线锁定）。
     - `LDADD` / `LDADDA` 原语（或 `LDXR/STXR` 独占加载存储循环）。
   * - **`Atomics.compareExchange(ta, idx, exp, val)`**
     - 比较并交换（CAS）。若当前值等于 `exp` 则写入 `val` 并返回旧值。
     - `LOCK CMPXCHG` 指令。
     - `CAS` 指令（ARMv8.1+）或 `LDAXR / STLXR` 独占监听循环。
   * - **`Atomics.exchange(ta, idx, val)`**
     - 无条件原子替换并返回被替换的旧值。
     - `XCHG` 指令（自动隐含全局总线锁定锁）。
     - `SWP` / `SWPA` 指令。

`Atomics.compareExchange`（CAS 原语）与无锁算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CAS（Compare-And-Swap）是整个无锁并发计算的基石。它允许程序在无需操作系统互斥锁介入的前提下，以乐观锁机制完成高冲突状态的并发变更：

.. code-block:: javascript

   function atomicUpdate(int32Array, index, updaterFn) {
     while (true) {
       // 1. 读取当前物理内存的即时值
       const currentValue = Atomics.load(int32Array, index);
       // 2. 在本地纯计算预期的新值
       const nextValue = updaterFn(currentValue);
       // 3. 硬件原子比较: 若在此期间该地址未被其他线程篡改, 则原子写入 nextValue
       const actualOldValue = Atomics.compareExchange(
         int32Array,
         index,
         currentValue,
         nextValue
       );
       // 4. 若返回值等于预期旧值, 说明写入成功, 退出循环; 否则自旋重试
       if (actualOldValue === currentValue) {
         return nextValue;
       }
     }
   }

------------------------------------------------------------------------
22.6 Linux Futex 机制在 Web 平台的映射：Atomics.wait 与 Atomics.notify
------------------------------------------------------------------------

在多线程协作中，若一个 Worker 需要等待特定条件成立（例如等待队列出现可用数据），单纯使用 `while (Atomics.load(...) === 0) {}` 的**自旋锁（Spinlock）**将持续榨干 CPU 核心算力（CPU 100% 满载），推高芯片温度并引发严重的降频节流。

为了实现真正的线程休眠与精准唤醒，Web 平台引入了源自 Linux 内核的 **Futex（Fast Userspace Mutex）** 机制投射：`Atomics.wait()` 与 `Atomics.notify()`。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                            Atomics.wait 与 notify 内核挂起唤醒时序                                |
   +---------------------------------------------------------------------------------------------------+

   Worker 线程 (消费者)                                             主线程 / 生产者 Worker
         |                                                                    |
         v                                                                    |
   [ 读取 Int32Array[0] ]                                                     |
         |                                                                    |
         v                                                                    |
   [ 发现数据未就绪 (值为 0) ]                                                |
         |                                                                    |
         v                                                                    |
   [ 调用 Atomics.wait(ta, 0, 0) ]                                            |
         |                                                                    |
         |---> (向操作系统内核发起 Futex 挂起系统调用)                         |
               * Linux: sys_futex(..., FUTEX_WAIT, 0, ...)                    |
               * 当前 Worker 线程进入 TASK_INTERRUPTIBLE 休眠态               |
               * 彻底让出 CPU 时间片, CPU 占用率瞬间归零!                     |
               * [ 线程被操作系统挂起挂住 ... ]                               |
                                                                              | (计算完成, 生产数据)
                                                                              v
                                                                      [ 写入数据缓冲区 ]
                                                                      [ Atomics.store(ta, 0, 1) ]
                                                                              |
                                                                              v
                                                                      [ 调用 Atomics.notify(ta, 0, 1) ]
                                                                              |
                                                                              |---> (向内核发送 Futex 唤醒系统调用)
                                                                                    * Linux: sys_futex(..., FUTEX_WAKE, 1)
                                                                                    * 操作系统调度器激活挂起的 Worker 线程!
               +--------------------------------------------------------------+
               |
               v
   [ Worker 线程被内核唤醒 ]
         |
         v (Atomics.wait 返回 "ok")
   [ 继续高速执行后续业务逻辑 ]

`Atomics.wait` 的四个执行步骤与防伪唤醒机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`Atomics.wait(typedArray, index, expectedValue, timeout)` 在内核中严格遵循以下四个逻辑步骤执行：
1. **内存边界与类型检查**：校验 `typedArray` 必须是共享的 `Int32Array`（或 ES2020 引入的 `BigInt64Array`），若为非共享内存直接抛出 `TypeError`；
2. **原子比较**：在内核锁保护下，读取 `typedArray[index]` 当前值。若当前值**不等于** `expectedValue`，说明在进入休眠前数据已经被修改，函数**立即返回 `"not-equal"`，绝不陷入休眠**；
3. **内核级休眠**：若当前值等于 `expectedValue`，将当前线程放入该内存地址对应的内核等待队列，线程被挂起；
4. **唤醒与结果返回**：线程被 `Atomics.notify` 唤醒时返回 `"ok"`；若超出 `timeout` 毫秒返回 `"timed-out"`。

主线程严禁调用同步 `Atomics.wait()` 的物理戒律
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

规范作出了极其严格的限制：**绝对禁止在浏览器主线程（Main Window Context）上调用同步的 `Atomics.wait()`，否则运行时将直接抛出 `TypeError`**。

这一限制的物理成因在于：
- 浏览器主线程是唯一的用户界面渲染与输入调度中枢；
- 若主线程进入内核休眠，它将无法执行任何后续的 Task、Microtask，屏幕重排重绘全部停滞；
- 此时页面不仅对点击滚动毫无反应，而且若负责唤醒它的后台 Worker 恰好需要通过主线程的事件分发辅助计算，整个系统将陷入不可逆的**死锁（Deadlock）**。

异步等待原语：`Atomics.waitAsync()`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在不阻塞主线程事件循环的前提下享受到 Futex 唤醒机制的低延迟优势，规范制定了非阻塞的 `Atomics.waitAsync()`：

.. code-block:: javascript

   // 在浏览器主线程或 Worker 中均可合法调用
   const result = Atomics.waitAsync(sharedInt32, 0, 0, 1000);

   if (result.async) {
     // 返回一个 Promise: 当前线程继续执行事件循环, 绝不阻塞渲染!
     result.value.then((status) => {
       if (status === "ok") {
         console.log("主线程被后台 Worker 异步唤醒, 数据已就绪!");
       } else if (status === "timed-out") {
         console.warn("等待超时");
       }
     });
   } else {
     // 同步判定已结束 (例如值已不等于 0, status 为 "not-equal")
     console.log("即刻返回状态:", result.value);
   }

------------------------------------------------------------------------
22.7 工业级实战：构建跨线程无锁环形队列 (Lock-Free Ring Buffer)
------------------------------------------------------------------------

为了将上述原子操作与共享内存技术融会贯通，我们实现一个在音视频处理与高性能计算中广泛应用的工业级基础设施：**基于 `SharedArrayBuffer` 的单生产者单消费者（SPSC - Single-Producer Single-Consumer）无锁环形队列**。

该队列允许主线程以微秒级时延将流式二进制数据推入，后台 Worker 持续无锁拉取，彻底规避 `postMessage` 带来的每秒数千次结构化克隆开销与垃圾回收停顿。

内存拓扑设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                               无锁环形队列物理内存连续布局 (64KB 总容量)                          |
   +---------------------------------------------------------------------------------------------------+

   [ Header 控制区: 16 字节 (4 个 Int32) ]
   +-------------------+-------------------+-------------------+-------------------+
   | Index 0: 队列容量 | Index 1: 写入指针 | Index 2: 读取指针 | Index 3: 预留标志 |
   | (CAPACITY = 16384)| (writeIndex: 0~N) | (readIndex: 0~N)  | (RESERVED)        |
   +-------------------+-------------------+-------------------+-------------------+
   |
   v
   [ 环形有效载荷缓冲区 (Ring Buffer Storage): 16384 个 Int32 槽位 (共 65536 字节) ]
   +-----------+-----------+-----------+-----------+ ... +-------------+-------------+
   | Slot 0    | Slot 1    | Slot 2    | Slot 3    | ... | Slot 16382  | Slot 16383  |
   +-----------+-----------+-----------+-----------+ ... +-------------+-------------+

完整源码级实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: javascript

   // ring-buffer.js - 跨线程无锁环形队列核心封装
   export class SharedRingBuffer {
     static HEADER_SLOTS = 4;
     static IDX_CAPACITY = 0;
     static IDX_WRITE = 1;
     static IDX_READ = 2;

     constructor(capacityOrBuffer) {
       if (typeof capacityOrBuffer === "number") {
         // 生产者初始化: 分配完整的 SharedArrayBuffer (4 字节 Header + 容量 * 4 字节 Data)
         const capacity = capacityOrBuffer;
         const totalByteLength = (SharedRingBuffer.HEADER_SLOTS + capacity) * Int32Array.BYTES_PER_ELEMENT;
         this.buffer = new SharedArrayBuffer(totalByteLength);
         this.header = new Int32Array(this.buffer, 0, SharedRingBuffer.HEADER_SLOTS);
         this.storage = new Int32Array(this.buffer, SharedRingBuffer.HEADER_SLOTS * Int32Array.BYTES_PER_ELEMENT, capacity);

         Atomics.store(this.header, SharedRingBuffer.IDX_CAPACITY, capacity);
         Atomics.store(this.header, SharedRingBuffer.IDX_WRITE, 0);
         Atomics.store(this.header, SharedRingBuffer.IDX_READ, 0);
       } else {
         // 消费者反序列化: 绑定已存在的 SharedArrayBuffer
         this.buffer = capacityOrBuffer;
         this.header = new Int32Array(this.buffer, 0, SharedRingBuffer.HEADER_SLOTS);
         const capacity = Atomics.load(this.header, SharedRingBuffer.IDX_CAPACITY);
         this.storage = new Int32Array(this.buffer, SharedRingBuffer.HEADER_SLOTS * Int32Array.BYTES_PER_ELEMENT, capacity);
       }
       this.capacity = Atomics.load(this.header, SharedRingBuffer.IDX_CAPACITY);
     }

     /**
      * 生产者写入单条数据 (无锁写入)
      * @param {number} value 32位整型数据
      * @returns {boolean} 是否写入成功 (队列满返回 false)
      */
     push(value) {
       const writePtr = Atomics.load(this.header, SharedRingBuffer.IDX_WRITE);
       const readPtr = Atomics.load(this.header, SharedRingBuffer.IDX_READ);

       // 判定队列是否已满: 写入指针领先读取指针达到容量上限
       if (writePtr - readPtr >= this.capacity) {
         return false; // 队列溢出保护, 让调用方实施背压处理
       }

       // 计算实际数组环形物理下标
       const physicalIndex = writePtr % this.capacity;
       // 将数据存入槽位
       this.storage[physicalIndex] = value;

       // 强制使用带 Release 语义的原子写操作推移写指针, 确保槽位数据的内存可见性
       Atomics.store(this.header, SharedRingBuffer.IDX_WRITE, writePtr + 1);

       // 若原本处于空队列状态, 唤醒可能处于休眠等待的消费者线程
       if (writePtr === readPtr) {
         Atomics.notify(this.header, SharedRingBuffer.IDX_WRITE, 1);
       }

       return true;
     }

     /**
      * 消费者阻塞读取数据 (若为空则在内核休眠挂起)
      * @param {number} timeout 最大休眠时间 (毫秒)
      * @returns {number|null} 读取到的值, 超时返回 null
      */
     popBlocking(timeout = 1000) {
       while (true) {
         const writePtr = Atomics.load(this.header, SharedRingBuffer.IDX_WRITE);
         const readPtr = Atomics.load(this.header, SharedRingBuffer.IDX_READ);

         // 队列非空, 即刻读取
         if (readPtr < writePtr) {
           const physicalIndex = readPtr % this.capacity;
           const value = this.storage[physicalIndex];

           // 使用带 Release 语义的原子写推移读指针
           Atomics.store(this.header, SharedRingBuffer.IDX_READ, readPtr + 1);
           return value;
         }

         // 队列为空: 进入内核级 Futex 休眠, 挂起等待写入指针变化
         const waitStatus = Atomics.wait(this.header, SharedRingBuffer.IDX_WRITE, writePtr, timeout);
         if (waitStatus === "timed-out") {
           return null; // 超时退出
         }
         // 被唤醒后继续循环尝试读取
       }
     }
   }

工程架构收益：
1. **零垃圾回收负担**：从头到尾在固定长度的预分配内存中循环使用，执行过程中完全零对象分配（Zero Allocations）；
2. **超高吞吐**：单次 Push/Pop 仅包含两次内存加载与一次原子存储，单核每秒吞吐可达到数千万次无锁交互；
3. **智能休眠**：在队列无数据时，消费者自动陷入操作系统级挂起，CPU 占用率立刻清零，彻底解决了传统 Worker 轮询造成的算力与电量损耗。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章深入探讨了现代 Web 平台的多线程并发微架构与共享内存模型：
- 剖析了 Web Worker 的操作系统原生线程绑定机理与 V8 Isolate 独立堆内存/独立 GC 隔离边界；
- 对比了结构化克隆（深拷贝开销）、可转移对象（$O(1)$ 指针所有权剥离）与 `SharedArrayBuffer`（物理页共享并发）的三种跨线程数据交互范式；
- 深入推导了抵御 Spectre 微架构侧信道攻击的物理原理，阐明了 COOP 与 COEP 跨域隔离 HTTP 标头作为启用共享内存的强制安全前置条件；
- 建立了基于 TypedArray 视图的多类型结构体重叠内存布局；
- 解密了 `Atomics` 静态对象在 CPU 硬件指令（MESI 缓存一致性总线锁定、`CMPXCHG` CAS 原语、内存屏障）层面的微架构映射；
- 剖析了 Linux Futex 机制在 Web 平台的投射（`Atomics.wait` 线程安全挂起与 `Atomics.notify` 唤醒），强调了主线程禁用同步阻塞等待的物理根由与 `Atomics.waitAsync` 异步方案；
- 实现了单生产者单消费者（SPSC）跨线程无锁环形队列，展示了高性能无锁计算的完整闭环。

在下一章 **Chapter 23: WebAssembly 运行时微架构：二进制格式解析、栈式虚拟机、编译流水线与 JIT 机器码生成** 中，我们将深入超越 JavaScript 文本解释的全新执行引擎：剖析 WebAssembly 的标准二进制编码格式与段（Section）结构、追踪栈式虚拟机（Stack Machine）的设计精髓、揭密 V8 内部针对 WASM 构建的双层编译流水线（Liftoff 极速基线编译器与 TurboFan 深度优化编译器），并探讨其在现代大型高性能 Web 系统中的架构定位。
