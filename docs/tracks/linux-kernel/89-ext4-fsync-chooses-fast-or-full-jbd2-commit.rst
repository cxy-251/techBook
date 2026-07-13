第八十九章：ext4 fsync 怎样选择 fast commit 或完整 JBD2 commit？
======================================================================

第八十八章结束时，file offset 0..4095 的 data WRITE 已经完成：target folio clean、uptodate、unlocked，``PG_writeback=0``，``file_write_and_wait_range()`` 返回 0。

``ext4_sync_file()`` 现在继续执行：

.. code-block:: c

   ext4_fsync_journal(inode, false, &needs_barrier);

这里的 ``false`` 来自 ``O_SYNC`` 对普通 fsync 语义的要求。本章追踪 ext4 怎样选择目标 transaction id，怎样判断 commit 本身是否会携带 data barrier，以及怎样在 fast commit、完整 JBD2 commit、已经提交三条路径之间汇合。

``i_sync_tid`` 与 ``i_datasync_tid`` 有什么区别
-----------------------------------------------

``ext4_fsync_journal()`` 首先取得：

.. code-block:: c

   tid_t commit_tid = datasync ? ei->i_datasync_tid
                               : ei->i_sync_tid;

当前 ``datasync=false``，所以选择：

.. code-block:: text

   commit_tid = EXT4_I(inode)->i_sync_tid

``i_datasync_tid`` 只追踪保证文件数据可正确访问所必需的 metadata；``i_sync_tid`` 还覆盖普通 fsync 要求的 inode metadata，例如本次 write path 可能更新的 mtime/ctime 与 inode state。

transaction id 不是磁盘 sector，也不是 AHCI tag。它标识 JBD2 中包含相关 metadata 更新的逻辑 transaction。

普通文件为什么可以尝试 fast commit
----------------------------------

fast commit 不完整支持目录和部分特殊 inode，所以代码先检查：

.. code-block:: c

   if (!S_ISREG(inode->i_mode))
       return ext4_force_commit(inode->i_sb);

固定对象是 regular file，因此继续进入 fast-commit-aware 路径。

这并不保证 fast commit 一定启用或一定成功；它只说明该 inode 类型没有在入口处强制 full commit。

``needs_barrier`` 在 commit 前怎样决定
-------------------------------------

ext4 检查：

.. code-block:: c

   if (journal->j_flags & JBD2_BARRIER &&
       !jbd2_trans_will_send_data_barrier(journal, commit_tid))
       *needs_barrier = true;

``JBD2_BARRIER`` 表示 filesystem 启用了 barrier 语义。``jbd2_trans_will_send_data_barrier()`` 检查目标 transaction 当前状态：

* transaction 仍在 running 时，可以设置 ``t_need_data_flush=1``，让后续 full commit 在 commit record 前建立 data ordering；
* transaction 已在 committing 时，只有尚未越过相应 flush state 才能复用该 commit 的 barrier；
* transaction 已经 committed，或 commit 已越过可附加 barrier 的阶段时，返回 false。

返回 false 时，ext4 把 ``needs_barrier`` 设为 true，准备在 journal commit 调用返回后额外执行 ``blkdev_issue_flush()``。

因此：

.. code-block:: text

   commit 会携带合适 barrier
   → needs_barrier = false

   commit 无法再替本次 fsync 携带 barrier
   → needs_barrier = true
   → ext4_sync_file 稍后单独 flush block device

若 filesystem 使用 ``nobarrier``，``JBD2_BARRIER`` 本身未设置，ext4不会要求额外 flush；这是 mount policy，不应伪装成设备已经执行 cache flush。

``ext4_fc_commit`` 是统一入口
----------------------------

入口最后调用：

.. code-block:: c

   ext4_fc_commit(journal, commit_tid);

函数名带 ``fc``，实际同时处理三类情况：

.. code-block:: text

   fast commit disabled
   → jbd2_complete_transaction(commit_tid)

   fast commit enabled and eligible
   → perform fast commit

   fast commit unavailable / ineligible / failed
   → fallback to full JBD2 commit

调用者无需预先知道最终选择哪一种。

fast commit 未启用时发生什么
----------------------------

若 mount option 没有启用 ``JOURNAL_FAST_COMMIT``，函数直接执行：

.. code-block:: c

   jbd2_complete_transaction(journal, commit_tid);

如果 ``commit_tid`` 已经小于或等于 ``j_commit_sequence``，目标 transaction 已完成，函数立即返回 0。

若它仍是 running transaction，``jbd2_complete_transaction()`` 调用 ``jbd2_log_start_commit()``：

.. code-block:: text

   journal->j_commit_request = commit_tid
   → wake kjournald2
   → writer task 等待 j_commit_sequence >= commit_tid

实际 full commit 由 journal thread 执行，不是 O_SYNC writer 在自己的调用栈里逐条写 journal blocks。

fast commit 怎样开始
--------------------

fast commit 启用时，``jbd2_fc_begin_commit()`` 尝试建立互斥的 fast-commit 状态：

* journal 已 aborted：返回错误；
* 尚未进行过任何 full commit：fast commit 不可用；
* ``commit_tid`` 已经满足：返回 ``-EALREADY``；
* 另一个 fast/full commit 正在进行：等待后返回 ``-EALREADY``；
* 成功：设置 ``JBD2_FAST_COMMIT_ONGOING``。

``-EALREADY`` 不等于 fsync 失败。调用者重新检查 transaction/sub-transaction 状态；若目标 durability 已由并发 commit 满足，可以直接返回成功。

哪些情况会回退 full commit
--------------------------

建立 fast-commit barrier 后，ext4 再检查 filesystem 是否被标记为 fast-commit ineligible。下列情况也会触发 fallback：

* snapshot inode/range 失败；
* fast-commit 区域空间不足；
* tracked extent 状态无法安全表达；
* memory allocation 失败；
* fast-commit buffer I/O 失败；
* 其他明确要求完整 transaction 的 metadata 操作。

fallback 调用：

.. code-block:: c

   jbd2_fc_end_commit_fallback(journal);

它清除 fast-commit active state，标记 full commit ongoing，并调用 ``jbd2_complete_transaction()`` 等待完整 transaction。

fast commit 成功路径先保证 data 顺序
-----------------------------------

``ext4_fc_perform_commit()`` 首先遍历 fast-commit queue 中的 inodes：

.. code-block:: text

   jbd2_submit_inode_data
   → jbd2_wait_inode_data

本次目标 range 在上一章已经完成 data writeback，因此对当前 inode通常无需重新发出 data bio；该步骤仍保证 fast-commit queue 中所有相关 data ranges 已满足顺序要求。

随后 fast commit：

#. 暂停新的 journal updates；
#. snapshot tracked inode 与 extent ranges；
#. 写入 dentry、inode、add-range/del-range TLV；
#. 写入带 transaction id 和 CRC 的 tail tag；
#. 等待 fast-commit buffers 完成。

fast commit tail 为什么带 ``PREFLUSH`` 和 ``FUA``
-------------------------------------------------

``ext4_fc_submit_bh(sb, true)`` 对 tail block执行：

.. code-block:: c

   if (test_opt(sb, BARRIER) && is_tail)
       write_flags |= REQ_FUA | REQ_PREFLUSH;

含义是：

* ``REQ_PREFLUSH``：tail 写入前，先把此前相关 write cache 内容推进到设备承诺的持久层；
* ``REQ_FUA``：tail block 本身按 force-unit-access 语义完成；
* tail 成功：fast-commit log 的结束记录与其之前的数据/metadata具有正确顺序。

fast commit tail 不是第八十七章的 file-data WRITE。它是 journal fast-commit area 中的 log record。

完整 JBD2 commit 做什么
----------------------

full commit 的主要阶段是：

.. code-block:: text

   T_RUNNING
   → T_LOCKED：阻止新 handle 并等待 outstanding updates
   → T_FLUSH：提交 transaction 关联的 file data
   → T_COMMIT：写 revoke、descriptor 和 metadata log blocks
   → T_COMMIT_DFLUSH：完成 data-device ordering
   → T_COMMIT_JFLUSH：写并等待 commit record
   → T_COMMIT_CALLBACK / T_FINISHED

journal thread 在 transaction lock 阶段等待现有 handles 结束，然后把 running transaction 移到 ``j_committing_transaction``。

它先调用 ``journal_submit_data_buffers()``，再写 journal metadata。对于同盘 journal，普通非 async commit 的 commit record在 ``JBD2_BARRIER`` 下带：

.. code-block:: text

   REQ_PREFLUSH | REQ_FUA

external journal 时，filesystem device与 journal device分离；JBD2在写 commit record 前根据 ``t_need_data_flush`` 对 filesystem device发出 flush。

async commit 模式可以更早提交 commit record，但在结束 transaction 前仍要等待 log blocks并执行 journal-device flush。

writer task 怎样等待 full commit
--------------------------------

``jbd2_log_wait_commit()`` 循环检查：

.. code-block:: c

   while (tid_gt(commit_tid, journal->j_commit_sequence))
       wait_event(journal->j_wait_done_commit, ...);

journal thread完成 transaction 后：

.. code-block:: text

   journal->j_commit_sequence = transaction->t_tid
   → wake_up(j_wait_done_commit)

writer 被唤醒后重新检查条件。若 journal aborted，wait 返回 ``-EIO``；固定成功路径返回 0。

fast 与 full commit 在哪里汇合
-----------------------------

成功分支最终都让 ``ext4_fc_commit()`` 返回 0：

.. code-block:: text

   already committed ───────────┐
   successful fast commit ──────┼→ ext4_fsync_journal returns 0
   successful full commit ──────┘

需要注意：fast commit 成功不要求立刻把整个 running transaction 变成 full committed transaction；它通过 durable fast-commit log满足当前 fsync 所需的 recovery 信息。

当前精确边界
------------

``ext4_fsync_journal()`` 已返回 0，``needs_barrier`` 已根据 barrier/transaction state确定。

当前状态：

* target data folio：clean、uptodate、``PG_writeback=0``；
* data WRITE：已经完成；
* target transaction durability：已由 already-committed、fast commit或 full commit路径满足；
* fast/full choice：取决于 mount option、eligibility 与运行时 transaction state；
* journal error：无；
* ``needs_barrier``：可能为 false，也可能为 true；
* standalone block-device flush：尚未由 ``ext4_sync_file()`` 执行；
* ``kiocb->ki_pos``：4096；
* local ``pos``：0；
* ``file->f_pos``：0；
* writer task：仍在 CPL 0 syscall process context；
* ``write()``：尚未返回。

下一入口回到 ``ext4_sync_file()`` 的 ``issue_flush`` 分支。若 ``needs_barrier`` 为 true，将调用 ``blkdev_issue_flush(inode->i_sb->s_bdev)``；否则直接进入 writeback-error 检查。

关键边界
--------

#. ``i_sync_tid`` 是 JBD2 transaction id，不是磁盘地址或 request tag。
#. regular file可以尝试 fast commit，不表示 fast commit 一定启用或成功。
#. fast commit失败会透明回退 full commit。
#. fast-commit tail 使用 ``PREFLUSH|FUA``，不是普通 file-data bio。
#. full commit由 journal thread执行，O_SYNC writer主要负责发起并等待。
#. fast commit满足当前 fsync，不要求整个 running transaction立即 full commit。
#. ``ext4_fsync_journal()`` 成功后仍可能需要 standalone device flush。

资料
----

* `Linux 7.2-rc1 fs/ext4/fsync.c：ext4_fsync_journal 与 ext4_sync_file <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/fsync.c>`_
* `Linux 7.2-rc1 fs/ext4/fast_commit.c：ext4_fc_commit、snapshot、tail 与 fallback <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/fast_commit.c>`_
* `Linux 7.2-rc1 fs/jbd2/journal.c：transaction request、wait 与 fast-commit coordination <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/jbd2/journal.c>`_
* `Linux 7.2-rc1 fs/jbd2/commit.c：完整 JBD2 transaction commit phases <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/jbd2/commit.c>`_
