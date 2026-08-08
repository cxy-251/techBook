JavaScript Source to Execution
==============================

核心知识点
----------

* JavaScript 源码只是执行入口；真实路径需要经过 ``source → parse → binding / scope → execution context → host capability → callback reentry``。
* 入口类型决定解析与运行语义：classic script、ES module、function call、event callback、dynamic ``import()``、``eval`` / ``Function`` 不是同一条路径。
* ES module 先形成 module record 与依赖图，再经历 fetch、parse、link、evaluate；静态 ``import`` 属于模块图，dynamic ``import()`` 在运行时返回 Promise。
* ``LexicalEnvironment`` 保存名字绑定及 outer environment 关系；``let`` / ``const``、函数、模块 binding 和闭包都依赖这一模型。闭包保留的是外层 binding 可达关系，不是“复制一份变量”。
* execution context 描述当前正在运行的 script / module / function 环境，包括 lexical environment、variable environment、``this`` 等运行信息；函数调用和 callback reentry 都会建立新的执行上下文。
* JavaScript engine 只负责 ECMAScript 语义；DOM、Fetch、timer、event、storage 等由浏览器 host 提供。代码写成 JS 调用，不代表能力属于 JS engine。
* 同一函数在生命周期中可能经历不同执行形态：初次解析、解释/基线执行、优化执行、deoptimization。源码顺序不能直接等价为最终机器执行成本。

关键路径
--------

页面模块启动：

``HTML <script type="module"> → module fetch → parse → dependency link → top-level evaluation → lexical bindings → DOM / Web API call``

事件重新进入 JavaScript：

``User input → browser event system → task → callback execution context → lexical lookup / closure state → DOM / Fetch / timer → return to host``

动态导入：

``callback → import(specifier) → host resolves URL → fetch / cache → parse / link / evaluate → Promise fulfilled → microtask continuation → module namespace``

排查“代码没运行”时依次确认：

``入口类型 → 资源是否取得 → parse 是否成功 → module link 是否成功 → binding 是否已初始化 → callback 是否被 host 调度 → host API 是否失败``

概念辨析
--------

* **源码 vs 执行**：源码是语言输入；执行还依赖 parser、scope、execution context、engine tier 和 host runtime。
* **Script vs Module**：module 默认 strict、拥有模块级 binding 和静态依赖图；classic script 更接近传统 global script 语义。
* **Lexical scope vs Call stack**：scope 决定名字从哪里解析；call stack 决定当前同步调用链。函数返回后 stack frame 消失，闭包引用的 lexical environment 仍可存活。
* **JavaScript engine vs Browser host**：Promise 语言语义属于 ECMAScript；``document``、``fetch``、``setTimeout``、事件和渲染属于 Web host。
* **dynamic import vs eval**：``import()`` 保留模块加载、安全与模块缓存边界；``eval`` / ``Function`` 把字符串重新变成代码执行边界，安全与优化成本更高。
* **代码已执行 vs 用户已看到结果**：DOM 状态可在 JS 中已经改变，但像素仍需浏览器取得渲染机会后才能显示。

本章结论
--------

分析 JavaScript 不能停在源码行号。稳定模型是 ``Source → Parse → Scope / Binding → Execution Context → Host Boundary → Callback Reentry``。先确定代码从哪个入口进入，再确定名字和状态由谁持有，最后追踪它如何跨浏览器 host 边界并重新进入 JavaScript；模块加载、闭包、异步回调和性能问题都能放回这条路径定位。
