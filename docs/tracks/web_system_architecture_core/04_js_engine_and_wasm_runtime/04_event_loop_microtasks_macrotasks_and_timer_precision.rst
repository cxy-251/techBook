========================================================================
Chapter 21: 事件循环微架构：任务队列、微任务清空机制、渲染帧时序与高精度计时
========================================================================

.. note:: 前置背景与认知承接
   在上一章中，我们系统剖析了 Google V8 垃圾回收微架构（Chapter 20：分代假设、Scavenger 新生代拷贝、Major GC 增量标记与 Orinoco 并发整理），明确了 JavaScript 堆内存中对象的生命周期与内存管理机制。垃圾回收器虽然通过后台并发 Worker 极大地缩减了主线程暂停时间（STW），但 JavaScript 代码本身的执行依然锚定在单个主执行线程之上。

   在浏览器或 Node.js 等宿主环境中，JavaScript 引擎并非孤立运行的机器，它必须与用户输入事件、网络 I/O、定时器、DOM 变更监听以及 60Hz/120Hz 的屏幕渲染管线实时协同。如果 JavaScript 采用多线程共享状态模型，DOM 树的并发读写将引入复杂的锁争用与死锁灾难；而若采用单纯的同步阻塞模型，任何耗时的网络请求或文件读取都将导致整个用户界面瞬间冻结。

   为了在单线程执行上下文下实现高并发、非阻塞的异步 I/O 与流畅的用户交互，现代 Web 平台构建了以 **事件循环（Event Loop）** 为中枢的调度体系。本章将深入解构事件循环的底层微架构：追踪 Task（宏任务）与 Task Source 多队列调度策略、剖析 Microtask Checkpoint 持续清空循环与饥饿风险、解密浏览器渲染机会（Rendering Opportunity）与 `requestAnimationFrame` 的精确时钟对齐、解剖定时器 4ms 物理嵌套下限与防御 Spectre 硬件攻击下的 `performance.now()` 时间量化机制，并揭示现代协作式调度器（`scheduler.postTask`、React Fiber）如何构建于宿主调度约束之上。

------------------------------------------------------------------------
21.1 宿主环境与事件循环中枢拓扑
------------------------------------------------------------------------

首先必须明确一个核心架构边界：**事件循环（Event Loop）不是 ECMAScript 语言规范定义的内置机制，而是由宿主环境（Host Environment，如 HTML 标准规定的浏览器渲染引擎或 libuv 驱动的 Node.js）提供并管理的并发调度框架**。

V8 引擎本身只负责给定一段 JavaScript 代码时分配内存、编译字节码、维护调用栈并执行同步指令；当代码遇到异步 API（如 `setTimeout`、`fetch`、`addEventListener`）时，V8 会通过 C++ 绑定将任务注册到浏览器宿主环境，随后立即清空调用栈。事件循环正是连接 V8 执行栈与宿主各底层子系统的调度中枢。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                                浏览器渲染进程主线程事件循环全景拓扑                               |
   +---------------------------------------------------------------------------------------------------+

   +--------------------------+    +-------------------------------------------------------------------+
   |  JavaScript 引擎 (V8)    |    |                     浏览器宿主环境 (Host Environment)             |
   |                          |    |                                                                   |
   |  [ 执行调用栈 Callstack ]|    |  [ 各种 Task Sources (宏任务源) ]                                 |
   |  | fnC()               | |    |  * User Interaction Queue (点击、输入、滚动事件)                  |
   |  | fnB()               | |    |  * Timer Task Queue (setTimeout / setInterval 触发)               |
   |  | fnA() (主脚本入口)  | |    |  * Networking Task Queue (Fetch / XHR 数据到达回调)               |
   |  +---------------------+ |    |                                                                   |
   |                          |    |  [ Microtask Queue (微任务队列) ]                                 |
   |  [ 堆内存 Heap Memory  ] |    |  * Promise Reaction Jobs (Promise.then / catch / finally)         |
   |  | 对象、闭包、上下文  | |    |  * queueMicrotask 回调                                            |
   |  +---------------------+ |    |  * MutationObserver 变更记录批处理回调                            |
   +--------------------------+    +-------------------------------------------------------------------+
                ^                                                |
                | (推入执行)                                      | (调度协调)
                +=================== [ Event Loop 调度中枢 ] <====+
                                             |
                                             v
   +---------------------------------------------------------------------------------------------------+
   |                              浏览器渲染流水线 (Rendering Pipeline)                                |
   |                                                                                                   |
   |  [ 渲染机会判定 (Rendering Opportunity) ] (根据屏幕 VSync 60Hz/120Hz 刷新周期决定是否触发)        |
   |  +---------------------------------------------------------------------------------------------+  |
   |  | 1. rAF 回调执行 (requestAnimationFrame) -> 准备下一帧几何/样式状态                           |  |
   |  | 2. Style (样式计算) -> Layout (排版布局) -> Paint (绘制指令) -> Composite (图层合成提交)     |  |
   |  +---------------------------------------------------------------------------------------------+  |
   |                                                                                                   |
   |  [ 空闲调度 (Idle Period) ] (若当前帧尚有空闲预算: 执行 requestIdleCallback 回调)                 |
   +---------------------------------------------------------------------------------------------------+

根据 WHATWG HTML 规范，一个标准的事件循环在每一次迭代（Tick）中严格执行以下有序动作：

1. **选择任务（Select Task）**：从所有处于可运行状态的 Task Queue 中，根据优先级策略选取一个最老的有效 Task；
2. **执行任务（Run Task）**：将该 Task 关联的回调函数压入 V8 调用栈，同步执行至调用栈完全清空；
3. **执行微任务检查点（Perform a Microtask Checkpoint）**：连续清空整个 Microtask Queue，直到队列中没有任何残留微任务（包括微任务执行期间新追加的嵌套微任务）；
4. **评估渲染机会（Update the Rendering）**：检查当前页面是否处于可见状态且到达屏幕刷新周期（如 16.6ms / 8.3ms）。若满足，依次触发 `requestAnimationFrame` 回调并执行样式计算、布局、绘制与图层合成；
5. **处理空闲时间（Idle Period）**：若本次 Tick 完成后距离下一次 VSync 信号仍有剩余计算预算，调度执行 `requestIdleCallback`。

------------------------------------------------------------------------
21.2 Task（宏任务）与 Task Source 多队列优先级微架构
------------------------------------------------------------------------

在工程交流中常被称为“宏任务”的概念，在 HTML 规范中被正式定义为 **Task**。Task 代表了事件循环中粒度最大的独立异步工作单元。

Task Source 与独立任务队列
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

规范明确指出：**事件循环并非仅拥有一个平铺的 Task Queue，而是存在多个与特定逻辑来源绑定的 Task Source**。浏览器引擎实现（如 Chromium Blink）会针对不同的 Task Source 建立多条物理队列，并根据当前用户交互状态动态赋予不同队列不同的调度权重：

.. list-table:: 典型 Task Source 分类与调度特征对比
   :widths: 22 25 30 23
   :header-rows: 1
   :class: tight-table

   * - Task Source (任务源)
     - 包含的典型操作与 API
     - 队列调度目标与策略
     - 优先级与饥饿风险
   * - **User Interaction**
     - `click`、`keydown`、`pointerdown`、`input` 事件派发
     - 优先保障用户即时输入响应，直接决定 Interaction to Next Paint (INP) 指标。
     - **最高优先级**。用户输入到达时立即插队调度。
   * - **Timer**
     - `setTimeout()`、`setInterval()` 回调执行
     - 经过设定的延迟时间后变为可运行状态。
     - **普通优先级**。在主线程高负载时会被延迟推迟。
   * - **Networking**
     - `fetch()`、`XMLHttpRequest`、WebSocket 数据到达
     - 由网络进程接收并组装完整数据后，向主线程派发回调任务。
     - **中等优先级**。按数据流就绪顺序轮询。
   * - **DOM Manipulation**
     - 非微任务类的历史导航、元素载入完成事件
     - 承载页面骨架生命周期的演进。
     - **普通优先级**。
   * - **Posting**
     - `window.postMessage()`、`MessageChannel.port.postMessage()`
     - 跨上下文或同一上下文内的协作式任务切片。
     - **高优先级**。常被用于绕过定时器最小延迟限制。

单次 Tick 只执行一个 Task 的物理约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

事件循环处理 Task 的核心法则是：**在单次循环迭代中，主线程仅从选中的 Task 队列中取出并执行严格一个 Task**。当该 Task 返回且调用栈清空后，事件循环立刻转向执行 Microtask Checkpoint，随后评估是否需要进入渲染流水线。

.. code-block:: javascript

   // 连续注册两个定时器 Task
   setTimeout(() => {
     console.log("Task A: 执行耗时同步工作");
     const start = performance.now();
     while (performance.now() - start < 50) {} // 阻塞主线程 50ms
   }, 0);

   setTimeout(() => {
     console.log("Task B: 紧随其后的定时器任务");
   }, 0);

在上述代码中，虽然两个 `setTimeout` 的延迟均为 0ms，但它们属于两个**完全独立的 Task**。当 Task A 运行时，主线程被其内部的 50ms 循环完全占领；Task A 结束退出后，浏览器并不会立即执行 Task B，而是先执行微任务检查点并检查屏幕刷新信号。如果此时正逢 VSync 刷新周期，浏览器将插队执行渲染管线，随后才在下一次 Tick 中取出 Task B 执行。

------------------------------------------------------------------------
21.3 Microtask Queue 与 Checkpoint 清空循环
------------------------------------------------------------------------

**Microtask（微任务）** 是为了在不交还主线程控制权给操作系统/浏览器宏观调度器前提下，实现局部状态一致性延续（Continuation）而设计的轻量调度机制。

Microtask 的执行触发点与 Checkpoint 算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

与 Task 每次仅执行一个不同，规范规定：**一旦触发 Microtask Checkpoint，事件循环必须持续出队并执行 Microtask，直到 Microtask Queue 彻底变为空（Queue is Empty）**。

微任务检查点（Microtask Checkpoint）在以下两个精确时刻被触发：
1. **当前 Task 的最外层 JavaScript 调用栈完全清空并即将返回宿主调度器时**；
2. **在脚本执行过程中，Web IDL 边界或特定规范算法显式调用 `perform a microtask checkpoint` 时**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  Microtask Checkpoint 内部清空循环状态机                |
   +-------------------------------------------------------------------------+

   [ 当前 Task 调用栈清空 / 显式 Checkpoint 触发 ]
                         |
                         v
                /-----------------\
                | Microtask Queue | <-----+ (微任务执行期间若产生新微任务)
                |   是否为空?     |       |
                \-----------------/       |
                   /            \         |
         (非空)   /              \ (已空) |
                 v                v       |
        [ 出队头部 Microtask ]   [ 结束 Checkpoint, 返回事件循环 ]
                 |                        |
                 v                        v
        [ 执行微任务函数 ] -----------> [ 评估渲染机会 / 下一个 Task ]

Microtask Starvation（微任务饥饿死锁）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于 Microtask Checkpoint 的退出条件是队列严格为空，**如果在微任务执行过程中不断向微任务队列追加新的微任务，事件循环将陷入死循环，永远无法退出 Checkpoint**：

.. code-block:: javascript

   function infiniteMicrotaskLoop() {
     Promise.resolve().then(infiniteMicrotaskLoop);
   }

   // 启动微任务风暴
   infiniteMicrotaskLoop();

在此场景下：
1. 虽然每次 `Promise.then` 回调只消耗极短的几个 CPU 指令周期，没有任何耗时的长同步循环；
2. 但 Microtask Queue 永远无法清空，主线程控制权永远无法交还给宿主环境；
3. **其破坏性等同于 `while(true) {}` 同步死循环**：所有后续 Task（用户点击、键盘输入、网络 I/O）被完全阻断，屏幕渲染管线彻底冻结，页面瞬间进入无响应（Crash / Freeze）状态。

.. list-table:: Task 与 Microtask 核心机制对比矩阵
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - Task (宏任务)
     - Microtask (微任务)
   * - **队列组织形式**
     - 多条 Task Source 独立队列，按优先级并发选取。
     - **全局唯一单向 FIFO 队列**。
   * - **单轮执行容量**
     - **每次 Tick 严格执行 1 个**。
     - **必须连续执行直至队列完全清空（Drain）**。
   * - **常见注册 API**
     - `setTimeout`、`setInterval`、`setImmediate` (Node.js)、I/O 事件、用户输入事件。
     - `Promise.then/catch/finally`、`queueMicrotask()`、`MutationObserver` 回调、`process.nextTick` (Node.js)。
   * - **执行时机**
     - 独立的一轮循环迭代起始端。
     - 当前 Task 结束退出后、进入渲染管线之前。
   * - **与渲染的关系**
     - 多个 Task 之间可能插入多次屏幕渲染。
     - **所有 Microtask 必须在下一次屏幕渲染前全部执行完毕**。

------------------------------------------------------------------------
21.4 事件循环与渲染流水线 (Rendering Pipeline) 时序交错
------------------------------------------------------------------------

在用户可见的交互链条中，最重要的认知是：**JavaScript 对 DOM 属性的修改只是修改了内存中的 C++ 对象树，并不等于屏幕像素已经同步呈现**。

渲染机会（Rendering Opportunity）判定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

屏幕显示设备通常以固定的物理刷新率（如 60Hz 对应每 16.66ms 刷新一次，120Hz 对应每 8.33ms 刷新一次）向 GPU 发送垂直同步信号（VSync）。浏览器为了消除画面撕裂（Tearing）并节省 GPU 功耗，并不会在每个 Task 完成后都触发渲染，而是**仅在捕获到 VSync 信号且页面处于可见状态时，才会开启渲染机会（Rendering Opportunity）**。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                           单帧时间内事件循环与渲染管线时序演进全景                                |
   +---------------------------------------------------------------------------------------------------+

   时间轴 (16.66ms @ 60Hz) ---------------------------------------------------------------------------->

   [ VSync 信号区间 ]
   +---------------+---------------+---------------+---------------------------------------------------+
   | Task 1 (点击) | Microtasks    | Task 2 (I/O)  | Microtasks  | Task 3 (Timer)| Microtasks          |
   | 修改 DOM 状态 | 批处理更新    | 读取数据      | 状态收敛    | 辅助计算      | 状态收敛            |
   +---------------+---------------+---------------+---------------------------------------------------+
                                                                                     |
                                                                                     v (VSync 刷新触发!)
   +---------------------------------------------------------------------------------------------------+
   |                                渲染更新流程 (Update the Rendering)                                 |
   |                                                                                                   |
   | 1. 处理窗口 Resize / Scroll 事件派发                                                               |
   | 2. 执行 requestAnimationFrame (rAF) 回调队列 (准备当前帧视觉动画数据)                             |
   | 3. 执行 IntersectionObserver 回调                                                                 |
   | 4. Recalculate Styles (重新计算 CSSOM 继承与层叠样式)                                             |
   | 5. Layout (重新排版计算几何包围盒与盒模型)                                                         |
   | 6. Update Layer Tree & Paint (更新属性树并生成光栅化绘图指令列表)                                 |
   | 7. Commit to Compositor (将绘制指令与图层提交至 GPU/Compositor 线程并触发最终光栅化上屏)          |
   +---------------------------------------------------------------------------------------------------+
                                                                                     |
                                                                                     v
                                                                 [ 空闲期: requestIdleCallback ]

`requestAnimationFrame` 的精确时钟锚定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`requestAnimationFrame(callback)`（简称 rAF）的架构设计目标是：**将动画回调的执行时机严格绑定在浏览器下一次物理绘制（Paint）之前**。

- **高精度时间戳输入**：rAF 回调接收一个由硬件时钟驱动的高精度时间戳参数（`DOMHighResTimeStamp`），该时间戳代表当前渲染帧启动的基准时间点，确保所有注册在同一帧的 rAF 回调基于完全一致的时间基准计算位移，彻底杜绝动画抖动（Jank）；
- **执行顺序保障**：rAF 回调的执行**晚于**前序所有 Task 与 Microtask，但**早于**当前帧的 Style/Layout 计算；
- **批处理渲染保护**：在 rAF 中修改 DOM 属性，修改结果将直接合并进入紧随其后的 Style/Layout 阶段，实现单次物理渲染呈现最终形态。

------------------------------------------------------------------------
21.5 定时器微架构、4ms 嵌套下限与高精度计时硬件约束
------------------------------------------------------------------------

`setTimeout` 与 `setInterval` 是 Web 平台最早提供的异步调度原语，但其底层实现受到操作系统时钟中断精度、能耗管理与安全防御的多重物理制约。

4ms 嵌套定时器物理下限 (Timer Clamping)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据 HTML 规范定义：当 `setTimeout` 的嵌套层级（Nesting Level）达到 **5 层以上** 时，即使开发者指定的延迟时间为 `0ms`（或小于 4ms），**浏览器引擎强制将延迟时间向上收紧（Clamp）至最小 4ms**。

.. code-block:: javascript

   let count = 0;
   let lastTime = performance.now();

   function benchmarkTimer() {
     const now = performance.now();
     console.log(`第 ${count} 次执行, 真实流逝时间: ${(now - lastTime).toFixed(2)}ms`);
     lastTime = now;
     count++;
     if (count < 8) {
       setTimeout(benchmarkTimer, 0); // 即使显式指定 0ms
     }
   }

   benchmarkTimer();

.. code-block:: text

   [ 浏览器控制台实测输出 ]
   第 0 次执行, 真实流逝时间: 0.00ms
   第 1 次执行, 真实流逝时间: 1.12ms  (嵌套层级 1)
   第 2 次执行, 真实流逝时间: 1.05ms  (嵌套层级 2)
   第 3 次执行, 真实流逝时间: 1.20ms  (嵌套层级 3)
   第 4 次执行, 真实流逝时间: 1.10ms  (嵌套层级 4)
   第 5 次执行, 真实流逝时间: 4.85ms  (嵌套层级 5 -> 触发 4ms Clamping!)
   第 6 次执行, 真实流逝时间: 4.90ms  (嵌套层级 6 -> 触发 4ms Clamping!)
   第 7 次执行, 真实流逝时间: 4.80ms  (嵌套层级 7 -> 触发 4ms Clamping!)

4ms 限制的历史与物理根源：
1. **防止 CPU 满载与能耗失控**：早期的 PC 操作系统时钟中断频率通常为 100Hz ~ 1000Hz。若允许页面无限制执行 0ms 定时器死循环，CPU 将无法进入 C-State 节能休眠状态，导致笔记本电脑电池迅速耗尽；
2. **后台标签页节流（Background Tab Throttling）**：当浏览器标签页被切换至后台不可见状态时，现代浏览器会进一步施加严格节流，将定时器最小间隔强制拉长至 **1000ms（1秒）** 甚至完全暂停，直到标签页重新激活。

Spectre 硬件漏洞与 `performance.now()` 时间量化防御
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 2018 年曝光的 **Spectre（幽灵）微架构侧信道攻击** 中，攻击者利用现代 CPU 的分支预测（Branch Prediction）与推测执行（Speculative Execution）机制，通过测量高精度定时器的纳秒级访问时延差异，能够逆向推导 CPU L1/L2 缓存中的跨进程私有内存数据。

为了阻断微架构侧信道攻击，W3C 与各大主流浏览器对高精度时间接口 `performance.now()` 实施了强制的 **时间粗化量化（Time Coarsening / Quantization）与随机抖动（Jittering）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     高精度时间戳量化防御模型                            |
   +-------------------------------------------------------------------------+

   [ 原始物理硬件时钟 (TSC 寄存器) ] (精度: 亚纳秒级 0.000001ms)
                  |
                  v
   [ 跨域隔离安全策略评估 (Cross-Origin Isolation) ]
         /                                 \
        / (未开启隔离)                      \ (已开启 COOP + COEP 隔离)
       v                                     v
   [ 强制时间粗化 (Coarsened) ]        [ 恢复微秒级高精度 ]
   * 精度强制降低至 100μs ~ 5μs        * 允许精度达到 5μs (0.005ms)
   * 注入伪随机时钟抖动 (Dithering)    * 依然防御超高精度纳秒探测
                  |                                  |
                  +-----------------+----------------+
                                    |
                                    v
                  [ 返回 performance.now() 给 JavaScript ]

开启跨域隔离（Cross-Origin Isolation）的必要配置：
通过在服务端 HTTP 响应头配置 `Cross-Origin-Opener-Policy: same-origin` 与 `Cross-Origin-Embedder-Policy: require-corp`，浏览器将页面运行在物理隔离的专用操作系统进程中，此时 `performance.now()` 的分辨率才被允许从粗化的 100$\mu s$ 恢复至 5$\mu s$。

------------------------------------------------------------------------
21.6 协作式任务调度演进：MessageChannel、IdleCallback 与 Scheduler API
------------------------------------------------------------------------

随着前端单页应用与数据可视化复杂度的爆发式增长，在主线程上执行大计算量任务极易突破 16.66ms 的单帧预算，引发严重的长任务（Long Task，耗时超过 50ms 的任务）。为此，Web 平台与开源社区演进出了一系列协作式任务调度模式。

MessageChannel 宏任务切片原语
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了规避 `setTimeout(fn, 0)` 嵌套 5 层后的 4ms 强制延迟惩罚，早期的高性能任务调度器（包括 React Scheduler）普遍采用 `MessageChannel` 作为 **0ms 宏任务切片** 的底层基础设施：

.. code-block:: javascript

   function yieldToMainThread() {
     return new Promise((resolve) => {
       const channel = new MessageChannel();
       channel.port1.onmessage = () => resolve();
       channel.port2.postMessage(null); // 向端口派发消息, 立即将 resolve 排入下一个 Task
     });
   }

   async function processLargeDataset(items) {
     let lastYield = performance.now();
     for (let i = 0; i < items.length; i++) {
       // 执行部分复杂数据处理
       computeItem(items[i]);

       // 检查当前任务是否已连续运行超过 5ms
       if (performance.now() - lastYield > 5) {
         await yieldToMainThread(); // 主动让出主线程控制权给浏览器, 允许响应用户输入与渲染!
         lastYield = performance.now();
       }
     }
   }

`requestIdleCallback` 的机制与局限
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`window.requestIdleCallback(callback, { timeout })` 允许开发者在浏览器主线程每一帧的空闲期（Idle Period）执行低优先级后台任务：

- **空闲时间预算计算**：回调函数接收一个 `IdleDeadline` 对象，`deadline.timeRemaining()` 动态返回当前帧距离下一次 VSync 信号剩余的毫秒数（最大不超过 50ms）；
- **局限性与风险**：在持续高频用户输入或复杂动画场景下，主线程可能连续数十帧没有任何空闲时间；若未设置 `timeout` 参数，注册的任务可能面临长期饥饿延后；此外，Safari / WebKit 长期未原生支持该 API。

WICG 原生优先级调度管道：`scheduler.postTask()`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了从浏览器内核底层统一任务优先级治理，WICG 推出了原生的 **Prioritized Task Scheduling API（`scheduler.postTask`）**。该 API 允许开发者直接指定任务的语义优先级，并支持通过 `AbortController` 动态取消或变更优先级：

.. code-block:: javascript

   // 1. 用户关键阻塞型任务 (抢占执行)
   scheduler.postTask(() => handleCriticalInput(), { priority: "user-blocking" });

   // 2. 普通用户可见任务 (默认优先级)
   scheduler.postTask(() => renderSecondaryList(), { priority: "user-visible" });

   // 3. 后台静默预加载/埋点计算 (空闲执行)
   const abortController = new TaskController({ priority: "background" });
   scheduler.postTask(() => runBackgroundIndexing(), { signal: abortController.signal });

.. list-table:: 原生任务调度机制全维度对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 调度 API / 原语
     - 任务类型归属
     - 最小延迟开销
     - 核心应用场景与工程考量
   * - **`setTimeout(fn, 0)`**
     - Task (Timer)
     - $\ge 4	ext{ms}$ (嵌套 5 层后)
     - 传统延时与防抖节流；不适合高频动画与密集任务切片。
   * - **`MessageChannel`**
     - Task (Posting)
     - $< 0.1	ext{ms}$ (零 4ms 惩罚)
     - React Scheduler 等框架用于构建自研协作式时间切片（Time Slicing）。
   * - **`requestAnimationFrame`**
     - 渲染前 Frame Callback
     - 动态对齐 VSync (16.6ms / 8.3ms)
     - 视觉动画更新、DOM 几何变换、下一帧状态初始化。
   * - **`requestIdleCallback`**
     - Idle Task
     - 视帧空闲预算而定 ($\le 50	ext{ms}$)
     - 埋点数据上报、后台缓存清理、不影响当前界面的预计算。
   * - **`scheduler.postTask`**
     - 内核原生优先级 Task
     - 动态内核队列调度
     - 现代 Web 应用统一调度中枢；支持优雅取消与多级优先级队列流转。

------------------------------------------------------------------------
21.7 现代框架调度器与宿主事件循环的映射拓扑
------------------------------------------------------------------------

现代前端框架（如 React、Vue、Svelte）在框架层提供了丰富的并发渲染与响应式批量更新特性。必须明确：**所有框架层的调度算法，最终都必须完全编译或降级映射到宿主环境的 Task 与 Microtask 规范边界之上**。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                                现代框架调度器与宿主事件循环映射矩阵                               |
   +---------------------------------------------------------------------------------------------------+

   [ 框架状态变更触发: setState() / reactive mutation ]
                           |
            +--------------+--------------+
            |                             |
            v                             v
   [ 框架 A: React Fiber 并发调度 ]    [ 框架 B: Vue / Svelte 响应式批处理 ]
   * 采用时间切片 (Time Slicing)       * 采用微任务批处理 (Microtask Batching)
   * 将大组件树拆解为 Fiber 链表       * 收集当前同步代码中的全部响应式变更
   * 每执行 5ms 工作即主动 Yield       * 将整体 flush 更新推入单次 queueMicrotask / Promise.then
            |                             |
            v (映射为 Task)               v (映射为 Microtask)
   +---------------------------------+ +---------------------------------------------------------------+
   | 宿主 Task (MessageChannel)      | | 宿主 Microtask (Promise Reaction / MutationObserver)          |
   | * 每次交出主线程控制权           | | * 在当前 Task 结束前以 Microtask 批量更新全部 DOM 节点        |
   | * 允许浏览器优先插入渲染与输入   | | * 确保在下一次物理渲染前，呈现最终一致的 DOM 状态             |
   +---------------------------------+ +---------------------------------------------------------------+

三大主流框架底层的宿主事件循环落地点：
1. **React 18/19 Concurrent Mode 与 Fiber 调度器**：
   - React 构建了双缓存 Fiber 树结构。其内部的 `Scheduler` 默认以 **5ms** 为一个时间切片单位；
   - 当检测到当前时间切片耗尽时，React 通过 `MessageChannel` 安排一个后续的宿主 Task，将主线程归还给浏览器；
   - 使得高优先级的离散用户输入（如输入框按键）能够抢占并打断低优先级的 Transition 渲染树构建，从根源上降低 INP 指标。
2. **Vue 3 响应式系统与 `nextTick()`**：
   - Vue 的响应式变更（Reactivity）在同一个事件回调中多次修改状态时，并不会触发多次 DOM 操作；
   - 内部通过 `queueJob()` 维护一个去重的更新队列，并调用 `Promise.resolve().then(flushJobs)` 将其排入宿主 **Microtask Queue**；
   - 因此，Vue 官方提供的 `nextTick()` 本质上就是返回一个紧随 `flushJobs` 之后的 Promise 微任务，确保开发者在回调中能够读取到已同步至 DOM 树的最新节点状态。
3. **Svelte 5 编译器驱动的 `tick()`**：
   - Svelte 同样将待处理的组件状态变更（Pending State Changes）汇聚在微任务阶段统一应用；
   - `tick()` 返回一个在当前全部微任务刷新完成后的 Promise。

长任务（Long Tasks）与 INP 劣化的微架构排查拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Google Core Web Vitals（核心网页指标）中，**INP（Interaction to Next Paint）** 衡量了从用户发起点击、按键或触摸到浏览器完成下一帧渲染呈现的最长交互延迟。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                             INP 交互延迟全链路耗时解构与排查拓扑                                  |
   +---------------------------------------------------------------------------------------------------+

   用户交互输入 (PointerDown)
        |
        | 1. 输入延迟 (Input Delay): 前序未完成的长任务 (Long Task) 正在霸占主线程, 导致事件回调无法启动!
        v
   [ 事件回调 Task 启动 ] (Event Handler Execution)
        |
        | 2. 处理耗时 (Processing Duration): 同步长任务计算、繁重的框架 Diff、强行读写布局 (Layout Thrashing)
        v
   [ Microtask Checkpoint ]
        |
        | 3. 微任务雪崩 (Microtask Starvation): 嵌套 Promise 链过长, 导致 Checkpoint 无法及时退出
        v
   [ 渲染更新 (Update the Rendering) ]
        |
        | 4. 呈现延迟 (Presentation Delay): rAF 回调阻塞、复杂 CSS 计算、超大 DOM 树重排与 GPU 合成耗时
        v
   最终物理像素发光呈现 (Next Paint Completed)

工业级排查决策链：
- 若 **Input Delay** 偏高：表明主线程常驻其他无关的长任务（如第三方分析脚本、离屏复杂计算），需通过 `scheduler.postTask({ priority: 'background' })` 或 Web Worker 迁出非关键代码；
- 若 **Processing Duration** 偏高：表明事件回调自身过于沉重，必须引入 `MessageChannel` 宏任务时间切片或框架级的 `startTransition` 拆解状态更新；
- 若 **Presentation Delay** 偏高：表明 DOM 节点规模过大或图层绘制复杂度超标，应重点重构 CSS 属性树与降低重排（Reflow）面积。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章深入探讨了现代 Web 平台的事件循环微架构与异步调度体系：
- 确立了事件循环作为宿主环境（Host Environment）协调 V8 执行栈、Task Sources 与渲染流水线的核心边界；
- 解构了 Task（宏任务）多队列优先级调度与单次迭代严格执行一个 Task 的物理约束；
- 剖析了 Microtask Queue 在 Checkpoint 阶段的持续清空机制，揭示了微任务饥饿死锁的破坏机理；
- 建立了屏幕垂直同步信号（VSync）驱动下的渲染机会判定模型，阐明了 `requestAnimationFrame` 帧回调与几何计算的时钟对齐机制；
- 深入推导了定时器 5 层嵌套触发 4ms 物理下限的根源，以及防御 Spectre 侧信道攻击下 `performance.now()` 的时间戳粗化量化模型；
- 追踪了从 `MessageChannel` 宏任务切片到 WICG 原生 `scheduler.postTask` 优先级管道的演进历程；
- 建立了现代前端框架（React Fiber、Vue nextTick）与底层宿主调度边界的精确映射矩阵，并给出了 INP 长任务排查全链路决策拓扑。

在下一章 **Chapter 22: Web 多线程架构：Web Workers、SharedArrayBuffer 与 Atomics 原子操作** 中，我们将走出主线程事件循环的单线程天地，深入真正的 Web 多线程世界：解构 Dedicated Worker、Shared Worker 与 Service Worker 的线程隔离与 IPC 通信机制、深入基于 `SharedArrayBuffer` 的跨线程共享内存模型，并剖析 `Atomics` 硬件级原子操作与 Futex 式等待唤醒（`wait/notify`）机制。
