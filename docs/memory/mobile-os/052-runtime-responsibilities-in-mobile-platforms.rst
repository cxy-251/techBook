第052章：Runtime Responsibilities in Mobile Platforms
====================================================

核心知识点
----------

* Runtime 位于 App code 与 Framework / native library 之间，负责让源码产物进入真实执行状态。
* Android 侧核心对象是 DEX、ART、ClassLoader、JIT/AOT、GC、JNI；Apple 侧核心对象是 Mach-O、dyld、Objective-C runtime、Swift runtime、ARC。
* Runtime 直接承担代码装载、方法解析、对象模型、内存管理、动态派发、native 互操作和 framework callback 承接。
* Runtime 不拥有相机、定位、文件等系统资源；这些能力进入 Framework 后仍由 system service / daemon 与 kernel 执行策略和资源控制。
* 启动慢、首帧卡顿、滚动抖动、内存上涨、native crash 都可能先落在 runtime 边界，而不是直接落到系统服务或驱动。
* Runtime 的成本最终表现为 CPU 时间、内存页、对象堆、代码页、动态库映射和主线程执行时间。

关键路径
--------

``App Code → Runtime → Framework API → IPC → System Service / Daemon → Kernel / Driver → Hardware``

Runtime 内部常见执行路径：

``代码产物 → 类 / image 装载 → 符号 / 方法解析 → 可执行入口 → 对象分配 → GC / ARC → 回调与事件循环``

排查顺序：

#. 先确认问题是否发生在应用进程内的 class loading、symbol binding、object allocation 或 native bridge。
#. 再确认是否已经跨入 Framework API 和 IPC。
#. 若服务端已执行，再继续看权限、资源状态、kernel I/O 或硬件等待。
#. 用 crash stack、heap、launch trace、loader event 和主线程时间片确定边界。

概念辨析
--------

* **Runtime 与 Framework**：Runtime 负责代码和对象怎样执行；Framework 负责向 App 提供平台能力 API。
* **Runtime 与 Kernel**：Runtime 管理语言级执行与对象；Kernel 管理线程、页表、文件、设备和进程隔离。
* **Managed code 与 Native code**：Managed code 受 ART / 语言 runtime 管理；native code 进入 ABI、指针、动态链接和系统库边界。
* **GC 与 ARC**：GC 根据可达性回收对象；ARC 根据引用计数释放对象。二者都服务对象生命周期，但停顿和内存峰值来源不同。
* **代码已安装 与 代码已可执行**：安装产物存在不等于方法已完成加载、解析、绑定和必要初始化。

本章结论
--------

Runtime 是 App 源码变成真实进程行为的执行层。阅读移动系统时，应先把 class / image loading、符号解析、对象分配、GC / ARC、native bridge 与 framework callback 放入 runtime，再继续向 system service、kernel 和 hardware 追踪；这样才能把应用侧执行成本与平台资源控制正确分层。