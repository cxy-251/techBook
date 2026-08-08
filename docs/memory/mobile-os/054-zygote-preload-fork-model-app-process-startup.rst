第054章：Zygote Preload, Fork Model, App Process Startup
======================================================

核心知识点
----------

* Zygote 是 Android 应用进程创建的运行时模板：系统启动期先初始化 ART 和高频 Framework 状态，再等待进程创建请求。
* system_server 负责决定是否需要新进程、目标组件是谁以及应用身份参数；Zygote 负责执行 fork 和子进程专门化。
* Preload 预先加载常用 class、resource、shared library 和部分 runtime cache，使后续应用通过 copy-on-write 共享大量只读页。
* Fork 后的子进程必须写入 UID、GID、SELinux domain、挂载视图、runtime flags、进程名等身份，才能从 Zygote 子进程变成受管理 App process。
* 子进程随后进入 ``ActivityThread.main()``，建立主 Looper、连接 system_server，并接收 Application、Activity、Service、Provider 等生命周期事务。
* Zygote 优化的是公共 Framework 与 Runtime 基础成本，不会替 App 预加载业务数据库、网络 SDK、首页图片和私有业务对象。
* 预加载越多并非越好：无用常驻页、可变全局状态和 fork 前副作用都会降低共享收益或扩大系统成本。

关键路径
--------

Android 冷启动主链：

``Launcher → system_server → 进程记录 / 启动决策 → Zygote socket → fork → specialize → ActivityThread.main → bindApplication → 组件启动 → first frame``

Zygote 共享路径：

``系统启动 → ART 初始化 → preload classes/resources/libs → fork → 共享只读页 → 子进程写时复制``

排查顺序：

#. 先看 system_server 是否已经正确解析组件并发起进程创建。
#. 再看 Zygote socket、fork 和 specialize 是否成功。
#. 子进程出现后，确认是否进入 ActivityThread 并及时 attach。
#. attach 完成后，再分析 class/resource loading、Application 初始化和首帧主线程工作。
#. 内存问题要区分真正共享页、COW 私有页和 App 私有堆。

概念辨析
--------

* **Zygote 与 system_server**：Zygote 负责创建和专门化进程；system_server 负责进程与组件生命周期决策。
* **Fork 与 Specialize**：fork 复制执行上下文；specialize 把子进程写成目标应用的安全与运行时身份。
* **Preload 与 App 预初始化**：preload 面向多数应用共享的 Framework 状态；业务初始化属于具体 App 自身。
* **共享内存 与 Copy-on-Write**：fork 后页面可共享；任一子进程写入后才产生私有副本。
* **ActivityThread 与 Linux thread**：``ActivityThread`` 是应用 Framework 主控制对象，不只是一个普通线程名称。

本章结论
--------

Zygote 把 Android 的应用启动优化建立在“预加载共享 + fork + 身份专门化”之上。稳定的阅读顺序是 ``system_server 决策 → Zygote 创建进程 → ActivityThread 接管 → ART / App 初始化 → 首帧``；这样可以把进程创建问题、运行时加载问题和业务启动问题分开。