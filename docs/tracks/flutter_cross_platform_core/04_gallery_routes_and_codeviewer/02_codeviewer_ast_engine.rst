========================================================================================
第 2 节：CodeViewer 源码查看器引擎：语法分词高亮、双视图联动与剪贴板管道
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/codeviewer/code_style.dart``、``cxyFork-gallery/lib/pages/demo.dart`` 与 ``code_segments.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/painting/text_span.dart`` 与 ``packages/flutter/lib/src/services/clipboard.dart``
   * **核心使命**：以大型组件库与教学工程的源码交互体验为基准，深度解构 Gallery CodeViewer 语法高亮引擎的词法标记流解析、基于 ``CodeStyle``（``InheritedWidget``）的语法着色分发拓扑、零 Widget 节点开销的扁平化 ``TextSpan`` 树构建、Demo 运行画板与 Code 源码查看器的双视图状态同步、以及基于 ``ServicesBinding`` 原生二进制通道的跨端剪贴板数据同步机制。

----------------------------------------------------------------------------------------

第一幕：词法分词与 `CodeStyle` 语法着色设计令牌
----------------------------------------------

在组件演示工程中，直接将代码作为普通纯文本（String）展示会极大破坏代码的可读性；而如果引入包含完整编译器前端的庞大语法分析库，又会导致应用打包体积激增数十兆。

Gallery 实现了轻量级高性能的词法高亮引擎，其核心样式分发由 ``CodeStyle`` 统领：

.. code-block:: text

   CodeStyle (InheritedWidget 语法着色中枢)
        │
        ├── baseStyle          (基础单色等宽字体: RobotoMono / Courier)
        ├── keywordStyle       (关键字高亮: class, extends, const, return, final, void)
        ├── classStyle         (类名与类型高亮: PascalCase 标识符)
        ├── stringStyle        (字符串字面量高亮: '...' 与 "...")
        ├── numberStyle        (数字字面量高亮: 0-9 整数与浮点数)
        ├── commentStyle       (单行与多行注释高亮: // 与 /* ... */)
        ├── punctuationStyle   (标点符号高亮: {}, (), [], ;, ,)
        └── constantStyle      (编译期常量与枚举值高亮)

1. 继承式语法样式传递拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~
* ``CodeStyle`` 继承自 ``InheritedWidget``，将 8 大词法标记的 ``TextStyle`` 封装为不可变样式集合；
* 子树中的代码展示组件只需调用 ``CodeStyle.of(context)``，即可在 $O(1)$ 时间内获取当前主题（深色/浅色模式）下的代码语法着色板；
* ``updateShouldNotify`` 精确比对 8 种样式的指针引用，确保仅在主题真实切换时才触发重绘。

----------------------------------------------------------------------------------------

第二幕：正则表达式分词流与 `TextSpan` 扁平化富文本构建
------------------------------------------------------

在 UI 树中展示数千行代码时，最严重的架构反模式是为每一个代码单词创建一个独立的 ``Text`` 组件（会导致内存中生成数万个 Element 节点与垃圾回收停顿）。

系统采用了**单一 `SelectableText.rich` + 扁平化 `TextSpan` 树** 的极速光栅化方案：

.. code-block:: text

   [原始 Dart 代码字符串 (code_segments.dart)]
                        │
                        ▼
   1. 正则词法扫描器 (Lexical Regex Scanner)
      • 捕获组 1: 字符串字面量 r"('|\")(.*?)\1"
      • 捕获组 2: 行注释与块注释 r"//.*|/\*[\s\S]*?\*/"
      • 捕获组 3: 语言核心关键字 r"\b(abstract|class|const|extends|final|return|...)\b"
      • 捕获组 4: 类名与构造器   r"\b[A-Z][a-zA-Z0-9_]*\b"
      • 捕获组 5: 数值字面量     r"\b\d+(\.\d+)?\b"
                        │
                        ▼
   2. 顺序切分并转换为 TextSpan 叶子节点列表
      List<InlineSpan> spans = [
        TextSpan(text: 'class ', style: codeStyle.keywordStyle),
        TextSpan(text: 'MyButton ', style: codeStyle.classStyle),
        TextSpan(text: 'extends ', style: codeStyle.keywordStyle),
        TextSpan(text: 'StatelessWidget ', style: codeStyle.classStyle),
        ...
      ]
                        │
                        ▼
   3. 挂载单一 SelectableText.rich(TextSpan(children: spans))
      • 整个代码块在渲染树中仅占 1 个 RenderParagraph 节点！
      • 支持跨行鼠标连续选中文本、高亮复制与原生右键菜单

----------------------------------------------------------------------------------------

第三幕：`DemoPage` 双视图联动与原生剪贴板管道
----------------------------------------------

在 ``lib/pages/demo.dart`` 中，系统为每个组件详情页构建了“运行实例（Demo）”与“源码查看（Code）”的双视图状态机：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ DemoPage 顶级详情脚手架 (多视图状态机)                                    │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. 顶部操作栏 (Header Actions):                                           │
   │    • 视图切换按钮: 在【运行演示】与【查看源码】之间平滑切换               │
   │    • 复制代码按钮: 一键将当前源码注入操作系统物理剪贴板                   │
   │    • 全屏演示按钮: 独立弹出全屏沉浸式体验                                 │
   │                                                                          │
   │ 2. 状态保持与图层拓扑:                                                   │
   │    • 演示层 (Demo View): 承载真实可交互组件实例，保持内部 State 不被销毁  │
   │    • 源码层 (Code View): 承载 CodeViewer，支持双向滚动与字号自适应缩放    │
   └──────────────────────────────────────────────────────────────────────────┘

1. 跨平台剪贴板物理管道 (`Clipboard.setData`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当用户点击“复制代码”按钮时，数据流转直接穿透至原生操作系统层：

.. code-block:: text

   [用户点击复制代码按钮]
             │
             ▼
   1. 提取当前演示案例的原始代码字符串: rawCodeString
             │
             ▼
   2. 调用 Clipboard.setData(ClipboardData(text: rawCodeString))
             │
             ▼
   3. ServicesBinding.instance.defaultBinaryMessenger 发送平台消息
      • Channel: "flutter/platform"
      • Method:  "Clipboard.setData"
             │
             ▼ 跨越 C++ Embedder 二进制管道写入宿主剪贴板
   4. 操作系统原生写入:
      • macOS:   [NSPasteboard generalPasteboard] setString
      • Android: ClipboardManager.setPrimaryClip
      • Web:     navigator.clipboard.writeText(text)
             │
             ▼
   5. 回调主线程弹出 SnackBar 浮动提示: "Code copied to clipboard"

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**【模块 04：声明式路由与 CodeViewer 语法引擎】全部 2 节已全量圆满完工并落盘**！
  同时，**【第一部】Gallery 企业级全平台商业工程实战篇（模块 01 ~ 04，共 14 篇长篇源码专著）已全部 100% 完工落盘**！
* **给下一个周期的施工建议**：
  下一个周期将正式跨入 **【第二部：向下穿透——Flutter 3.32 SDK 框架层核心机制】**！
  我们将正式推进 **模块 05：响应式核心——三棵树拓扑与 Diff 算法** 的第二节：
  ``05_framework_three_trees/02_element_lifecycle_and_mount.rst``。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/widgets/framework.dart`` 源码，系统剖析 ``Element`` 四态生命周期状态机（``initial`` $	o$ ``active`` $	o$ ``inactive`` $	o$ ``defunct``）、深度优先挂载（``mount``）、``BuildContext`` 的物理本质（即 Element 自身）、以及未激活元素回收桶（``_InactiveElements``）在帧末尾的批量卸载与垃圾回收机制。
