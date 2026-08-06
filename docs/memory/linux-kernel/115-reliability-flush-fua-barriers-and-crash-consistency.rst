第115章：可靠性、Flush、FUA、Barrier 与崩溃一致性
==================================================

核心知识点
----------

崩溃一致性讨论恢复边界
   目标不是让所有写都立即落盘，而是保证在任意断电、内核崩溃或 controller reset 点之后，系统仍能识别一个满足约束的已提交状态。

完成事件具有层级
   ``write()`` 返回、Page Cache writeback、文件系统事务提交、块 request 完成和非易失介质完成是不同承诺。

易失写缓存制造持久化缺口
   设备或控制器可在数据仍位于 volatile write cache 时报告命令完成，因此“写成功”和“掉电后仍存在”之间可能有 durability gap。

Flush 与 FUA 控制不同范围
   ``REQ_PREFLUSH`` 要求当前操作前的易失写入先稳定；``REQ_FUA`` 要求当前写在报告完成前达到非易失状态。

FUA 可以原生实现或模拟
   设备支持 FUA 时可直接附加协议标志；不支持时可能转换为 write 加 flush。实现方式不同，语义目标必须保持一致。

Barrier 是存储顺序约束
   现代 Linux 主要通过 flush、FUA、请求依赖和文件系统事务表达 barrier。它与 CPU memory barrier 完全不同。

文件系统日志需要先写后提交
   Journal descriptor、数据或元数据必须按文件系统合同稳定后，commit record 才能成为可恢复事务的确认点。

``fsync`` 收束文件系统与设备状态
   ``fsync(fd)`` 通常推进相关数据、必要元数据、日志事务、flush/FUA，并报告延迟 writeback 错误。

Rename 原子性不等于崩溃持久性
   ``rename`` 提供运行时命名切换原子性。可靠文件替换通常还需要同步临时文件和父目录。

所有虚拟层必须传播持久化语义
   DM、RAID、cache、loop、NBD 和虚拟化后端必须传播、拆分、汇总或等价模拟 flush/FUA；任一层吞掉语义都会破坏上层保证。

关键路径
--------

普通写的持久化缺口：

::

   应用 write
   → Page Cache dirty
   → 文件系统 writeback
   → 普通块写
   → 设备易失缓存接收
   → 命令可能先完成
   → 后续才进入非易失介质
   → 掉电可能丢失未刷新数据

Flush 与 FUA：

::

   文件系统建立顺序点
   → REQ_PREFLUSH 刷新此前写入
   → 提交当前关键写
   → REQ_FUA 要求当前写稳定
   → 下层设备确认
   → 完成逐层返回
   → 事务获得持久化边界

日志事务提交：

::

   收集 transaction 更新
   → 写日志描述与受保护内容
   → 建立所需数据/元数据顺序
   → flush 或 FUA
   → 写 commit record
   → commit 稳定
   → 后续 checkpoint 到 home location

可靠文件替换：

::

   创建临时文件
   → 写入完整内容
   → fsync 临时文件
   → rename 替换目标
   → fsync 父目录
   → 检查所有返回值
   → 崩溃后验证目标版本

分层 Flush：

::

   上层文件系统发出 flush/FUA
   → dm / RAID / cache 解释语义
   → 向所有必要成员或后端传播
   → 等待各下层稳定完成
   → 聚合状态
   → 向上层返回成功或错误

概念辨析
--------

Write 完成与持久化完成
   Write 完成表示接口接受了数据；持久化完成还要求文件系统和最终设备兑现同步语义。

Flush 与 FUA
   Flush 主要稳定此前写入；FUA 主要约束当前写的完成条件。

存储 Barrier 与内存 Barrier
   存储 barrier 约束 I/O 持久化顺序；内存 barrier 约束 CPU 与编译器的内存访问顺序。

Journal 一致性与应用事务
   文件系统日志保护文件系统结构；跨文件或业务状态仍需应用 WAL、版本号或数据库事务。

Rename 原子性与目录持久化
   Rename 保证运行时切换不可见中间状态；崩溃后目录项是否存在仍依赖目录同步和文件系统合同。

设备完成与应用 ``fsync`` 返回
   块层完成只是同步链的一环；应用仍需等待所有相关数据、元数据和下层 completion 收束。

本章结论
--------

崩溃一致性要求应用、文件系统、块层、虚拟设备和最终硬件对顺序与完成作出同一条可传递承诺；Flush 与 FUA 是把该承诺送达非易失介质的关键控制点。
