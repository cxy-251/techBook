第162章：ART, Zygote, DEX, JIT, AOT, App Startup
================================================

核心知识点
----------

* Android 冷启动主链可压缩为 ``Launcher → system_server → Zygote fork → App specialization → ActivityThread.main → LoadedApk/ClassLoader → ART → Application → Activity → First Frame``。
* Zygote 预先启动 ART，并预加载常用类、资源和部分共享状态；App 进程通过 fork 获得这些共享页，降低每次冷启动的初始化和内存成本。
* fork 后还要 specialization：设置 UID/GID、SELinux context、进程名、data directory、runtime flags 等，使子进程成为目标 App。
* ``ActivityThread.main()`` 建立主线程 Looper，接收 system_server 的 bind/application/activity transaction，随后创建 ``LoadedApk``、ClassLoader、Application 和组件对象。
* DEX 是 ART 的托管代码输入。类加载成本包括定位、验证/准备、类初始化；大量 static initializer、反射、DI 容器和 SDK 初始化都会把成本前移到首帧之前。
* Method resolution 把 DEX 中的方法引用解析到真实调用目标；启动路径涉及的 class/method 越多，page fault、解析与初始化成本越明显。
* ART 支持 interpreted、JIT compiled、AOT compiled 等执行形态。Android 7.0 之后的主线是混合 JIT/AOT + profile-guided compilation。
* JIT 根据运行时热点编译方法，减少长期解释执行成本；AOT 在运行前编译，降低首次使用延迟但增加安装/存储成本。
* Baseline Profile、Cloud Profile、Startup Profile 分别从常用路径、分发侧历史和 DEX layout 等方向改善首次运行与启动关键路径。
* Zygote 共享解决的是进程创建和基础运行时成本；Profile 解决的是代码布局和编译状态；二者都不能替 App 消除主线程同步 I/O、过量初始化或复杂首屏布局。
* App Startup 至少要区分冷启动、暖启动、热启动。只有冷启动一定包含进程创建与完整 runtime 初始化。
* TTID 与 TTFD 是不同目标：前者关注初始画面，后者关注页面真正可交互/完整内容完成。启动优化应优先缩短首帧前关键路径。

关键路径
--------

::

   User launches App
   → ActivityTask / ActivityManager decides target
   → Zygote forks process
   → UID / SELinux / process specialization
   → ActivityThread.main + Main Looper
   → LoadedApk + ClassLoader
   → ART loads DEX / resolves methods
   → Application.onCreate
   → Activity lifecycle
   → View traversal / first frame

编译路径：

::

   DEX
   → interpreter for cold/uncompiled path
   → runtime profile collection
   → JIT hot methods
   → background / install-time profile-guided AOT
   → faster subsequent execution

概念辨析
--------

* **Zygote 与 ART**：Zygote 是预初始化并 fork App 的进程模型；ART 是执行 DEX、管理对象和编译代码的运行时。
* **Class Loading 与 Class Initialization**：加载/验证类不等于执行 ``<clinit>``；静态初始化常是启动隐藏成本。
* **JIT 与 AOT**：JIT 在运行时编译热点，AOT 在运行前编译；现代 Android 混合使用。
* **Baseline Profile 与 Startup Profile**：前者主要指导常用代码提前优化，后者还帮助启动相关类/方法的 DEX 布局。
* **Runtime 慢与 App 主线程慢**：编译/加载状态可能影响启动，但同步 I/O、SDK 初始化、复杂 UI 仍属于 App 自身首帧路径。

本章结论
--------

Android 启动应按 ``Process Creation → Runtime Ready → Code Loading/Compilation → Application Init → UI First Frame`` 拆解。启动慢时先确认是哪一段长，再判断是 Zygote/系统调度、ART/DEX/Profile，还是 App 主线程工作量。