第055章：Apple Runtime Mach-O, dyld, Swift Runtime, Objective-C Runtime
====================================================================

核心知识点
----------

* Apple App 的运行入口从 Mach-O 二进制开始，而不是从 Swift 或 Objective-C 源码开始。
* Mach-O 用 header、load command、segment、section、symbol 和 code signature 描述可执行映像、依赖、内存布局和信任信息。
* ``dyld`` 负责加载主程序依赖的 dynamic library / framework，并执行映射、rebase、bind 与初始化。
* dyld shared cache 通过预组织大量系统库降低重复解析与提升代码页共享效率。
* Objective-C runtime 负责 class、selector、message dispatch、category 与方法缓存等动态对象模型。
* Swift runtime 负责类型 metadata、泛型、protocol witness table、动态类型行为和 Swift ABI 相关执行支持。
* ARC 管理 Objective-C / Swift 引用计数对象；weak reference、autorelease pool、强引用环和 bridge 会影响对象生命周期与内存峰值。
* App 调用系统 Framework 后，runtime 仍只负责客户端对象和调用承接；真实系统能力可能继续通过 XPC / daemon 进入系统服务边界。

关键路径
--------

冷启动主链：

``App Bundle → Main Mach-O → Kernel 映射 → dyld → 依赖 Framework / dylib → rebase / bind → Runtime metadata 初始化 → App / Scene 入口``

一次 Framework 调用：

``Swift / Objective-C object → runtime dispatch → public Framework → XPC / system backend → callback → run loop / dispatch queue → App``

排查顺序：

#. 业务入口前失败先检查 Mach-O、依赖库、架构、签名与 dyld 错误。
#. 启动慢再看 embedded framework 数量、initializer、metadata 注册和 page fault。
#. 方法行为异常时区分 Objective-C message dispatch 与 Swift metadata / protocol dispatch。
#. 内存不下降时检查 ARC ownership、closure capture、autorelease 与 bridge 边界。

概念辨析
--------

* **Mach-O 与 Runtime**：Mach-O 是二进制文件格式；Swift / Objective-C runtime 是进程中的语言执行机制。
* **dyld 与 Framework**：dyld 负责把 framework 的二进制装载并绑定；framework 是代码、资源和公开 API 的分发边界。
* **Rebase 与 Bind**：rebase 修正 image 自身因加载地址变化产生的指针；bind 把跨 image 符号引用连接到真实定义。
* **Objective-C dispatch 与 Swift dispatch**：前者大量依赖 selector / message send；后者还涉及静态派发、vtable、protocol witness 和 metadata。
* **ARC 与 Sandbox**：ARC 只管理对象生命周期；sandbox、entitlement、TCC 决定资源访问资格。

本章结论
--------

Apple Runtime 应按 ``Mach-O → dyld → Framework loading → Objective-C / Swift runtime → ARC → App 回调`` 阅读。启动、符号、动态派发和内存问题分别落在不同边界；把二进制装载与语言 runtime 分开，是理解 Apple App 执行链的基础。