第015章：Memory, Flash Storage, and Mobile IO Characteristics
============================================================

核心知识点
----------

* Mobile DRAM 同时承载 App heap、native memory、system service、page cache、graphics buffer、camera buffer、video frame 和 kernel/DMA buffer；语言层对象只覆盖整机内存占用的一部分。
* 内存问题应先区分 anonymous memory、file-backed memory 与 kernel/DMA buffer。三者回收成本、可见性和生命周期不同。
* 内存压力上升时，系统会先回收 page cache、压缩或换出匿名页，再降低后台进程优先级或终止缓存进程。Android 的 LMKD、Apple 可观察到的 Jetsam 都体现系统级进程回收思想。
* DRAM capacity 回答“能放多少”，memory bandwidth 回答“每秒能搬多少”。相机、GPU、NPU、video codec 和 display 并发时，即使容量足够也可能因带宽不足产生掉帧。
* Flash storage 由 NAND、controller、firmware、block layer、filesystem 和加密路径组成。UFS/NVMe 提供高队列能力，但真实延迟仍受随机写、garbage collection、flush、温度和固件策略影响。
* 持久化写入要区分“数据已进入 page cache”“文件系统事务已提交”“控制器确认落盘”等层次。``fsync``/flush 提高耐久性，也会把底层延迟暴露到调用路径。
* App 启动性能高度依赖 I/O latency 与 cache 命中。动态库、代码页、资源、数据库、配置和模型文件都会进入冷启动读路径。
* Page cache 能减少重复存储访问；compression/swap/zram 用 CPU 和存储/压缩开销换取更大的可用内存窗口；这些机制不能消除工作集本身过大的问题。
* 共享 buffer、DMA-BUF/GraphicBuffer、IOSurface 等机制的目标是减少 CPU copy，让 camera、GPU、codec、display 等消费者共享同一数据对象；同步和生命周期管理仍不可省略。
* 文件加密、key management、Data Protection/keystore 等安全机制把持久化 I/O 与用户解锁状态、设备密钥和 App 身份绑定。存储性能与数据保护不是两条完全独立的路径。

关键路径
--------

照片保存：

::

   capture buffer
   → image encode
   → file write / database transaction
   → page cache / filesystem metadata
   → block layer
   → UFS / NVMe controller
   → NAND persistence
   → media index / thumbnail update

内存压力：

::

   working set grows
   → reclaim clean file cache
   → compress / swap eligible pages
   → rank processes by importance
   → reclaim cached/background process
   → relaunch or restore when user returns

启动 I/O：

::

   process launch
   → map executable and libraries
   → page faults load code / resources
   → open config and database
   → query system services
   → first frame becomes ready

概念辨析
--------

* **Memory capacity 与 bandwidth**：前者决定能否容纳工作集，后者决定多个硬件单元能否及时搬运数据。
* **RAM 空闲与系统健康**：page cache 占用并非浪费；现代 OS 会主动利用空闲 DRAM 缓存可重读数据。
* **写入返回与真正持久化**：write 成功可能只表示数据进入缓存，断电级耐久性需要更严格的同步语义。
* **Swap/Compression 与扩容**：它们延缓内存压力，但会增加 CPU、I/O 或延迟成本，不能等价成物理 DRAM。
* **App heap 与整机内存**：图形、相机、native 与 DMA buffer 可能位于语言 GC 统计之外，却仍消耗系统 DRAM。

本章结论
--------

移动内存与 I/O 问题必须分成容量、带宽、延迟、持久化和保护五类来分析。看到启动慢、保存卡顿、后台被杀或预览掉帧时，应沿 DRAM 工作集、共享 buffer、page cache、flash queue、同步点和加密边界逐层定位，而不是笼统归结为“内存不够”或“存储慢”。