第114章：Device Mapper、LVM、RAID 与分层块设备
==============================================

核心知识点
----------

Device Mapper 是虚拟块设备框架
   DM 按虚拟 sector 查询映射表，再由 target 决定改写、克隆、缓存、加密、校验或转发请求。

映射表与 target 分工明确
   Table 决定某段地址由哪个 target 处理；target 的 ``map``、status 和管理回调定义该段的实际块语义。

不同 target 改变不同合同
   Linear 改地址，striped 分散负载，mirror/RAID 提供冗余，snapshot/thin 建立共享和延迟分配，cache 改变数据驻留层，crypt 改变数据表示。

LVM 是 DM 之上的策略层
   LVM 用 PV、VG、LV 和 segment 元数据组织容量，并把逻辑卷策略转换为运行时 Device Mapper table。

逻辑容量不等于实际可写容量
   Thin volume 可以显示很大逻辑空间，真正写入仍依赖 thin pool 的 data、metadata 和 reserve。任一域耗尽都可能中断服务。

Snapshot 依赖 COW 空间
   Snapshot 初始只建立共享映射；origin 首次覆盖某 chunk 时才复制旧数据。COW 空间耗尽会使快照失效。

RAID 会扩大请求形状
   Mirror 产生多副本写，parity RAID 产生数据、校验和可能的 read-modify-write。一个上层请求可展开为多个成员请求。

Queue limits 必须逐层合成
   最大 I/O、对齐、discard、flush、FUA、zoned 和 segment 能力必须由所有下层共同满足。中间层不能暴露无法兑现的能力。

完成与错误可能被吸收或转换
   某个 mirror member 失败时，上层 I/O 仍可能成功，但设备已进入 degraded。最终成功不能替代底层健康证据。

每增加一层都会增加放大
   分层设备会增加映射 CPU、元数据 I/O、clone/split、flush 扇出、错误传播和恢复状态，必须按层观测。

关键路径
--------

Device Mapper 提交：

::

   上层 bio 到达 dm 设备
   → 按 sector 查询 table
   → 找到 target
   → target map
   → 改写 / clone / split bio
   → 提交下层设备
   → 汇总子请求状态
   → 完成原 bio

LVM 到运行时设备：

::

   PV 提供 physical extents
   → VG 汇集空间
   → LV 分配 logical extents
   → LVM 生成 segment 元数据
   → 创建 dm table
   → 内核建立虚拟块设备
   → 文件系统使用该设备

Thin 写入：

::

   未映射逻辑块写入
   → 查询 thin metadata
   → 分配 pool data block
   → 更新逻辑到物理映射
   → 提交数据 I/O
   → 提交 metadata transaction
   → 完成上层请求

RAID 降级与重建：

::

   成员错误
   → 标记 degraded / faulty
   → 从剩余成员继续服务
   → 选择替代成员
   → resync / rebuild
   → 监控前台延迟与新错误
   → 恢复冗余状态

概念辨析
--------

Device Mapper 与 LVM
   DM 是内核数据路径框架；LVM 是用户空间容量、策略和元数据管理层。

映射表与 target
   Table 选择处理者；target 定义地址、数据、缓存、冗余和完成语义。

Thin 逻辑容量与 pool 容量
   Thin device 的逻辑大小可超配；实际可写性取决于 pool data、metadata 和保留空间。

Snapshot 与备份
   Snapshot 通常共享底层设备和故障域，只保存映射时间点，不等于独立备份。

RAID 降级与数据安全
   降级设备仍可能正常读写，但剩余故障容忍度下降，重建期间风险与尾延迟都会上升。

上层完成与成员完成
   RAID/cache target 按自身策略聚合子请求；单个成员完成不等于上层逻辑请求已经完成。

本章结论
--------

Device Mapper 让地址、缓存、加密、快照和冗余可组合，LVM 与 RAID 在其上提供策略与可靠性；每增加一层，也同时增加性能、持久化和故障分析复杂度。
