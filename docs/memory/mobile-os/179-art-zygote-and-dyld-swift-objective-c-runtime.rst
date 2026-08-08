第179章：ART Zygote and dyld Swift Objective-C Runtime
======================================================

核心知识点
----------

* Android 与 Apple 都要解决“第三方应用如何快速进入受控进程并连接系统 framework”的问题，差异主要在代码表示、进程创建、编译优化和对象生命周期管理。
* Android 使用 DEX + ART：class loading、verification、method resolution、interpreter、JIT、AOT、profile-guided compilation 和 GC 共同决定执行形态。
* Zygote 预加载常用类和资源，再通过 fork 创建 App 进程；copy-on-write 让多个进程共享大量只读页，同时进程私有写入会逐步打破共享。
* Baseline Profile / runtime profile 能让启动和高频路径更早获得 AOT 优化；缺少 profile、类加载过多、JIT 热身或 GC 都可能进入冷启动成本。
* Apple 使用 Mach-O + dyld：主 executable 与 framework / dylib 通过 image mapping、fixup、symbol binding 和 initializer 接入进程；dyld shared cache 降低系统 framework 的重复装载成本。
* Objective-C runtime 管理 class、selector、message dispatch、method cache 与动态对象模型；Swift runtime 管理类型 metadata、protocol witness table、generics 和 ABI 语义。
* Apple 主要通过 ARC 管理对象引用计数；Android 主要由 GC 回收托管堆。两者都可能产生内存峰值和暂停 / CPU 成本，只是成本形态不同。
* 运行时性能问题必须区分进程创建、代码装载、编译、framework 初始化、对象生命周期和 App 自身主线程工作。

关键路径
--------

::

   Android cold start:
   Launcher → System Service → Zygote fork
       → App specialization → ART / DEX load
       → JIT / AOT compiled code → ActivityThread / Application
       → First Activity → First Frame

   Apple cold start:
   SpringBoard / System → App Process
       → Mach-O mapping → dyld / shared cache
       → ObjC + Swift runtime setup → Framework entry
       → UIApplication / SwiftUI lifecycle → First Frame

启动慢时先分 ``process creation``、``runtime/loading``、``framework initialization``、``app main-thread work`` 四段，而不是只看语言。

概念辨析
--------

* ``DEX`` 是 Android 的执行输入格式，``ART`` 是执行与内存管理运行时；两者不是同一层。
* ``Zygote`` 解决进程创建和预加载共享，``JIT/AOT`` 解决方法执行优化。
* ``Mach-O`` 是二进制格式，``dyld`` 是动态链接器，``Swift/ObjC runtime`` 负责语言级运行时语义。
* ``GC`` 与 ``ARC`` 都不代表“自动就没有内存问题”：GC 有扫描 / 暂停和堆压力，ARC 有 retain/release 开销、循环引用和 autorelease 峰值。

本章结论
--------

Android 以 Zygote + ART + profile-driven JIT/AOT 在跨设备兼容与运行优化之间取舍；Apple 以 Mach-O + dyld + shared cache + Swift/Objective-C runtime 把原生二进制快速接入系统框架。启动性能的本质是进程、装载、编译 / 链接、对象管理和首帧工作量的总和。