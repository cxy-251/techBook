第174章：kdump 与 vmcore 收集
============================

核心知识点
----------

Kdump 是预先建立的崩溃取证路径
   运行内核失去可信度后，系统依靠提前预留的 Crash Kernel 启动最小收集环境，而不是继续依赖已经崩溃的生产内核。

``crashkernel=`` 预留独立物理内存
   该区域容纳 Dump-capture Kernel、Initramfs 和收集工具，普通页分配器不能使用。命令行存在不等于预留成功，应结合 ``/proc/iomem`` 验证。

Crash Kernel 必须在故障前加载
   Kexec Crash Image 预加载完成后，Panic 路径才可能切换到第二内核。``kexec_crash_loaded`` 等状态只证明已加载，不证明端到端收集可用。

``/proc/vmcore`` 表示第一内核内存
   第二内核通过 ELF Core 风格接口暴露崩溃内核的内存视图。它不是第二内核自身的普通内存快照。

收集链任一环节都可能失败
   预留区、Kexec、CPU 停止、第二内核启动、驱动初始化、存储或网络、空间、脚本和重启策略共同决定是否得到有效 Vmcore。

Capture Kernel 应最小化依赖
   其目标是读取并保存现场，不是恢复业务。CPU、驱动、存储、网络和用户态组件越少，崩溃后再次失败的概率越低。

设备状态在 Panic 后不可信
   DMA、IRQ、Firmware 和 Queue 可能仍处于异常状态。第二内核重新初始化设备并不保证成功，本地存储若正是故障源尤其危险。

Vmcore 完整度受过滤策略影响
   Makdumpfile 可压缩并过滤 Free Page、User Page 或其它区域。文件变小的代价是后续对象可能不可读，分析时必须记录 Dump Level。

Pstore/Ramoops 是短日志冗余
   Pstore 可在重启后保存少量 Oops、Panic、Console 或 Ftrace 记录。它不能替代完整 Vmcore，但在 Kdump 失败时可能保留最后证据。

符号配对面向崩溃的第一内核
   后续分析所需 ``vmlinux``、Module Debuginfo、Build ID、Config 和 Source 必须匹配生产内核，而不是 Dump-capture Kernel。

Vmcore 是高敏感数据
   内存镜像可能包含密钥、凭证、用户数据和内核地址，应控制传输、存储、访问、保留和销毁，并保存 Hash 与完整性元数据。

Kdump 必须通过真实故障演练验收
   服务 Active、参数存在或 Crash Image Loaded 都不足以证明有效。只有受控触发后成功保存并打开匹配 Vmcore，收集链才算闭合。

关键路径
--------

正常启动准备：

::

   Bootloader 传入 crashkernel
   → 第一内核预留物理内存
   → 用户态构建 Capture Initramfs
   → kexec 预加载 Crash Kernel
   → 验证预留区、Loaded 状态和目标容量

崩溃收集：

::

   第一内核 Panic
   → 停止或收束其它 CPU
   → crash_kexec 切换到预留内核
   → Capture Kernel 初始化最小设备路径
   → /proc/vmcore 暴露第一内核内存
   → 压缩/过滤并保存本地或远端
   → 校验文件并重启

证据冗余：

::

   Printk / Serial / BMC 保存即时日志
   + Pstore/Ramoops 保存短持久记录
   + Kdump 保存 Vmcore
   → 按 Boot ID、Build ID 和时间建立同一故障集合

概念辨析
--------

* Panic 与 Vmcore：Panic 只是进入崩溃路径，后续任一步失败都可能没有 Dump。
* Crash Kernel 与生产内核：前者负责收集；Vmcore 和分析符号描述的是后者。
* Pstore 与 Kdump：Pstore 保存容量有限的短记录；Kdump 保存可重建对象状态的内存镜像。
* 完整 Vmcore 与过滤 Vmcore：过滤降低体积，也可能删除分析所需页面。
* Crash Image Loaded 与端到端可用：Loaded 只验证准备阶段，真实故障演练才验证完整链路。

本章结论
--------

Kdump 的可靠性来自崩溃前就隔离好内存、第二内核、保存目标和符号资产；事后能否分析，主要取决于这条最小取证路径是否预先验证。