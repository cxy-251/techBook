========================================================================
Chapter 12: HTML 分词算法、容错机制与 DOM 树构建：从字节流到有向对象图
========================================================================

.. note:: 前置背景与认知承接
   前一模块系统解构了 Web 标准契约、URL 架构角色、传输层连接生命周期（DNS/TCP/TLS 1.3/QUIC）、HTTP 协议演进、缓存控制平面以及 Preload Scanner 预加载扫描器。当网络管道将首批 HTML 二进制字节流推送至浏览器渲染进程（Renderer Process）的内存缓冲区后，整个 Web 页面生命周期正式进入**文档构建与渲染执行阶段**。HTML 作为一种极具历史包容性的声明式标记语言，其解析算法不同于传统编译器的上下文无关文法（Context-Free Grammar）。浏览器内核必须在面对各种语法错误、标签未闭合及动态脚本注入时，保证 100% 确定性且不发生崩溃。本章将深入 Blink 与 WebKit 内核微架构，系统剖析字符流解码、WHATWG 状态机分词、栈驱动树构建算法、领养机构容错机制（Adoption Agency Algorithm）以及 C++/V8 内部 DOM 节点内存拓扑。

------------------------------------------------------------------------
12.1 字节流解码与输入流预处理 (Byte Stream to Unicode Stream)
------------------------------------------------------------------------

渲染进程的网络接收缓冲区（Network Buffer）最初接收到的是纯粹的物理字节序列（Octet Stream）。HTML 解析器的第一步，是通过严格的规范将字节流解码为连续的 Unicode 字符流（UTF-16 标量值）：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  HTML 字节流解码与字符预处理流水线                      |
   +-------------------------------------------------------------------------+

   [ 原始物理字节流 (Raw Byte Chunks) ]
        |
        v
   [ 1. 字符编码嗅探 (Encoding Sniffing: BOM -> HTTP Header -> <meta>) ]
        |
        v
   [ 2. 字符集解码器 (TextDecoder: 如 UTF-8 / GB18030 / Windows-1252) ]
        |
        v
   [ 3. 换行符规范化 (Newline Normalization: CRLF / CR -> LF (
)) ]
        |
        v
   [ 4. 非法字符清洗 (Invalid Character Replacement: U+0000 -> U+FFFD) ]
        |
        v
   [ 纯净 Unicode 标量字符流 (Unicode Stream) 送入分词器 ]

字符编码判定状态机与重解析代价 (Encoding Sniffing & Rollback)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

浏览器确定字符编码的优先级遵循严格的确定性阶梯：

1. **字节顺序标记（BOM - Byte Order Mark）**：检查文件最前端的特殊魔数（如 UTF-8 的 `0xEF 0xBB 0xBF`，UTF-16LE 的 `0xFF 0xFE`）；
2. **HTTP 响应头声明**：检查传输层 `Content-Type: text/html; charset=utf-8`；
3. **HTML 内联 `<meta>` 嗅探**：若前两项均未指定，解析器将读取 HTML 前 1024 字节，嗅探 `<meta charset="...">` 或 `<meta http-equiv="Content-Type">`；
4. **系统与区域默认编码**：最终回退至用户操作系统的本地默认配置（如 `windows-1252`）。

- **重解析回滚代价（Encoding Sniffing Rollback）**：若浏览器先以默认编码启动了解析流水线，随后在第 500 字节处发现 `<meta charset="gb18030">` 且与初始推断冲突，解析器必须**完全销毁已生成的全部 Token 与临时 DOM 树，将输入流回滚至偏移量 0，以全新解码器重新从头执行全量解析**。因此，将 `<meta charset="utf-8">` 置于 HTML `<head>` 最前端是消除 CPU 重复解析的硬性工程准则。

换行符与非法字符的物理规范化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **换行符统一化**：操作系统间的换行符各不相同（Windows 的 `CRLF (\r
)`，经典 Mac 的 `CR (\r)`，POSIX 的 `LF (
)`）。HTML5 规范要求预处理器在分词前将所有的 `\r
` 序列及单独的 `\r` 全部无条件替换为单一的 `
 (U+000A)`；
- **空字符置换**：C/C++ 字符串以 Null 字符 `\0 (U+0000)` 作为终止符。为了防止内存越界与安全解析截断漏洞，解析器将所有文本中的 `U+0000` 无条件替换为 Unicode 替换字符 `U+FFFD ()`。

------------------------------------------------------------------------
12.2 WHATWG 确定性有限状态机分词器 (HTML Tokenization State Machine)
------------------------------------------------------------------------

HTML 不是一种可以用经典 Lex/Yacc 或 LL(k)/LR(k) 编译器生成的上下文无关文法，其分词过程是一个包含 **80 多个离散状态的确定性有限自动机（DFA）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       HTML Tokenizer 核心状态流转拓扑                   |
   +-------------------------------------------------------------------------+

              +-------------------- 遇到普通字符 ---------------------+
              |                                                       |
              v                                                       |
         [ Data State ] <------------------------------------+        |
              |                                              |        |
              | 遇到 '<' 字符                                |        | 发射
              v                                              |        | Character Token
     [ Tag Open State ]                                      |        |
              |                                              |        |
              +-- 遇到 a-zA-Z -> [ Tag Name State ]          |        |
              |                        |                     |        |
              |                        +-- 遇到空白符 ------->+        |
              |                        |  (进 Before Attribute Name)  |
              |                        +-- 遇到 '>' ----------------->+
              |                        |  (发射 StartTag / EndTag)    |
              |                        +-- 遇到 '/' ----------------->+
              |                           (进 Self-Closing State)     |
              |                                                       |
              +-- 遇到 '/' ----> [ End Tag Open State ] ------------->+
              +-- 遇到 '!' ----> [ Markup Declaration Open State ] -->+ (DOCTYPE/Comment)

分词器输出的六大核心 Token 类型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: HTML Tokenizer 生成的原子 Token 类型结构
   :widths: 20 25 55
   :header-rows: 1
   :class: tight-table

   * - Token 类型
     - 携带的核心元数据
     - 物理含义与树构建器行为
   * - **DOCTYPE Token**
     - `name`, `publicIdentifier`, `systemIdentifier`, `forceQuirks`
     - 决定浏览器进入“标准模式（Standards Mode）”还是“怪异模式（Quirks Mode）”
   * - **Start Tag Token**
     - `tagName`, `selfClosingFlag`, `attributes` 键值对列表
     - 指示开启新元素节点，压入打开元素栈
   * - **End Tag Token**
     - `tagName`
     - 指示封闭当前层级元素，从打开元素栈弹出节点
   * - **Character Token**
     - Unicode 标量字符（UTF-16 字符块）
     - 创建或向当前游标文本节点追加文本内容
   * - **Comment Token**
     - 注释内容字符串（`data`）
     - 在当前父节点下挂载 `Comment` 节点
   * - **EOF Token**
     - 无
     - 输入流终结，触发未闭合标签强制闭合与树固化

特殊内容模型的动态分词分流 (RAWTEXT / RCDATA / Script Data)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

分词器的状态不仅仅由当前输入的字符决定，还**受到树构建器（Tree Builder）反馈的当前上下文约束**：

- **RAWTEXT 状态（如 `<style>`, `<iframe>`, `<noembed>`）**：解析器进入 RAWTEXT 模式，在此模式下，任何实体字符引用（如 `&lt;`、`&amp;`）均不被转义，任何内部的 `<` 字符只要后面紧跟的不是对应的闭合标签（如 `</style>`），均被直接当作纯文本字符发射；
- **RCDATA 状态（如 `<textarea>`, `<title>`）**：与 RAWTEXT 类似，不解析子 HTML 标签，但**允许转义字符实体**（`&copy;` 会被转义为 `©`）；
- **Script Data 状态（如 `<script>`）**：专门支持处理内联 JavaScript 中包含的 HTML 字符串字面量（如 `var a = "</div>";`），引入了严密的转义状态机防止过早闭合。

------------------------------------------------------------------------
12.3 栈驱动树构建算法与打开元素栈 (The Stack of Open Elements)
------------------------------------------------------------------------

分词器发射出的 Token 并不会在内存中全部积攒，而是**以流水线模式即时推送给树构建器（HTMLTreeBuilder）**。树构建器维护着两个关键的底层数据结构：

1. **当前节点游标（Current Node Pointer）**：指向当前正在接收子节点的容器；
2. **打开元素栈（The Stack of Open Elements）**：记录从根节点 `<html>` 到当前处理节点的全路径父子祖先嵌套关系。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                栈驱动 DOM 树构建流水线与打开元素栈状态机                |
   +-------------------------------------------------------------------------+

   [ Token 流传入: StartTag <p> ]
        |
        v
   [ 1. 查找当前插入模式 (Insertion Mode: 如 "In Body") ]
        |
        v
   [ 2. 实例化 Blink C++ 对象: RefPtr<HTMLParagraphElement> ]
        |
        v
   [ 3. 挂载至当前打开元素栈栈顶节点: stack.Top()->AppendChild(pNode) ]
        |
        v
   [ 4. 将新节点压入栈顶: stack.Push(pNode) ]

   [ Token 流传入: Character Token "Hello" ]
        |
        v
   [ 5. 检查栈顶是否为 Text 节点: stack.Top()->AppendData("Hello") ]

   [ Token 流传入: EndTag </p> ]
        |
        v
   [ 6. 检查栈顶节点标签名是否匹配: stack.Pop() 弹出当前节点 ]

树构建插入模式 (Insertion Modes) 状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

树构建器根据页面解析所处的阶段，在 23 种独立的**插入模式（Insertion Modes）**之间跳转：

.. list-table:: 核心 HTML 树构建插入模式与行为规则
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 插入模式名称
     - 触发条件与转移逻辑
     - 自动修正与隐式节点补全行为
   * - **Initial**
     - 解析起始阶段，等待 DOCTYPE Token
     - 若未遇到 DOCTYPE，强制设置怪异模式并转入 `Before HTML`
   * - **Before HTML**
     - 等待 `<html>` StartTag
     - 若遇到 `<body>` 或文字，**自动隐式创建 `<html>` 节点**并压栈
   * - **Before Head**
     - `<html>` 之后，等待 `<head>`
     - 若遇到 `<title>` 或非空白字符，**自动隐式创建 `<head>` 节点**
   * - **In Head**
     - 处理 `<meta>`, `<link>`, `<style>`, `<script>`
     - 遇到 `<body>` 或任何非法标签，**隐式闭合 `<head>`** 转入 `After Head`
   * - **In Body**
     - 处理主体绝大部分内容
     - 自动补全段落闭合，管理格式化元素
   * - **In Table**
     - 处理 `<table>` 内部结构
     - 严格约束仅允许 `<caption>`, `<colgroup>`, `<tbody>`, `<tr>`，触发 Foster Parenting

------------------------------------------------------------------------
12.4 活跃格式化元素列表与 Adoption Agency 容错算法
------------------------------------------------------------------------

在真实的 Web 页面中，充斥着大量未按 XML 规范严格嵌套的非法 HTML。最经典的反模式是**格式化标签交叉重叠（Misnested Formatting Tags）**：

.. code-block:: html

   <p>1<b>2<i>3</p>4</i>5</b>

若直接采用简单的递归下降栈，当遇到 `</p>` 时，栈内有 `[html, body, p, b, i]`，无法合法弹出 `p` 而保留 `b, i`。为了解决这一历史遗留问题，HTML5 制定了著名的**领养机构算法（Adoption Agency Algorithm - AAA）**。

活跃格式化元素列表 (List of Active Formatting Elements)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

树构建器引入了独立于打开元素栈的第二张表——**活跃格式化元素列表（Active Formatting Elements List）**，用于暂存行内格式化标记（`<b>`, `<i>`, `<a>`, `<span>`, `<em>`, `<font>` 等）。列表中还包含**标记点（Markers）**，用于限定格式化作用域。

领养机构算法 (AAA) 核心推演八步法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当在 `In Body` 模式下遇到一个格式化结束标签（如 `</i>` 或 `</b>`），且该标签不是当前栈顶元素时，触发 AAA 算法进行拓扑重组：

1. **定位目标格式化元素（Formatting Element）**：在活跃格式化列表中逆向查找最近的同名元素；
2. **定位最高层级节点（Furthest Block）**：在打开元素栈中，找到处于目标格式化元素之下的最高块级父容器；
3. **节点领养迁移（Adoption）**：将 Furthest Block 从原父节点脱离，重新作为格式化元素的子节点进行挂载；
4. **克隆格式化标记（Reconstruct Formatting Elements）**：自动克隆未闭合的 `<i>` 与 `<b>` 节点，分别注入到各个块级容器的切片内部。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |               Adoption Agency Algorithm 拓扑重构前后对比                |
   +-------------------------------------------------------------------------+

   [ 原始非法 HTML 输入 ]:
   <p>1<b>2<i>3</p>4</i>5</b>

   [ 经过 AAA 算法重构后的合法 DOM 对象树 ]:
   * p
     +-- "1"
     +-- b
         +-- "2"
         +-- i
             +-- "3"
   * b (自动克隆分裂出的新父节点)
     +-- i (自动克隆分裂出的新节点)
     |   +-- "4"
     +-- "5"

表格内容逃逸 (Foster Parenting) 容错机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当 HTML 在 `<table>` 与 `<tr>` 之间错误插入了非表格元素（如 `<table><div>Error Text</div><tr><td>Data</td></tr></table>`）：
- 插入模式 `In Table` 判定 `<div>` 为非法子元素；
- 触发 **Foster Parenting（寄养机制）**：解析器不会将该 `<div>` 挂在 `table` 内部，而是**将其强行提升至 `table` 之前的同级父节点中插入**，确保表格内部数据结构的严密性。

------------------------------------------------------------------------
12.5 Blink 内核 DOM 内存布局与 C++/V8 双向对象生命周期
------------------------------------------------------------------------

DOM 树不是抽象的逻辑图，而是常驻于渲染进程堆内存中的大型 C++ 对象有向图。

Blink C++ Node 内存布局与双向链表拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Chromium Blink 源码（`third_party/blink/renderer/core/dom/`）中，所有的 DOM 节点均继承自 `blink::Node`。为了兼顾高效的兄弟节点遍历、父节点回溯与极低的指针内存开销，DOM 树采用了**紧凑的四指针双向链表拓扑**：

.. code-block:: cpp

   // Blink 内核 Node 核心成员变量布局精简示意
   namespace blink {
   class Node : public GarbageCollected<Node> {
    protected:
       uint32_t node_flags_;             // 存储节点类型、状态标记位
       Member<ContainerNode> parent_;    // 指向父节点的垃圾回收托管指针
       Member<Node> previous_;           // 指向前一个兄弟节点
       Member<Node> next_;               // 指向后一个兄弟节点
       Member<TreeScope> tree_scope_;    // 指向所属 Document 或 ShadowRoot
   };

   class ContainerNode : public Node {
    private:
       Member<Node> first_child_;        // 指向第一个子节点
       Member<Node> last_child_;         // 指向最后一个子节点
   };
   }

.. list-table:: Blink DOM 节点内部四指针导航时间复杂度
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 导航操作 API
     - 底层 C++ 指针访问路径
     - 时间复杂度与内存特性
   * - `node.parentNode`
     - 直接解引用 `parent_` 指针
     - **严格 $O(1)$**
   * - `node.nextSibling`
     - 直接解引用 `next_` 指针
     - **严格 $O(1)$**
   * - `node.firstChild`
     - 直接解引用 `first_child_` 指针
     - **严格 $O(1)$**
   * - `node.childNodes[i]`
     - 自 `first_child_` 沿 `next_` 遍历 $i$ 次
     - $O(N)$（底层带遍历游标缓存加速）

Oilpan C++ 垃圾回收与 V8 DOM 包装器生命周期
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

DOM 树的生命周期管理横跨了 **Blink C++ 渲染引擎（使用 Oilpan 垃圾回收器）** 与 **V8 JavaScript 虚拟机（使用 V8 GC）** 两个独立的世界：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |               V8 JS 对象与 Blink C++ DOM 节点的跨世界双向绑定           |
   +-------------------------------------------------------------------------+

   [ V8 JavaScript 虚拟机堆内存 (V8 Heap) ]
   +-------------------------------------------------------------+
   |  JavaScript 变量: const el = document.getElementById('app') |
   |  v8::Object (JS DOM Wrapper 包装器对象)                      |
   |    - 内部字段 0 (Internal Field 0): WrapperTypeInfo         |
   |    - 内部字段 1 (Internal Field 1): 裸指针 -----------------+
   +-------------------------------------------------------------+
                                                                 |
        +--------------------------------------------------------+
        | (直接存储 C++ 对象的内存地址)
        v
   [ Blink 渲染引擎堆内存 (Oilpan Heap - C++) ]
   +-------------------------------------------------------------+
   |  blink::HTMLDivElement (C++ 原生节点对象)                   |
   |    - Member<Node> parent_ / first_child_                    |
   |    - TraceWrappers(): 告诉 V8 GC 该节点反向持有 V8 包装器   |
   +-------------------------------------------------------------+

- **跨边界垃圾回收协同（Unified Garbage Collection）**：
  若在 JS 中将 `el = null`，只要该节点依然连接在 DOM 树中，C++ 的 `parent_` 指针就会阻止 Oilpan 释放该节点；
  若从 DOM 树中调用 `node.remove()` 移除了节点，但 JS 变量 `window.savedNode = el` 依然持有引用，V8 GC 会在标记阶段通过统一垃圾回收接口告知 Oilpan：“该 C++ 对象受到 JS 根引用的保护，绝对不能回收！”，从而完美根除了跨语言内存泄漏与悬垂指针（Use-After-Free）。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从底层实现出发，系统解构了输入字节流的编码嗅探与 Unicode 规范化、WHATWG 确定性有限状态机分词器的 80+ 状态流转、树构建器的打开元素栈与 23 种插入模式、解决非法交叉嵌套的领养机构算法（Adoption Agency Algorithm）、表格寄养容错，以及 Blink 内核 C++ 节点四指针内存布局与 Oilpan/V8 统一垃圾回收模型。

在 DOM 树成功构建并驻留内存后，页面仅具备了结构与文本骨架，尚无任何颜色、尺寸与视觉坐标。下一章我们将进入渲染管线的第二核心阶段——**CSS 解析、级联规则与计算样式 (ComputedStyle)：从样式表到层叠样式树**，深度剖析 CSS 词法解析器、CSS 选择器匹配引擎、继承与层叠优先级权重计算，以及 Blink 如何将复杂的 CSS 规则编译为高效的只读 `ComputedStyle` 结构体。
