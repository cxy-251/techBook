================================================================================
Chapter 25: DOM API 内部实现机制：C++ 原生绑定、V8 包装器对象、属性穿透开销与事件流微架构
================================================================================

.. note:: 前置背景与认知承接
   在上一章中，我们深入剖析了 JavaScript 与 WebAssembly 的跨语言边界互操作，揭密了 V8 引擎内部调用跳板（Trampoline）、参数解包与打包、基于 `ArrayBuffer` 的线性内存直接穿透以及 FFI 调用的纳秒级物理开销（Chapter 24：JS 与 WASM 深度互操作）。然而，在真实前端应用中，最频繁、最基础的跨语言边界调用并非发生在 JS 与 WASM 之间，而是发生在 JavaScript 与浏览器内核原生 DOM（Document Object Model）之间。

   在日常业务开发中，开发者在脚本中书写 `document.getElementById()`、修改 `element.className` 或注册 `element.addEventListener()`，这些操作表面上与普通的 JavaScript 对象属性读写毫无二致。但从底层微架构审视，DOM 树并非驻留在 V8 垃圾回收堆中的原生 JavaScript 对象图，而是存在于浏览器渲染引擎（以 Chromium Blink 为代表）内部由 C++ 构建的复杂系统对象。本章将自底向上穿透这一层抽象：深入剖析 Blink 渲染引擎中 C++ DOM 树的真实内存拓扑与 Oilpan GC 托管机制；揭解 V8 包装器（Wrapper Object）与 C++ 原生节点之间的双向指针绑定与包装器缓存（Wrapper Cache）；详解跨越 V8 堆与 C++ 堆的联合垃圾回收（Unified GC / Cross-Component Tracing）如何解决跨语言循环引用内存泄漏；量化属性读写的跨边界穿透代价与强制同步重排（Layout Thrashing）的物理惩罚；最后系统拆解 DOM 三阶段事件流（Event Flow）在 C++ 内核中的调度状态机、Shadow DOM 事件重定位（Retargeting）以及被动监听器（Passive Event Listeners）解放主线程滚动性能的微架构机制。

------------------------------------------------------------------------
25.1 浏览器 DOM 的底层本质与 Blink C++ 物理内存拓扑
------------------------------------------------------------------------

在浏览器内核的物理架构中，JavaScript 虚拟机（如 V8）与文档渲染引擎（如 Blink、WebKit、Gecko）在历史上曾经是两个完全独立的系统组件。虽然在现代多进程浏览器中，它们被编译运行在同一个操作系统渲染进程（Renderer Process）的主线程中，但在内存布局和对象所有权上，两者依然有着清晰的物理分界。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                       Chromium 渲染进程主线程：V8 堆与 Blink C++ 堆的物理分离内存拓扑              |
   +---------------------------------------------------------------------------------------------------+

   +---------------------------------------+                   +---------------------------------------+
   | V8 托管内存堆 (V8 Managed Heap)       |                   | Blink 原生 C++ 堆 (Oilpan Managed Heap)|
   | (负责执行 ECMAScript 语法逻辑)        |                   | (负责解析 HTML、排版、绘制与树形状态) |
   +---------------------------------------+                   +---------------------------------------+
   |                                       |                   |                                       |
   |  [JS 变量: const div = ...]           |                   |  [blink::HTMLDivElement C++ 实例]     |
   |            |                          |                   |            ^                          |
   |            v                          |                   |            |                          |
   |  [v8::Object (DOM Wrapper)]           |                   |            |                          |
   |  +---------------------------------+  |                   |  +---------+-----------------------+  |
   |  | JS Object Header (Map / Class)  |  |                   |  | blink::Element 虚表指针 (vptr)  |  |
   |  | JS Properties / Elements Slots  |  |                   |  | blink::Node 父子兄弟节点指针:   |  |
   |  |---------------------------------|  |                   |  |   - parent_node_ (Member<Node>) |  |
   |  | Internal Field 0 (Type Tag)     |  |                   |  |   - first_child_ (Member<Node>) |  |
   |  | Internal Field 1:               |  | (原始 C++ 指针)   |  |   - next_sibling_(Member<Node>) |  |
   |  |   raw_ptr ----------------------+--+-------------------+->|  | AttributeCollection 属性容器    |  |
   |  +---------------------------------+  |                   |  | ComputedStyle 指针 (样式快照)   |  |
   |                                       |                   |  | LayoutObject 指针 (排版树映射)  |  |
   |                                       |                   |  +---------------------------------+  |
   |                                       |                   |            |                          |
   |                                       |                   |  (弱引用或 TraceWrapperMember)         |
   |                                       |                   |            v                          |
   |                                       |<------------------+--[ScriptWrappable 内部包装器引用]     |
   +---------------------------------------+                   +---------------------------------------+

DOM 树不是 JavaScript 对象
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

开发者所操作的 DOM 节点，其核心数据结构完全由 C++ 实现。在 Chromium Blink 内核源码中：
- `document` 对应 `blink::Document` 类的 C++ 实例；
- `<div>` 对应 `blink::HTMLDivElement` 类的 C++ 实例；
- 文本内容对应 `blink::Text` 类的 C++ 实例。

这些 C++ 实例的基类可以回溯至 `blink::Node` 与 `blink::EventTarget`。每一个 `blink::Node` 实例都在内部显式维护着用于构成树状拓扑的原生指针：指向父节点的 `parent_or_shadow_host_node_`、指向首个子节点的 `first_child_`、指向前一个兄弟节点的 `previous_sibling_` 以及指向后一个兄弟节点的 `next_sibling_`。此外，`Node` 内部还维护着指向所属 `Document` 的指针、标志位掩码（如当前节点是否处于悬挂状态、是否包含 ShadowRoot、是否失效等），以及与排版渲染密切相关的 `layout_object_` 关联指针。

Oilpan：Blink 的 C++ 追踪式垃圾回收系统
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

早期 WebKit/Blink 内核使用侵入式引用计数（`WTF::RefCounted<T>` 与 `scoped_refptr<T>`）来管理 DOM 节点的生命周期。但在复杂的 DOM 树操作中，跨节点循环引用（例如子节点引用父节点、事件监听闭包间接引用祖先节点）极其容易导致引用计数无法归零，进而引发隐蔽且严重的内存泄漏。

现代 Blink 彻底废弃了 DOM 树的纯引用计数管理，全面采用了名为 **Oilpan** 的 C++ 追踪式精确垃圾回收器（Precise Tracing Garbage Collector）：
1. **统一继承基类**：所有需要由 Oilpan 管理生命周期的 C++ 节点类型都必须继承自 `blink::GarbageCollected<T>`；
2. **托管指针机制**：节点之间的指针引用不再使用裸指针（Raw Pointers），而是封装在 `blink::Member<T>`（强引用托管指针）或 `blink::WeakMember<T>`（弱引用托管指针）智能指针模板中；
3. **Trace 追踪协议**：每个托管类都必须实现 `Trace(Visitor* visitor)` 方法，向垃圾回收器登记它所持有的所有 `Member<T>` 字段。在垃圾回收的标记阶段，Oilpan 会从根集合（如当前活跃的 `Document`、栈上寄存器或持久句柄）出发，沿着 `Trace` 方法构成的对象图完成全量可达性图标记。

当某个 DOM 子树从文档中移除（`list.removeChild(child)`）且 JavaScript 侧再无任何变量引用时，这组 C++ 节点将在 Oilpan 的下一个 GC 周期中被原子化扫描并成批销毁。

------------------------------------------------------------------------
25.2 V8 DOM Bindings 与 V8 包装器 (Wrapper Object) 微架构
------------------------------------------------------------------------

由于 JavaScript 无法直接读写 C++ 堆上的内存结构体，浏览器必须在两者之间构建一层高性能的中间翻译层，这一层被称为 **DOM Bindings（DOM 胶水绑定层）**。

Web IDL 规范驱动的代码生成流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Blink 并不依赖开发者或引擎工程师手动编写每个 DOM 方法的 C++ 桥接函数，而是采用由 **Web IDL (Web Interface Definition Language)** 规范驱动的自动化编译生成机制：

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                                 Blink DOM Bindings 自动化代码生成流水线                           |
   +---------------------------------------------------------------------------------------------------+

   WHATWG 标准 Web IDL 定义文件 (如 Element.idl):
   [Exposed=Window]
   interface Element : Node {
       [CEReactions] attribute DOMString id;
       [CEReactions] attribute DOMString className;
       Node appendChild(Node node);
   };
          |
          v (通过 Python 编写的 Blink IDL Compiler: code_generator_v8.py)
   +---------------------------------------------------------------------------------------------------+
   | 自动生成 C++ 粘合代码文件:                                                                         |
   | - v8_element.h / v8_element.cc                                                                    |
   |                                                                                                   |
   | 1. 生成 V8 模板构建逻辑 (v8::FunctionTemplate / v8::ObjectTemplate):                             |
   |    - 注册 JavaScript 原型链继承关系 (Element.prototype.__proto__ === Node.prototype)              |
   |    - 注册属性访问拦截器 (Accessor Getter/Setter 回调)                                             |
   |                                                                                                   |
   | 2. 生成方法调用分发器 (Method Callback Stubs):                                                    |
   |    - V8Element::AppendChildMethodCallback(const v8::FunctionCallbackInfo<v8::Value>& info)       |
   |                                                                                                   |
   | 3. 生成内部字段解包与类型转换逻辑:                                                                 |
   |    - 从 info.Holder() 提取内部字段 1 中的裸 C++ 指针 (blink::Element*)                             |
   |    - 将 V8 String / Object 转换为 Blink WTF::AtomicString / blink::Node*                          |
   +---------------------------------------------------------------------------------------------------+

包装器对象 (DOM Wrapper) 的结构剖析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当在 JavaScript 中执行 `const el = document.createElement('div')` 时，V8 引擎并不是凭空分配一个常规的 JavaScript 普通散列对象（Plain Object），而是通过预定义的 `v8::ObjectTemplate` 实例化一个具有特殊内部结构的 **DOM 包装器对象（DOM Wrapper）**。

在 V8 内部，常规 JavaScript 对象的结构包含：
- 指向隐藏类（Map）的指针；
- 指向属性存储数组（Properties Backing Store）的指针；
- 指向元素数组（Elements Backing Store）的指针。

而由 DOM 绑定所创建的包装器对象，其隐藏类在创建时被显式配置了固定数量的 **内部字段（Internal Fields）**。在 Chromium 的 64 位架构下：
- **Internal Field 0（类型标记 / Wrapper Type Info）**：存储指向静态结构体 `WrapperTypeInfo` 的原生内存指针。该结构体记录了该 DOM 对象的具体类型元数据（如该对象是 `HTMLDivElement` 还是 `SVGElement`）、C++ 虚函数查找表指针、以及专属的销毁回调函数；
- **Internal Field 1（原生对象裸指针 / C++ Instance Pointer）**：存储指向 Blink C++ 堆中真实 `blink::HTMLDivElement` 实例的 64 位裸物理内存指针。

当脚本访问 `el.id` 时，V8 引擎命中隐藏类上的访问器描述符（Accessor），直接触发由 IDL 生成的 C++ 静态桩函数 `V8Element::IdAttributeGetterCallback`。该函数从 V8 对象的 Internal Field 1 中直接解包出 `blink::Element*` 指针，随即调用 C++ 原生成员函数 `element->GetIdAttribute()`，将结果包装为 `v8::String` 返回给 JavaScript。

包装器缓存 (Wrapper Cache) 与 ScriptWrappable 机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

如果在脚本中多次访问同一个节点的属性，例如：

.. code-block:: javascript

   const a = document.getElementById("target");
   const b = document.getElementById("target");
   console.log(a === b); // 输出 true，引用全等！

为什么两次独立的 DOM 查询返回的 JavaScript 对象在引用上完全相同？

这是因为 Blink 实现了 **包装器缓存（Wrapper Cache）** 机制。每个可被脚本访问的 C++ DOM 节点都继承自 `blink::ScriptWrappable` 类。该类内部持有一个指向其 V8 包装器对象的反向引用。
1. **初次访问**：当某个 C++ 节点首次被暴露给 JavaScript 时，Blink 在 V8 堆中为其分配包装器对象，并将指向该包装器的引用保存在 C++ 节点的 `ScriptWrappable` 槽位中；
2. **后续访问**：无论通过 `getElementById`、`querySelector` 还是 `parentNode` 重新获取该节点，Blink 都会先检查 `ScriptWrappable` 中的缓存。如果缓存中的包装器仍然有效，则直接返回该现存的 `v8::Object` 句柄，从而杜绝重复分配，并确保了严格的语言级引用同一性（Identity Equality）。

跨垃圾回收器循环引用：Unified GC (跨组件追踪)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

V8 包装器与 C++ 原生节点构成的双向引用体系引发了整个浏览器内核中最棘手的内存管理挑战——**跨垃圾回收器孤岛的循环引用（Cross-Heap Cyclic References）**。

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                           V8 堆与 Oilpan C++ 堆之间的循环引用死锁示意图                           |
   +---------------------------------------------------------------------------------------------------+

   +---------------------------------------+                   +---------------------------------------+
   | V8 垃圾回收堆 (Orinoco GC)            |                   | Blink C++ 垃圾回收堆 (Oilpan GC)       |
   +---------------------------------------+                   +---------------------------------------+
   |                                       |                   |                                       |
   |   [v8::Object (DOM Wrapper)]          |                   |   [blink::HTMLDivElement]             |
   |   持有自定义 JS 属性:                 |                   |                                       |
   |   wrapper.callback = function() {     |                   |                                       |
   |     // 闭包捕获了另一个 DOM 节点包装器|                   |                                       |
   |     return anotherWrapper;            |                   |                                       |
   |   }                                   |                   |                                       |
   |      |                                |                   |                                       |
   |      | (Internal Field 1 持有强引用)  |                   |                                       |
   |      +--------------------------------+-------------------+--> 自身处于 DOM 孤岛中 (未挂载至文档)  |
   |                                       |                   |      |                                |
   |                                       |                   |      | (通过 DOM 树指针持有子节点)     |
   |                                       |                   |      v                                |
   |   [v8::Object (Another Wrapper)]      |                   |   [blink::HTMLSpanElement (子节点)]   |
   |      ^                                |                   |      |                                |
   |      |                                |                   |      | (ScriptWrappable 持有反向指针) |
   |      +--------------------------------+-------------------+------+                                |
   |                                       |                   |                                       |
   +---------------------------------------+                   +---------------------------------------+

在上述场景中，如果仅由 V8 单独执行垃圾回收，从 V8 根集合（全局作用域、执行栈）出发已无法直接触达 `wrapper`；但是由于包装器被 C++ 节点的 `ScriptWrappable` 持有，V8 只能将其标记为外部存活对象。同理，Oilpan 检查 C++ 堆时，虽然该 DOM 子树已经脱离主文档（孤岛），但因为子节点包装器仍然存活，使得整个子树无法释放。如果两个垃圾回收器各自为政，该结构将永久驻留在内存中。

为了根除这一泄漏，现代 Chromium 架构引入了 **Unified Garbage Collection（联合垃圾回收 / Cross-Component Tracing）**：
- 在 V8 进行增量标记（Incremental Marking）时，V8 会调用由 Blink 注册的跨组件追踪钩子；
- V8 遍历所有存活的 DOM 包装器，通过其内部指针直接通知 Oilpan 访问对应的 C++ 节点；
- Oilpan 随即以这些 C++ 节点为起点，沿着 C++ 内部的 `Member<T>` 指针遍历其子节点、父节点与关联对象；
- 当 Oilpan 发现被遍历到的 C++ 节点关联着其他 V8 包装器时，它会通过反向通道将这些包装器推回 V8 的标记工作列表（Marking Worklist）；
- 最终，V8 与 Oilpan 的对象图在逻辑上融为单一的统一拓扑图，只有当整个跨语言循环对象环整体与外部根集合断开联系时，两个堆上的对象才会在同一次协同 GC 周期中被安全回收。

------------------------------------------------------------------------
25.3 DOM 属性读写穿透开销与强制同步重排 (Layout Thrashing)
------------------------------------------------------------------------

当 JavaScript 代码执行单次 DOM 读写时，系统底层需要经历复杂的指令流转。

单次属性访问的物理调用序列
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以下列简单的属性读取为例：

.. code-block:: javascript

   const width = element.clientWidth;

这段脚本的底层执行经历了以下 7 级穿透调用链：
1. **V8 JIT 命中解构**：V8 引擎检查 `element` 隐藏类，发现 `clientWidth` 是一个位于原型链上的 AccessorDescriptor，调用由 Blink 预先绑定的 C++ 桩函数；
2. **上下文安全检查**：桩函数进入，执行上下文与同源策略校验，确认当前脚本执行的 ExecutionContext 具有访问目标 Document 的安全权限；
3. **指针提取与校验**：从当前对象的内部字段解包出 `blink::Element*` 原生指针，并执行空指针及节点是否已脱落（Disconnected）状态检查；
4. **触发渲染更新流水线**：`clientWidth` 的值并非静态保存在 `Element` 的成员变量中，它属于几何排版属性。Blink 内核判定当前文档的样式与排版状态是否“脏（Dirty）”；
5. **按需重算排版树**：如果当前存在未决的 DOM/CSS 修改，内核被迫在主线程立即同步暂停 JavaScript 虚拟机执行，直接调用 `Document::UpdateStyleAndLayoutForNode()` 强制完成样式重算与几何排版计算；
6. **读取排版对象物理盒模型**：从对应的 C++ `LayoutBox` 实例中读取实际渲染像素盒模型，扣除滚动条占位宽度后执行浮点到整数的四舍五入；
7. **数据封装与返回**：将提取出的整数打包为 V8 的带标记小整数（Smi），压入 JavaScript 执行栈并退出 C++ 边界返回脚本。

.. list-table:: JavaScript 内部属性与 DOM 绑定属性性能特征对比
   :widths: 22 28 25 25
   :header-rows: 1

   * - 访问类型
     - 底层机器指令与动作序列
     - 典型执行周期 (CPU Cycles)
     - 是否伴随连带副作用
   * - **普通 JS 对象属性读取**
     - TurboFan 编译为单条内存加载：`mov eax, [rbx + offset]`
     - **0.5 ~ 2 cycles**
     - 纯内存访问，单周期完成，无任何状态失效。
   * - **常规 DOM 属性读取** (如 `el.id`)
     - C++ Accessor 调用、解包裸指针、读取 `AtomicString`、转回 V8 字符串
     - **20 ~ 50 cycles**
     - 经历 C++ 函数调用跳板与类型封装，无渲染管线副作用。
   * - **几何布局 DOM 属性读取** (如 `el.offsetWidth`)
     - C++ 调用、安全检查、检查排版脏位标记、视情况强制同步重排
     - **50 ~ 数十万 cycles**
     - 若触发强制同步重排，将阻塞主线程数毫秒至数十毫秒！

强制同步重排 (Forced Synchronous Layout) 的级联惩罚
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

正常情况下，浏览器渲染引擎对 DOM 的修改采取 **批处理延迟更新（Batching & Deferred Updating）** 策略：在事件回调执行期间，脚本对 DOM 树的多次修改（如修改类名、设置宽高）只会在节点上打上标记（Invalidation Flags）。浏览器会延缓真实的几何重新计算，直到当前 JavaScript 任务彻底结束，在浏览器事件循环的渲染更新阶段（Update the Rendering），集中执行单次全局排版与绘制。

然而，如果代码在修改 DOM 之后，紧接着同步读取任何需要精确几何信息的值，批处理机制将被瞬间击穿：

.. code-block:: javascript

   // 工业级反模式：交错读写导致的布局抖动 (Layout Thrashing)
   function badResizeColumns(elements) {
     for (let i = 0; i < elements.length; i++) {
       // 1. 读取几何信息（此时由于上一轮循环写入了宽度，排版树已脏，内核被迫立即同步排版！）
       const currentWidth = elements[i].offsetWidth;
       // 2. 写入新宽度（立刻使排版树重新失效！）
       elements[i].style.width = (currentWidth + 10) + 'px';
     }
   }

在上述循环中，假设 `elements` 包含 100 个节点：
- 第 1 次循环写入 `style.width`，Blink 将布局标记为脏；
- 第 2 次循环读取 `offsetWidth`，内核发现布局脏位激活，**无法返回过期数据，必须立即挂起当前循环，对整棵 DOM 树重新执行样式计算与几何重排（Forced Synchronous Layout）**；
- 循环 100 次，导致单帧内执行了 100 次全局或局部同步排版！原本仅需 0.5 毫秒的逻辑，在低端设备上瞬间膨胀为耗时超过 50 毫秒的严重长任务（Long Task），直接引发页面掉帧与卡顿。

**架构优化范式：读写分离与批处理编排**：

.. code-block:: javascript

   // 正确范式：完全分离读取与写入阶段
   function optimizedResizeColumns(elements) {
     // 第一阶段：集中并发读取（只触发至多 1 次排版求值）
     const currentWidths = elements.map(el => el.offsetWidth);
     
     // 第二阶段：集中批量写入（延缓至下一渲染帧统一排版）
     elements.forEach((el, index) => {
       el.style.width = (currentWidths[index] + 10) + 'px';
     });
   }

------------------------------------------------------------------------
25.4 DOM 事件流 (Event Flow) 物理微架构：捕获、目标与冒泡
------------------------------------------------------------------------

DOM 事件系统并非简单的回调订阅发布中心，而是紧密结合 DOM 树拓扑结构的层次化状态机模型。

三阶段事件调度模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据 WHATWG DOM 规范，当用户在屏幕上触发物理交互（如点击输入）时，浏览器操作系统层将硬件中断转换为原始输入事件，渲染进程的输入事件处理器命中底层坐标处的渲染图层，并在 C++ 中构建出目标节点 `target`。随后，事件以该目标节点为核心，在 DOM 树中展开严格的三阶段分发：

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                                DOM 标准三阶段事件流分发全景拓扑图                                  |
   +---------------------------------------------------------------------------------------------------+

                    +---------------------------------------+
                    |                Window                 |
                    +---------------------------------------+
                       |                                 ^
        阶段 1: 捕获    |                                 |   阶段 3: 冒泡
        (Capturing)    |                                 |   (Bubbling)
                       v                                 |
                    +---------------------------------------+
                    |               Document                |
                    +---------------------------------------+
                       |                                 ^
                       v                                 |
                    +---------------------------------------+
                    |             <html> (Root)             |
                    +---------------------------------------+
                       |                                 ^
                       v                                 |
                    +---------------------------------------+
                    |                <body>                 |
                    +---------------------------------------+
                       |                                 ^
                       v                                 |
                    +---------------------------------------+
                    |            <div id="panel">           |
                    +---------------------------------------+
                       |                                 ^
                       |    +-------------------------+  |
                       +--->| <button id="targetBtn"> |--+
                            +-------------------------+
                                    阶段 2: 目标
                                   (Target Phase)

事件路径构建 (Event Path Construction) 内部算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++ 内核（`blink::EventDispatcher::DispatchEvent`）触发实际派发前，引擎必须先计算出本次事件流动的固定物理路径，这一过程称为 **事件路径构建（Event Path Construction）**：
1. **静态拓扑冻结**：从目标节点 `target` 开始，反复读取 `node->parentNode()`，一路向上回溯遍历，直到 `Document` 与 `Window` 对象；
2. **构建派发矢量数组**：将所有途经的祖先节点按顺序压入一个线性的 C++ 向量数组中，构建出单向链路：`[Window, Document, HTML, Body, Panel, Target]`；
3. **避免动态变异死锁**：一旦事件路径在开始前完成冻结构建，**即使某个事件监听器在执行过程中调用 `target.remove()` 将自身节点从 DOM 树彻底拔除，后续的冒泡传播依然会沿着预先构建好的祖先链条稳定推进，绝不会因为实时拓扑变异而崩溃中断**。

Shadow DOM 边界穿透与事件重定位 (Event Retargeting)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代 Web Components 与微前端架构中，Shadow DOM 引入了强隔离边界。为维护组件黑盒封装性，DOM 事件系统在跨越 Shadow Root 边界时会执行严密的 **事件重定位（Event Retargeting）** 算法：

.. code-block:: text

   外部主文档: <custom-editor> (拥有私有 ShadowRoot)
                     |
                     +-- ShadowRoot (封装边界)
                            |
                            +-- <div class="toolbar">
                                     |
                                     +-- <button class="bold-btn"> (真实物理点击 target)

如果该事件允许穿透边界（定义为 `composed: true`），当事件从 ShadowRoot 内部冒泡溢出至外部主文档时：
- 在主文档中的监听器读取 `event.target` 时，浏览器内核会自动将其重定位改写为宿主自定义元素 `<custom-editor>`，而不是暴露内部私有的 `<button>` 节点；
- 如果外部需要观测真实物理源头，需调用 `event.composedPath()`。该 API 返回完整的无裁剪路径数组，但在存在闭合 ShadowRoot（`mode: 'closed'`）时，闭合边界内部的节点依旧会被内核主动过滤剔除。

C++ 事件分发循环与阻断控制：`stopPropagation` vs `stopImmediatePropagation`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Blink 内部，节点派发事件的核心循环可抽象为如下伪代码状态机：

.. code-block:: cpp

   // Blink 内核事件派发状态机伪逻辑
   void EventDispatcher::DispatchEvent(Event& event, const EventPath& path) {
       // 阶段 1: 捕获遍历 (从根节点自顶向下推进至目标前驱节点)
       for (int i = path.size() - 1; i > 0; --i) {
           path[i].InvokeListeners(event, EventPhase::kCapturing);
           if (event.is_propagation_stopped_) return; // 检查是否阻断传播
       }

       // 阶段 2: 目标阶段 (在目标节点自身执行)
       path[0].InvokeListeners(event, EventPhase::kAtTarget);
       if (event.is_propagation_stopped_) return;

       // 阶段 3: 冒泡阶段 (自目标后继节点逆向冒泡回根节点)
       if (event.bubbles()) {
           for (size_t i = 1; i < path.size(); ++i) {
               path[i].InvokeListeners(event, EventPhase::kBubbling);
               if (event.is_propagation_stopped_) return;
           }
       }
   }

在此过程中，两个核心 API 对循环状态的控制存在本质区别：
- **`event.stopPropagation()`**：仅将 `event.is_propagation_stopped_` 标志位置为 `true`。当前节点上挂载的其余同类监听器仍会被全部执行完毕，但事件不会继续向路径中的下一个节点推进；
- **`event.stopImmediatePropagation()`**：同时将 `is_propagation_stopped_` 与 `is_immediate_propagation_stopped_` 均置为 `true`。内核**立刻强行终止当前节点剩余所有监听器的执行**，并立即中断整条事件链路。

被动事件监听器 (Passive Event Listeners) 的微架构革命
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在移动端设备上，用户执行滑动手势时，页面常常出现百毫秒级卡顿。这一顽疾的深层物理根因正是传统事件流机制对浏览器多线程架构的阻塞：

.. code-block:: text

   +---------------------------------------------------------------------------------------------------+
   |                    传统事件监听器 vs 被动事件监听器 (Passive Listeners) 线程时序对比              |
   +---------------------------------------------------------------------------------------------------+

   【传统监听器场景: el.addEventListener('touchstart', fn)】
   
   Compositor 线程 (合成线程)    | 主线程 (Main Thread / V8)
   -----------------------------+-----------------------------------------------------
   接收物理触控触摸包             | 
   检测到存在非 passive 监听器    | 
   被迫完全挂起暂停滚动流水线!  | 挂起中... 等待调度
   等待主线程反馈............... | 调度并执行 touchstart 回调函数
   ............................ | 函数执行耗时 150ms...
   ............................ | 函数末尾决定：未调用 preventDefault()
   收到通知：允许滚动            |<-- 回调完成
   终于启动图层合成滚动输出 (造成 150ms 严重手势延迟卡顿！)

   -----------------------------------------------------------------------------------
   【被动监听器场景: el.addEventListener('touchstart', fn, { passive: true })】
   
   Compositor 线程 (合成线程)    | 主线程 (Main Thread / V8)
   -----------------------------+-----------------------------------------------------
   接收物理触控触摸包             | 
   检测到 passive 标记激活       | 
   ★ 零延迟直接并发启动平滑滚动! | 异步将 touchstart 事件加入普通任务队列
   图层即时以 60/120fps 滑动    | 稍后在主线程空闲时被动执行监听器函数
   完全不受主线程业务阻塞影响!  | (若内部误调 preventDefault()，控制台直接抛警告忽略)

通过显式声明 `{ passive: true }`，开发者向浏览器内核做出了物理级承诺：**当前回调函数绝不会调用 `event.preventDefault()` 来取消默认行为**。合成器线程（Compositor Thread）因此无需等待主线程 JavaScript 执行完毕，可以直接独立在 GPU 图层中并发驱动页面物理滚动，彻底终结手势卡顿。

------------------------------------------------------------------------
25.5 事件代理 (Event Delegation) 与高频交互治理工程实践
------------------------------------------------------------------------

基于事件冒泡机制构建的 **事件代理（Event Delegation）** 是大型客户端架构中最重要的性能优化模式之一。

物理收益：内存足迹与垃圾回收降维
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

假设有一个包含 10,000 条复杂记录的虚拟化数据表格。如果为每一行的按钮单独绑定监听器：
- **V8 堆内存膨胀**：V8 必须在堆上实例化 10,000 个独立的 `JSFunction` 闭包对象；
- **Oilpan C++ 内存膨胀**：Blink 必须为每个 C++ 节点分别分配一个 `EventListener` 结构体，并在节点的事件监听映射表（`EventTargetData`）中注册对应条目；
- **GC 压力加剧**：这 10,000 个双向跨堆跨语言引用全部需要参与前文所述的 Unified GC 标记追踪，极大拖慢垃圾回收周期的全堆扫描速度。

采用事件代理模式，将事件统一委托至外层公共父容器节点（`<table>`）：
- V8 堆与 C++ 堆上的监听器对象数量从 10,000 个骤降至 **1 个**；
- 当动态添加、删除或置换列表行时，完全无需执行频繁的跨语言绑定与解绑操作（零 DOM Binding 写入），有效规避了内存碎片化。

边界限制与陷阱防范
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

尽管事件代理极具工程价值，但在系统级架构设计中必须明确其边界约束：
1. **天然不冒泡事件的物理失效**：标准规范中明确定义了部分事件不具备冒泡传播特性：
   - 焦点类事件：`focus` 与 `blur` 事件不冒泡。必须采用支持冒泡的等价事件 `focusin` 与 `focusout`，或者强制在捕获阶段（Capture Phase）进行代理；
   - 鼠标悬停类事件：`mouseenter` 与 `mouseleave` 不冒泡（专门设计用于避免穿透子元素触发伪震荡）。如果需要代理悬停逻辑，必须使用支持冒泡的 `mouseover` 与 `mouseout` 并严格校验 `relatedTarget`；
   - 媒体类与滚动类：`play`、`pause`、`load`、`scroll` 默认不冒泡。
2. **选择器匹配回溯的 CPU 损耗控制**：在事件代理处理函数中，开发者通常依赖 `Element.closest(selector)` 来定位触发事件的具体业务组件。然而，在具有深厚嵌套层级的 DOM 树上，如果每发生一次鼠标移动或点击都执行一次无限深度的祖先树回溯匹配，选择器编译与字符串匹配将成为新的 CPU 热点：

.. code-block:: javascript

   // 高性能事件代理设计模式
   const container = document.querySelector("#data-grid");

   container.addEventListener("click", (event) => {
     // 限制回溯范围不超过当前代理容器本身，避免溢出无界遍历
     const actionBtn = event.target.closest("[data-action]");
     if (!actionBtn || !container.contains(actionBtn)) {
       return;
     }

     const actionType = actionBtn.dataset.action;
     const rowId = actionBtn.closest("tr")?.dataset.rowId;
     
     handleAction(actionType, rowId);
   });

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章作为 **Part 5: 客户端架构、DOM 抽象与前端运行时** 的开篇之作，自底向上解构了 DOM API 在浏览器内核底层的真实系统实现：
- 揭示了 DOM 树驻留在 Blink C++ 堆上的物理本质，剖析了由 Oilpan GC 驱动的 C++ 节点生命周期管理；
- 深入解密了 V8 DOM 绑定层由 Web IDL 生成的代码骨干，揭示了 V8 包装器对象基于两个内部字段（Internal Fields）持有 C++ 裸指针的微架构，以及 `ScriptWrappable` 包装器缓存的工作原理；
- 剖析了跨越 V8 堆与 Oilpan 堆的统一垃圾回收（Unified GC / Cross-Component Tracing）机制，推导了其如何化解跨语言循环引用内存泄漏死锁；
- 量化了单次 DOM 属性读写的 7 级穿透调用链，推导了交错读写引发强制同步重排（Layout Thrashing）的物理惩罚与读写分离批处理防范策略；
- 全景拆解了 DOM 三阶段事件流的路径冻结构建算法、Shadow DOM 边界下的事件重定位机理、`stopPropagation` 与 `stopImmediatePropagation` 的内核状态机差异，以及被动监听器（Passive Listeners）解放主线程滚动的微架构革命；
- 建立了基于事件代理的内存治理工程范式，并标定了不冒泡事件与选择器回溯的性能边界。

正是由于跨越 DOM 胶水层直接读写 C++ 物理节点伴随着显微层面的 CPU 周期消耗、内存包装开销以及一旦处理不慎便极易引发的强制同步重排，现代工业级前端技术栈才发展出了各类旨在**抽象、缓存、合并并最小化直接 DOM 操作**的运行时代数体系。

在下一章中，我们将正式深入现代前端框架的核心基础设施——**Virtual DOM 协调算法与 React Fiber 并发架构**（Chapter 26）：深入剖析虚拟 DOM 树作为纯 JavaScript 内存数据结构的代数本质、Diff 算法从 $O(n^3)$ 到 $O(n)$ 的启发式剪枝、Fiber 节点链表双缓存架构（Double Buffering）、时间切片（Time Slicing）协同浏览器空闲调度的底层物理实现。敬请进入下一章的深度探索！
