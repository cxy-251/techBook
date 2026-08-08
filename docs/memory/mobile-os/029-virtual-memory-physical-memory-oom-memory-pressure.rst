第029章：Virtual Memory, Physical Memory, OOM, Memory Pressure
===============================================================

核心知识点
----------

* Virtual Memory 给每个进程独立地址空间；Physical Memory 是所有 App、System Service、Kernel、graphics/camera buffer 与 page cache 共同竞争的真实 DRAM。
* 页表把虚拟地址映射到物理页并携带读/写/执行权限。Page fault 可能触发匿名页分配、文件页读入、copy-on-write，或因非法访问终止当前进程。
* 虚拟地址空间大小不等于真实 DRAM 占用。共享库、文件映射、COW 页、匿名私有页和共享 buffer 的物理成本不同。
* Page Cache 缓存文件内容；干净文件页可低成本丢弃并重新读取，dirty page 需要写回，匿名页则通常依赖压缩、swap 或进程退出才能释放。
* Mobile DRAM 还被 kernel slab、network buffer、graphics buffer、camera frame、video buffer、AI tensor 等大量非语言运行时对象占用；只看 Java/Swift heap 会漏掉整机压力来源。
* Memory Pressure 是系统级状态。系统通常先 reclaim 可回收页，再使用 compression/swap 等手段，最后依据进程重要性释放整个进程。
* Android 通过进程生命周期、OOM 评分和 LMKD 等机制优先保留前台/关键服务并回收缓存进程；Apple 的 jetsam 类行为体现同样的“系统稳定优先于后台进程存活”原则。
* zram/compressed memory/swap 能用 CPU 和 I/O 成本换取更多有效内存，但会增加 page fault、解压、换入换出与延迟，不等于免费扩容。
* App 从后台返回是热恢复还是冷启动，首先取决于进程是否仍存在，其次取决于关键页面和缓存是否仍可快速恢复。

关键路径
--------

内存映射与访问：

::

   allocation / mmap
   → virtual address range
   → page table lookup
   → page fault if needed
   → physical page / page cache
   → access succeeds or protection fault

内存压力处理：

::

   DRAM pressure rises
   → reclaim clean cache
   → write back dirty pages
   → compress / swap eligible pages
   → evaluate process importance
   → LMKD / jetsam-like process termination
   → foreground survives, background may cold-start later

概念辨析
--------

* **Virtual Memory 与 Physical Memory**：前者是每个进程看到的地址模型，后者是整机有限 DRAM；虚拟空间宽裕不代表物理内存没有压力。
* **Heap 与 RSS/PSS**：语言层 heap 只是进程占用的一部分；native、mapped file、shared buffer 和 kernel/DMA 内存必须另行考虑。
* **Page Cache 与内存泄漏**：Page Cache 是可回收文件缓存，不应仅因数值变大就判定泄漏；持续增长的不可回收私有页更值得警惕。
* **OOM 与进程回收**：后台进程被系统结束并不等于应用发生传统分配失败；移动 OS 会主动牺牲低优先级进程保护整体系统。
* **Swap/Compression 与性能**：它们减少直接杀进程压力，但增加 CPU、I/O 和恢复延迟，不能替代控制工作集。

本章结论
--------

移动内存分析必须从“进程虚拟地址”继续追到“整机物理页”。用户看到的后台丢失、冷启动、相机黑屏或系统卡顿，往往来自匿名页、page cache、共享多媒体 buffer、压缩交换和生命周期策略共同作用。稳定的判断顺序是先确认进程是否被回收，再确认物理压力来源，最后分析 reclaim、compression/swap 与杀进程策略。