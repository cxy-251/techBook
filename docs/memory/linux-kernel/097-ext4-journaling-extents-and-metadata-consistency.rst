第097章：ext4 日志、Extent 与元数据一致性
=========================================

核心知识点
----------

Ext4 以就地更新为基础
   Ext4 延续传统 inode、目录项和块分配模型，普通数据与元数据最终写回既定磁盘位置。它不是通用 Copy-on-Write 文件系统。

Extent 压缩块映射
   Extent 用逻辑起点、物理起点和连续长度描述一段映射，大文件不必为每个块保存独立指针。映射复杂时通过 extent tree 扩展。

Block group 是空间管理域
   块位图、inode 位图、inode table 和数据块按 group 组织。分配器利用 group 局部性改善 inode、目录与文件数据布局。

Extent 与 block group 职责不同
   Extent 描述某个文件逻辑范围映射到哪里；block group 描述文件系统在哪些局部区域管理空闲块与 inode。

延迟分配推迟物理块选择
   Buffered write 先在 Page Cache 中形成脏范围，真实块分配常推迟到 writeback 或同步阶段，使分配器能看到更完整的写入范围。

``write()`` 成功不保证空间兑现
   Delayed allocation 尚未建立最终物理 extent，后续 writeback 仍可能因空间、配额、日志或设备错误失败。

JBD2 保护元数据事务
   Ext4 决定要修改哪些 inode、bitmap、extent 和目录块；JBD2 负责事务组织、日志提交和崩溃后的 replay。

Journal handle 表达事务预算
   元数据修改必须先取得 handle 和足够 credits，再按协议取得 buffer 写权限并标记日志脏状态。预算不足需要扩展、重启或拆分事务。

日志采用先写日志再回写原位
   事务的日志记录和 commit record 按顺序达到稳定状态后，元数据才可在后续 checkpoint 写回 home location。

恢复只重放完整事务
   崩溃后 JBD2 识别具有完整提交记录的事务并重放，使 ext4 元数据结构回到可解释状态；未完成事务不会作为完整更新应用。

数据模式决定数据与元数据顺序
   ``data=ordered``、``data=writeback`` 和 ``data=journal`` 对普通数据是否进入日志、何时相对元数据写出具有不同约束。

Ordered 不是同步写
   Ordered mode 主要防止已提交元数据暴露未初始化旧块内容，不表示每次 ``write()`` 返回时数据已经持久化。

``fsync()`` 建立应用可依赖的边界
   文件数据、必要元数据、日志和设备 flush 必须共同推进。Rename 等命名更新还可能要求同步父目录，才能形成崩溃后可恢复的应用协议。

日志恢复与业务事务不同
   Ext4 能恢复文件系统结构，不会自动保证跨多个文件的应用状态原子一致。业务事务仍需应用自己的提交和恢复设计。

关键路径
--------

延迟分配写入：

::

   用户写入文件逻辑范围
   → Page Cache 接收数据并标记 dirty
   → inode 记录 delayed allocation 范围
   → writeback 或 fsync 触发真实块分配
   → 在 block group 中选择连续空间
   → 建立或扩展 extent
   → 元数据变化加入 JBD2 事务
   → 数据、日志和 home metadata 按模式推进

JBD2 元数据事务：

::

   Ext4 估算元数据修改量
   → 取得 journal handle 与 credits
   → 获取目标 metadata buffer 写权限
   → 修改 inode、bitmap、extent 或目录块
   → 标记 journal dirty metadata
   → 提交日志描述与 commit record
   → 事务成为可恢复状态
   → checkpoint 后续更新原始元数据位置

崩溃后恢复：

::

   挂载发现日志未清理
   → 扫描日志序列与校验信息
   → 找到完整提交事务
   → 重放受保护的元数据更新
   → 忽略不完整事务
   → 继续 orphan 等延迟清理
   → 建立结构一致的文件系统视图

应用原子替换：

::

   写入临时文件
   → fsync / fdatasync 临时文件
   → rename 切换目录项
   → 必要时 fsync 父目录
   → 检查每一步返回值
   → 依赖日志与设备 flush 顺序
   → 崩溃后验证应用所需版本

概念辨析
--------

* Extent 与 block group：Extent 是文件映射；block group 是局部空间和 inode 管理域。
* Delayed allocation 与空间预留：延迟分配改善布局，不等于写入时已经获得最终磁盘块。
* Journal 与文件数据：JBD2 主要保护元数据事务；普通数据是否进入日志由 data mode 决定。
* Ordered mode 与持久化：Ordered 约束写出顺序；``fsync`` 才建立更强的调用者同步边界。
* Rename 原子性与掉电恢复：Rename 在运行时切换名字关系；崩溃后结果还依赖文件及目录的同步顺序。
* 文件系统一致性与应用一致性：日志保证 ext4 结构可恢复；业务跨文件关系需要应用级协议。

本章结论
--------

Ext4 用 extent 与延迟分配优化空间布局，用 JBD2 保护元数据事务；数据真正持久化仍由 data mode、同步调用和设备顺序共同决定。
