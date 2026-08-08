第171章：Mach-O, dyld, Swift Runtime, Objective-C Runtime, Framework Loading
============================================================================

核心知识点
----------

* Apple App 从进程创建到业务代码可执行，要经过 Mach-O 映射、dyld 动态链接、runtime 元数据准备、framework loading 与对象初始化。
* Mach-O 是 Apple 原生 executable/dylib/object image 格式；header、load command、segment/section、symbol/linkedit、code signature 共同描述如何装载和验证二进制。
* ``dyld`` 根据 Mach-O 依赖装载动态库，完成 image mapping、rebase/fixup、bind、initializer 等工作；这些工作大多发生在主业务逻辑之前。
* ``dyld shared cache`` 预组织大量系统 framework/dylib，减少系统库重复装载和内存占用；App 自带动态 framework 仍会产生额外 image、fixup 和 initializer 成本。
* Objective-C runtime 负责 class、selector、method cache、message dispatch、category 等动态对象模型；``objc_msgSend`` 的核心是按 receiver class 解析 selector 到实现。
* Swift runtime 负责 type metadata、protocol conformance / witness table、generics、dynamic cast 等运行时能力，并依赖稳定 ABI 与标准库支持。
* ARC 是编译器与 runtime 协同的引用计数模型；retain/release、weak、autorelease pool 和循环引用直接影响对象生命周期与内存峰值。
* Framework loading 只让 API 进入当前进程可调用状态；真正访问相机、定位等系统能力时，调用仍可能跨到 XPC / daemon。

关键路径
--------

* 冷启动进程内路径：``Mach-O main image → dyld loads dependencies → shared cache / app frameworks → ObjC & Swift metadata → initializers → UIApplicationMain / SwiftUI entry → App code``。
* 启动慢时先分段：image 数量与 mapping → fixup/bind → ``+load`` / static initializer → runtime metadata → App own initialization → first framework service request。
* 添加动态 framework 会修改 Mach-O load commands，并增加签名校验、映射、符号绑定和 metadata registration 工作。
* Objective-C 首次消息查找可能经历 class/method lookup，后续命中 method cache；Swift 泛型和协议调用可能依赖 metadata 与 witness table。
* 分析启动性能时，pre-main 时间与进入 ``main``/App 生命周期后的主线程时间必须分开。

概念辨析
--------

* ``Mach-O`` 是二进制格式；``dyld`` 是运行期 loader/linker，二者分别描述“文件是什么”和“文件如何接入进程”。
* ``Rebase/fixup`` 解决 image 内部地址修正；``Bind`` 解决外部符号引用，两者目标不同。
* ``dyld shared cache`` 优化系统库装载，不等于把第三方 framework 预编译进系统缓存。
* ``Objective-C runtime`` 与 ``Swift runtime`` 各自处理语言运行时语义，但同一 App 中可以桥接并共享底层 process、memory 与 framework。
* ``Framework loaded`` 不代表对应系统服务已经执行；真正的硬件/受控能力通常还要跨 IPC 和 policy boundary。

本章结论
--------

Apple Runtime Layer 应按“二进制装载 → 动态链接 → 语言 runtime → 对象生命周期 → framework 调用”读取。启动性能问题只有先区分 pre-main 的 dyld/runtime 成本与进入 App 代码后的初始化成本，才能判断应该减少动态 image、initializer、runtime 元数据工作，还是优化业务主线程与后续系统服务访问。