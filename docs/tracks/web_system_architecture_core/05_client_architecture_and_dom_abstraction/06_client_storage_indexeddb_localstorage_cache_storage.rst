================================================================================
Chapter 30: 客户端存储微架构：IndexedDB 事务模型、LocalStorage 同步 I/O 阻塞陷阱与 Cache Storage
================================================================================

.. note:: 前置背景与认知承接
   在上一章中，我们系统剖析了现代 Web 前端状态管理范式的底层机理与工程实现（Chapter 29：现代前端状态管理范式演进与性能权衡：不可变单向数据流、观察者响应式、原子化派生与 Signals）。我们证明了：在复杂的单页应用中，无论是基于不可变单向数据流的快照浅比较，还是基于 Proxy 的细粒度响应式拓扑图，本质上都是在客户端内存空间（V8 堆内存）中管理瞬时状态，确保视图函数能够在最小计算开销下完成精准增量更新。

   然而，内存中的数据结构具有高度的挥发性（Volatile）：用户关闭标签页、意外崩溃、页面刷新或弱网离线，都会直接抹除所有的内存堆栈。当业务进入离线文档协作、海量离线音视频缓存、富交互草稿自动保存、全天候高频交易日志记录等深度应用场景时，系统必须将关键数据可靠地下沉固化至物理磁盘中。

   浏览器并非开放的操作系统文件管理器，而是基于严格的同源安全沙箱与多进程架构，向脚本层暴露了职责迥异的持久化存储能力。如果架构师误将大体积数据写入同步阻塞的 LocalStorage，或者对 IndexedDB 的事务生命周期与跨标签页锁竞争缺乏微架构认知，持久化层将反向压垮渲染主线程，造成灾难性的交互卡顿（INP 飙升）与数据写入竞争丢失。

   本章作为 **Part 5: 客户端架构、DOM 抽象与前端运行时** 的收官之作，深入解构现代浏览器客户端存储的微架构底座：从 Web Storage 同步 I/O 对事件循环的物理阻塞机制，到 IndexedDB 基于 B-Tree / LSM-Tree 的异步事务模型与游标遍历；从 Cache Storage 配合 Service Worker 对网络请求响应二进制流的直接托管，到现代离线优先（Offline-First）架构中的版本冲突仲裁与多级存储全链路级联清理协议。

------------------------------------------------------------------------
30.1 浏览器存储体系全景与物理边界：Request-Bound、Origin 隔离与生命周期拓扑
------------------------------------------------------------------------
在评估客户端存储选型前，架构师必须跳出单一 API 调用的狭隘视角，将浏览器本地存储视为一个包含**网络绑定、沙箱隔离、I/O 调度与生命周期承诺**的多维执行体系：

.. list-table:: 现代浏览器主要客户端存储基础设施多维对比矩阵
   :widths: 14 16 16 18 18 18
   :header-rows: 1

   * - 存储机制
     - 底层 I/O 模型
     - 数据类型与结构
     - 请求绑定属性 (Request-Bound)
     - 典型容量配额
     - 适用场景与安全约束
   * - **Cookie**
     - 同步内存/异步落盘
     - 键值字符串 (4KB 限制)
     - **强绑定** (匹配 Domain/Path 自动注入 Header)
     - ~4KB / 域名
     - 会话标识符、CSRF Token；受 `HttpOnly`/`SameSite` 约束
   * - **LocalStorage**
     - **同步阻塞 I/O**
     - 纯字符串键值
     - 无绑定 (由脚本显式读取)
     - ~5MB / Origin
     - 极低频轻量级 UI 偏好、非敏感客户端配置
   * - **SessionStorage**
     - **同步阻塞 I/O**
     - 纯字符串键值
     - 无绑定 (按 Tab/Session 分区)
     - ~5MB / Tab Context
     - 单标签页独立流水分步表单、临时搜索筛选上下文
   * - **IndexedDB**
     - **异步非阻塞事务 I/O**
     - 结构化克隆对象 / 二进制 Blob
     - 无绑定 (由脚本显式读取)
     - 磁盘可用空间 60%~80% (按 Origin 动态配额)
     - 离线业务数据库、富文本草稿、结构化数据缓存、同步队列
   * - **Cache Storage**
     - **异步非阻塞流式 I/O**
     - Request / Response 原生二进制对象
     - **配合 Service Worker 拦截绑定**
     - 共享 Origin 动态大配额
     - App Shell 离线资源包、静态资源缓存、PWA 运行时网络拦截

存储拓扑的核心分界准则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
理解这套体系的关键在于把握三大系统物理边界：

1. **请求绑定边界（Request-Bound vs Script-Driven）**：
   Cookie 的核心特征在于其生命周期深度嵌入 HTTP 网络传输层。只要请求的 URL 命中 Cookie 的 Domain 与 Path 规则，浏览器内核的 Network 进程在组装 TCP/QUIC 报文时，便会自动在 Header 中追加 `Cookie: ...` 字段。这意味着任何存入 Cookie 的冗余数据都会直接放大所有上行网络包的体积。而 Web Storage、IndexedDB 与 Cache Storage 完全属于脚本驱动（Script-Driven）范畴，数据绝不会自发进入网络信道，唯有当脚本显式读取并将其拼装入 Fetch Payload 时才产生网络成本。
2. **执行线程与 I/O 调度边界（Sync Main Thread vs Async Thread Pool）**：
   LocalStorage 与 SessionStorage 的 API 签名被历史性地设计为同步阻塞调用（`getItem` / `setItem`），其底层数据读取与写入操作直接与渲染主线程的 JavaScript 执行管线绑定。IndexedDB 与 Cache Storage 则全面构建于异步事件和 Promise 模型之上，实际的磁盘读写与数据库引擎运转完全托管于浏览器内核的专用 I/O 线程池中，避免对 UI 渲染形成物理阻塞。
3. **安全沙箱与 Origin 隔离边界（Storage Partitioning）**：
   所有浏览器存储均受到同源策略（Same-Origin Policy: Protocol + Host + Port）的绝对约束。近年来主流浏览器（Chromium、WebKit、Gecko）全面推行了**第三方存储分区机制（Third-Party Storage Partitioning）**：当网站 `widget.example.com` 以 iframe 形式嵌入 `site-a.com` 与 `site-b.com` 时，浏览器将根据顶级站点（Top-Level Site）对存储实施双重键控（Double-Keying）。`widget.example.com` 在两个宿主站点下访问到的 LocalStorage 或 IndexedDB 在物理磁盘上处于完全隔离的分区，彻底粉碎了跨站追踪依赖客户端存储串联用户指纹的技术路径。

------------------------------------------------------------------------
30.2 Web Storage 同步 I/O 的物理缺陷：主线程阻塞、序列化惩罚与配额极限
------------------------------------------------------------------------
Web Storage（LocalStorage 与 SessionStorage）凭借极简的 `key-value` 字典接口，长期成为前端开发者持久化配置的首选。然而，其同步阻塞的架构设计在现代高性能 Web 运行时中构成了严重的性能反模式。

Chromium 内核下的 Web Storage 存储引擎实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了理解 Web Storage 的阻塞物理成因，必须剖析其在 Chromium / Blink 多进程架构下的底层实现路径：

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                             Chromium Web Storage 跨进程同步读写架构                               |
   +---------------------------------------------------------------------------------------------------+

      [Renderer 进程: 渲染主线程]                         [Browser 进程: 存储后台线程]
               |                                                       |
               |  1. 页面初始化: 触发同步读取请求                      |
               |======================================================>| (通过同步 Mojo IPC 阻塞主线程)
               |                                                       |
               |                                                       | 2. 从磁盘 LevelDB 加载 Origin 数据
               |                                                       |    读取并反序列化整个 Storage Area
               |                                                       |
               |  3. 返回全量数据并填充 Renderer 内存缓存              |
               |<======================================================|
               |                                                       |
               +---> [内存缓存 StorageArea (DOMStorageMap)]            |
               |                                                       |
               |  4. localStorage.setItem("key", "value")              |
               +---> (1) 同步写入 Renderer 内存缓存                    |
               +---> (2) 发起异步持久化指令 (Commit Task)              |
               |------------------------------------------------------>|
               |                                                       | 5. 写入 Browser 进程内存缓冲区
               |                                                       | 6. 触发延时磁盘写入 (LevelDB Batch)
               |                                                       |
               |  5. 临界异常: 快速连续高频写入 / 缓存未命中           |
               |======================================================>| (锁等待与同步 IPC 强制挂起主线程)
               |                                                       |

1. **进程间通信与内存镜像初始化**：
   在页面加载阶段，Renderer 进程中的脚本首次访问 `window.localStorage` 时，如果当前 Origin 的数据尚未载入，Renderer 必须向 Browser 进程发起一个**同步阻塞的 Mojo IPC 调用**。Browser 进程在其专用的存储线程上读取磁盘中的 LevelDB 实例，将该 Origin 的全部键值对加载完毕后返回给 Renderer。在此期间，Renderer 的主线程处于完全冻结状态，无法响应用户输入，也无法推进样式计算与图层排版。
2. **写入机制与提交锁（Commit Bottleneck）**：
   一旦内存缓存建立，`localStorage.setItem()` 会立即同步更新 Renderer 内存中的 `DOMStorageMap`，并向 Browser 进程投递一条异步写入任务。虽然单个写入指令对磁盘是异步批处理的（写入 LevelDB WAL 日志），但如果脚本在短时间内写入大量数据（例如几兆字节），或者在不同的同源标签页间并发修改，内部的互斥锁（Mutex）与跨进程数据同步将强制 Renderer 进程的主线程陷入同步等待状态。

三大物理缺陷深度量化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在大型企业级前端工程中，滥用 LocalStorage 将导致以下三大物理故障：

- **缺陷 1：主线程强行卡死与长任务（Long Tasks / INP 劣化）**
  LocalStorage 的所有 API 执行均独占 JavaScript 单线程。当开发者尝试通过 `localStorage.getItem()` 读取一个几兆字节的大型 JSON 字符串，随后立即执行 `JSON.parse()` 时，主线程将被连续阻塞数十毫秒至数百毫秒。这在移动端低性能 CPU 上会直接引发严重的界面掉帧与输入迟滞。
- **缺陷 2：纯字符串模型的序列化与反序列化 CPU 惩罚**
  Web Storage 严格要求键和值均为 UTF-16 纯文本字符串。当存储复杂对象、数组、日期或二进制数据时，开发者必须频繁执行 `JSON.stringify()` 与 `JSON.parse()`。这种深层对象遍历不仅消耗可观的 CPU 周期，更会在 V8 堆内存中瞬间分配大量临时的 AST 节点与字符串碎片，直接加剧年轻代（New Space）的垃圾回收负担，频繁触发 Scavenger GC。
- **缺陷 3：容量死锁与 QuotaExceededError 崩溃**
  浏览器对 Web Storage 施加了硬性的容量上限（大部分现代浏览器固定为 **5MB**，部分环境为 2.5MB）。当写入数据触碰配额红线时，浏览器会同步抛出无法恢复的 `DOMException: QuotaExceededError`。由于缺乏分级淘汰策略与自动清理机制，若代码未用 `try...catch` 严格防御，该异常将直接导致后续业务逻辑彻底中断。

------------------------------------------------------------------------
30.3 IndexedDB 核心微架构：B-Tree / LSM-Tree 底层、异步事务模型与游标查询
------------------------------------------------------------------------
为了突破 Web Storage 的同步阻塞与体积限制，W3C 推出了 **Indexed Database API (IndexedDB)**。它是直接嵌入浏览器内核的高性能、支持事务的结构化对象数据库系统。

底层存储引擎与物理拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在浏览器内核（如 Chromium 的 Blink 引擎）内部，IndexedDB 并非纯内存结构，其底层依托于成熟的嵌入式数据库引擎：
- **Chromium / Blink**：底层完全基于 **LevelDB**（Google 开发的高性能 LSM-Tree 键值存储引擎）构建；
- **Firefox / Gecko**：底层完全基于 **SQLite**（通过 B-Tree 索引组织表结构与磁盘文件）构建；
- **Safari / WebKit**：底层同样基于 **SQLite** 实现。

以 LevelDB 为例，IndexedDB 的对象存储区（Object Store）中的主键（KeyPath）以及辅助索引（Indexes），均被编码映射为 LevelDB 底层的有序字节序列（Keys），数据实体则通过结构化克隆算法（Structured Clone Algorithm）序列化后保存在值空间（Values）中。由于 LSM-Tree 具备极其出色的顺序追加写入性能（Append-only WAL 日志），IndexedDB 能够在处理大规模数据写入时保持极高的磁盘吞吐量。

IndexedDB 四层核心架构要素
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                                 IndexedDB 内部层级与拓扑映射模型                                  |
   +---------------------------------------------------------------------------------------------------+

      [Database: "ProjectManagementDB" (Version: 2)]
           |
           +---> [Object Store: "tasks" (KeyPath: "taskId", AutoIncrement: false)]
           |          |
           |          +---> Record 1: { taskId: "T-101", title: "Refactor IO", status: "pending", ... }
           |          +---> Record 2: { taskId: "T-102", title: "Audit Cache", status: "done", ... }
           |          |
           |          +---> [Index 1: "status_idx" (KeyPath: "status", Unique: false)]
           |          |          +---> "done"    -> ["T-102"]
           |          |          +---> "pending" -> ["T-101"]
           |          |
           |          +---> [Index 2: "created_idx" (KeyPath: "createdAt", Unique: false)]
           |
           +---> [Object Store: "audit_logs" (KeyPath: "id", AutoIncrement: true)]
                      +---> Record 1: ...

版本管理与模式迁移状态机 (Versionchange)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
IndexedDB 的表结构定义（创建或删除 Object Store、创建或修改 Index）必须在受严格约束的模式迁移事务中执行。这个过程由数据库版本号（Version）严格驱动：

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                          IndexedDB 版本升级与跨标签页连接阻断状态机                               |
   +---------------------------------------------------------------------------------------------------+

       [当前 Tab A (新版代码)]                        [后台存活 Tab B (旧版代码)]
                  |                                                  |
                  | 1. 打开数据库 version: 2                         | 持有旧连接 (version: 1)
                  +------------------------------------------------->|
                  |                                                  |
                  | 2. 触发 Tab B 的 db.onversionchange 事件         |
                  |                                                  +---> 应主动执行 db.close() 释放锁！
                  |                                                  |
                  +---[分支 1: Tab B 及时关闭]-----------------------+
                  |    Tab A 触发 upgradeneeded                      |
                  |    执行 createObjectStore / createIndex          |
                  |    完成模式升级，触发 onsuccess 正常通信         |
                  |                                                  |
                  +---[分支 2: Tab B 未关闭连接 (死锁风险)]----------+
                  |    Tab A 触发 onblocked 事件！                   |
                  |    模式升级被全局物理挂起，无法打开数据库！      |

在生产环境中，跨标签页的 `versionchange` 死锁是导致用户客户端数据库彻底崩溃的核心隐患。当用户长期打开一个后台标签页（运行旧版本代码），前台标签页在热更新后加载了新版本代码并尝试打开更高的数据库版本时，若旧标签页未注册 `db.onversionchange` 事件并及时调用 `db.close()`，新标签页将永久陷入 `onblocked` 挂起状态，无法进行任何读写。

事务模型与自动化生命周期绑定 (Transaction Auto-Commit)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
IndexedDB 的所有增删改查均必须包裹在显式事务（`IDBTransaction`）中。事务模式分为三类：
1. **`readonly`（只读事务）**：不阻塞其他只读事务，支持并发无锁读取；
2. **`readwrite`（读写事务）**：在目标 Object Store 范围施加排他互斥锁，保障 ACID 隔离性；
3. **`versionchange`（版本变更事务）**：独占整库排他锁，阻塞除自身外的所有连接。

**事务自动提交机制的物理陷阱（Auto-Commit Behavior）**：
IndexedDB 的事务并没有提供显式的 `tx.commit()` 方法（虽然现代标准补全了该方法，但历史核心机制是隐式的）。事务由**底层事件循环任务队列（Event Loop Task Queue）的空闲状态自动决定提交**：

.. code-block:: javascript

   const tx = db.transaction("drafts", "readwrite");
   const store = tx.objectStore("drafts");

   store.put({ id: 1, title: "Draft A" });

   // 危险反模式：在事务链路中引入异步宏任务或跨微任务边界
   setTimeout(() => {
     // 错误！此时当前微任务队列已清空，主线程事件循环已完成一次 Tick
     // 浏览器判定事务已自动提交关闭！
     // 下面的写入将直接抛出: DOMException: The transaction has already finished.
     store.put({ id: 2, title: "Draft B" });
   }, 100);

当一个事务发起的所有当前请求（Requests）全部完成，且当前主线程执行栈及其关联的微任务队列（Microtask Queue）变为空闲（No pending requests/tasks）时，浏览器内核会自动将该事务提交至持久化磁盘并将其关闭。因此，**严禁在 IndexedDB 事务的作用域内掺杂任意外部异步操作（如 `fetch()`、`setTimeout()`）**，否则事务必将提前自动提交并失效。

游标与索引范围遍历机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当查询结果集较大时，使用 `getAll()` 会将整个数据集合一次性深拷贝载入 V8 堆内存，极易诱发内存溢出。工业级实现必须采用基于游标（Cursor）的流式分页遍历：

.. code-block:: javascript

   const tx = db.transaction("tasks", "readonly");
   const index = tx.objectStore("tasks").index("created_idx");

   // 使用 IDBKeyRange 约束索引的上下界
   const range = IDBKeyRange.bound(
     new Date("2026-01-01"),
     new Date("2026-12-31"),
     false, // 包含下界
     false  // 包含上界
   );

   // 打开正向游标，按时间顺序增量推进
   const cursorRequest = index.openCursor(range, "next");

   cursorRequest.onsuccess = (e) => {
     const cursor = e.target.result;
     if (cursor) {
       processTask(cursor.value);
       // 显式推动游标跳跃前进，每次仅将单条记录加载至内存
       cursor.continue();
     } else {
       // 遍历结束
       finalizeProcessing();
     }
   };

------------------------------------------------------------------------
30.4 Cache Storage 与 Service Worker 请求响应缓存微架构
------------------------------------------------------------------------
如果说 IndexedDB 负责结构化业务实体数据的本地落盘，那么 **Cache Storage** 则是专门用于托管 **HTTP 网络请求与响应（Request / Response 对）**的底层流式缓存空间。它与 Service Worker 紧密咬合，构成了现代渐进式 Web 应用（PWA）与离线优先架构的传输层基础。

网络请求拦截与 Cache Storage 的物理协作链路
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Cache Storage 不仅可以在 Window 页面上下文中调用，更通常作为 Service Worker 后台线程的数据源：

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                           Service Worker 拦截与 Cache Storage 数据流向                            |
   +---------------------------------------------------------------------------------------------------+

     [Renderer 主线程 (页面)]                  [Service Worker 独立线程]               [Cache Storage]
               |                                           |                                  |
               | 1. fetch("/static/bundle.js")             |                                  |
               |==========================================>| (触发 onfetch 事件)              |
               |                                           |                                  |
               |                                           | 2. caches.match(event.request)   |
               |                                           |--------------------------------->|
               |                                           |                                  |
               |                                           | 3. 二进制流快速命中              |
               |                                           |<---------------------------------|
               |                                           |                                  |
               | 4. 零延迟直接返回 Response (200 OK)       |                                  |
               |<==========================================|                                  |
               |    (完全绕过网络栈与外部 HTTP 往返！)     |                                  |

核心物理特性与流式落盘
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
与 IndexedDB 的结构化对象序列化不同，Cache Storage 在 Chromium 内核中由底层的磁盘缓存子系统（Simple Cache 或 Blockfile）支撑：
1. **直接托管原始流（Streaming Body）**：
   Cache Storage 存储的是真实的 HTTP 报文元数据（Headers、Status Code）与二进制流体（ReadableStream）。当一个大体积的 WebAssembly 模块或音频文件写入 Cache Storage 时，数据可以直接从网络套接字（Socket）通过内核缓冲区流式写入物理磁盘，无需在 JavaScript 堆中完成全量字符串化装配，极大降低了内存驻留峰值。
2. **Response 对象的只读与消耗性（Single-Use Body）**：
   在 Fetch API 规范中，`Response.body` 是一个只能消费一次的可读流。一旦通过 `response.text()` 或直接返回给渲染引擎，流即被锁定读取。若需要同时将响应写入缓存并返回给页面，代码必须显式调用 `response.clone()`，由底层系统分流（Tee）出两份独立的流管道。

不透明响应 (Opaque Response) 的空间填充膨胀惩罚
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当应用通过 `fetch()` 跨域请求无 CORS 头的第三方资源时（`mode: 'no-cors'`），浏览器会返回一个状态码为 `0` 的**不透明响应（Opaque Response）**。为了防止恶意脚本通过探测存储配额消耗反推跨域资源的大小（侧信道时间与体积分析漏洞），浏览器强制对不透明响应实施了严苛的 **填充惩罚机制（Padding Mechanism）**：

- 在 Chromium 中，即使一个跨域不透明图片只有 5KB，将其存入 Cache Storage 时，浏览器配额计算器也会将其标记为**占用至少 7MB 甚至更高的虚拟配额（Padding Size）**。
- 如果开发者在 Service Worker 中盲目对 CDN 上的跨域子资源执行无 CORS 缓存，仅需数十个请求就会迅速击穿 Origin 的总配额上限，直接引发整站数据写入崩溃。

------------------------------------------------------------------------
30.5 现代离线优先 (Offline-First) 数据同步与跨标签页一致性架构
------------------------------------------------------------------------
结合上述底层存储引擎的物理特性，现代离线优先（Offline-First）架构必须在本地存储与远端数据库之间建立确定性的状态同步与冲突仲裁拓扑。

多级存储架构的分工全景
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. list-table:: 现代离线优先 Web 应用多级存储层级拓扑
   :widths: 15 25 35 25
   :header-rows: 1

   * - 存储层级
     - 承载实体
     - 数据一致性级别
     - 失效与恢复策略
   * - **L1: 内存状态**
     - Zustand / Redux 瞬时状态
     - 极低（随进程/Tab 销毁）
     - 从 L2 / L3 数据库秒级恢复
   * - **L2: 结构化数据库**
     - IndexedDB 本地实体与 Mutation 队列
     - 高（持久化磁盘，事务隔离）
     - 服务端版本号对比，乐观合并
   * - **L3: 二进制资源缓存**
     - Cache Storage (App Shell / 静态资源)
     - 中高（按 Service Worker 版本固化）
     - Cache-Tag 显式失效，激活阶段替换
   * - **L4: 远端权威源**
     - 服务端 PostgreSQL / MySQL
     - 绝对权威（ACID 唯一事实源）
     - WAL 日志顺序重放，权威冲突裁决

离线突变队列与乐观 UI 恢复流
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在断网环境下，用户的每一次增删改操作绝不能被系统丢弃，必须转化为自包含的本地突变事务：

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                                离线突变队列与乐观同步状态机流转                                   |
   +---------------------------------------------------------------------------------------------------+

     [用户点击提交表单: 修改项目标题]
            |
            v
     1. [UI 乐观更新]: 内存 Store 立即变更，界面秒级呈现新标题
            |
            v
     2. [写入 IndexedDB]: 开启只读写事务，并发完成双写操作：
            +---> 更新本地草稿记录: { id: "doc-1", title: "New Title", baseVersion: 12 }
            +---> 入队突变记录 (Mutations Store):
                  {
                    mutationId: "uuid-999",
                    entityId: "doc-1",
                    action: "UPDATE_TITLE",
                    payload: { title: "New Title" },
                    baseVersion: 12,
                    status: "PENDING_SYNC",
                    timestamp: 1772619000
                  }
            |
            v
     3. [网络感知监听]: 监听 window.addEventListener("online") 或 Background Sync
            |
            v
     4. [恢复在线网络同步]:
            +---> 从 IndexedDB 按 FIFO 顺序读取所有 status === "PENDING_SYNC" 记录
            +---> 向服务端批量提交变更 (携带 baseVersion: 12)
            |
            v
     5. [服务端仲裁执行]:
            +---[情况 A: 服务端当前版本仍为 12]---------------------+
            |    服务端写入成功，生成版本 13，返回 ACK              |
            |    客户端删除对应 Mutation 记录，更新 baseVersion: 13 |
            |                                                       |
            +---[情况 B: 服务端已被其他设备修改为版本 14 (冲突)]----+
                 服务端拒绝直接覆盖，返回 Conflict 数据快照
                 客户端根据策略（以服务端为准 / 三方合并 / 弹窗仲裁）
                 回滚或重新演进本地数据

跨标签页广播同步协议 (BroadcastChannel)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当用户在浏览器 Tab 1 中完成了数据修改或执行了用户登出时，Tab 2 必须即时感知并同步状态，避免跨页面数据污染：

.. code-block:: javascript

   // 建立同源全局广播管道
   const syncChannel = new BroadcastChannel("app_storage_bus");

   // Tab 1: 写入 IndexedDB 成功后发出事件
   async function commitTaskUpdate(task) {
     await idbPut("tasks", task);
     syncChannel.postMessage({
       type: "TASK_UPDATED",
       payload: { taskId: task.id, updatedAt: Date.now() }
     });
   }

   // Tab 2: 接收通知，精准刷新本地内存与视图
   syncChannel.onmessage = (event) => {
     if (event.data.type === "TASK_UPDATED") {
       const { taskId } = event.data.payload;
       // 精准从 IndexedDB 重载特定实体，更新内存 Store，规避全量重载
       reloadTaskToStore(taskId);
     } else if (event.data.type === "USER_LOGOUT") {
       // 执行跨标签页级联清理与强制跳转
       executeCascadePurgeAndRedirect();
     }
   };

退出登录的级联清理协议 (Cascade Purge Protocol)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在企业级安全架构中，退出登录绝不仅仅是销毁内存变量，必须实施严格的跨层级联清理协议：
1. **服务端终结**：向后端发起注销请求，服务端废弃 Redis / Session 中的 Token 实体；
2. **网络 Cookie 擦除**：服务端返回带有 `Max-Age=0` 的 `Set-Cookie` 指令，彻底清除鉴权 Cookie；
3. **本地敏感数据重置**：
   - 遍历清除 LocalStorage 与 SessionStorage 中携带用户身份与业务配置的键值；
   - 打开 IndexedDB 事务，清空包含业务实体与离线草稿的 Object Store；
   - 清理 Cache Storage 中缓存的用户私有 API 响应数据；
4. **多标签页广播同步**：通过 `BroadcastChannel` 广播 `USER_LOGOUT` 指令，强制所有并存的同源标签页同步清空内存 Store 并重定向至登录网关，杜绝公共机房环境下的数据泄漏隐患。

------------------------------------------------------------------------
小结与下卷导读
------------------------------------------------------------------------
本章作为 **Part 5: 客户端架构、DOM 抽象与前端运行时** 的收官之作，系统解构了现代 Web 客户端持久化存储的底层原理与物理约束：
- 建立了包含 Request-Bound、Origin 隔离、线程 I/O 调度与生命周期承诺的浏览器存储四维全景对比矩阵；
- 深入 Chromium / Blink 多进程微架构，揭秘了 Web Storage 同步 Mojo IPC 与 LevelDB 锁等待引发主线程卡死（INP 劣化）的物理本质，剖析了纯字符串序列化的 CPU 开销与配额崩溃风险；
- 全面拆解了 IndexedDB 底层基于 LSM-Tree / B-Tree 的存储映射模型，剖析了版本迁移事务（`versionchange`）在多标签页场景下的死锁诱因，明确了事务基于事件循环微任务空闲自动提交的物理边界；
- 深入解构了 Cache Storage 与 Service Worker 在流式请求响应托管中的微架构协同，指出了无 CORS 不透明响应（Opaque Response）空间填充膨胀带来的配额击穿隐患；
- 建立了面向现代离线优先（Offline-First）架构的四级存储拓扑，系统设计了离线突变队列（Mutation Queue）、跨标签页 `BroadcastChannel` 同步总线与退出登录级联清理协议。

至此，我们已经完成了对现代 Web **客户端运行时全部技术栈（DOM 抽象、Virtual DOM 调和、细粒度响应式、客户端路由、状态管理与持久化存储）**的体系化剖析。

在接下来的 **Part 6: 服务端、同构渲染与现代全栈范式** 中，我们将把视野从客户端沙箱推向数据中心与云端服务器。我们将跨越网络边界，深入探讨 Node.js、Deno 与 Bun 现代 JavaScript 服务端运行时的底层微架构（Chapter 31）。我们将深入剖析 libuv 线程池与 epoll / kqueue / io_uring 事件多路复用模型，解密服务端高并发 I/O 调度的物理机理。敬请期待下一模块的宏大探索！
