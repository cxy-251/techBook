第053章：Android Runtime DEX, ART, Class Loading, JIT, AOT, GC
=============================================================

核心知识点
----------

* Android 托管代码最终以 DEX 作为 ART 的主要执行输入；源码本身不会被运行时直接执行。
* DEX 保存类型、字段、方法、签名和字节码等结构，ClassLoader 决定目标类在哪个可见路径中被找到。
* ART 可以让同一方法处于解释执行、JIT 编译或 AOT 编译状态，并利用 profile 把真实热路径转成后续优化依据。
* Interpreter 提供立即可执行的兜底；JIT 在运行期间优化热点；AOT 把部分编译成本前移到安装、更新或后台优化阶段。
* Class loading 与 method resolution 负责把类名、方法索引和调用点绑定到真实运行时对象与代码入口。
* GC 管理 managed heap；分配速率、对象可达性、heap 增长和 GC 时机都会影响 UI 响应与内存峰值。
* ART 的设计是在启动速度、运行性能、存储占用、CPU、电池和更新成本之间做系统级平衡。

关键路径
--------

冷启动中的典型 ART 路径：

``进程入口 → ClassLoader → DEX 定位 → 类验证 / 方法解析 → AOT / Interpreter → JIT 热度收集 → Code Cache / Profile → 后台 dex2oat``

对象路径：

``方法执行 → 对象分配 → Managed Heap → GC 判定 → 并发 / 暂停回收 → 继续执行或内存压力``

排查顺序：

#. 确认目标类和方法是否真实进入最终 DEX，以及属于哪个 DEX / split。
#. 确认当前 ClassLoader 是否能看到它。
#. 再看关键方法是否已有可用 AOT 代码，是否大量落入解释执行或首次 JIT。
#. 卡顿时同时查看 allocation rate、GC event、主线程和 frame deadline。
#. OOM 或后台被杀时，区分 Java heap 问题与系统整体 memory pressure。

概念辨析
--------

* **DEX 与 JVM class**：DEX 是 Android 运行时使用的字节码容器，不等同于 JVM ``.class`` 文件。
* **Interpreter 与 JIT**：Interpreter 逐步执行字节码；JIT 在运行中把热点编译为机器码。
* **JIT 与 AOT**：JIT 用真实运行反馈换取动态优化；AOT 用提前编译换取更低运行时成本。
* **Class loading 与 Method resolution**：前者解决类从哪里来；后者解决调用点最终指向哪个字段或方法实现。
* **GC 与系统进程回收**：GC 回收应用堆中不可达对象；LMK / LMKD 类系统策略回收的是整个低优先级进程。

本章结论
--------

Android Runtime 的稳定阅读模型是 ``DEX → ClassLoader → ART 执行策略 → Managed Heap / GC``。启动和交互问题应先确认代码是否可见、如何执行，再分析 profile、JIT/AOT 与对象分配；只有把 ART 内部执行成本与系统级进程回收分开，才能正确解释 Android 的性能与内存行为。