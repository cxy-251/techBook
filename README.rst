techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第九十五章：child 写只读 COW 地址时，x86 #PF 怎样进入 do_wp_page？ <docs/tracks/linux-kernel/95-x86-cow-write-fault-enters-do-wp-page.rst>`_
* `第九十六章：wp_page_copy() 怎样分配新 folio 并替换 child PTE？ <docs/tracks/linux-kernel/96-wp-page-copy-replaces-child-pte.rst>`_
* `第九十七章：page fault 返回后，CPU 怎样重试 store 并完成 COW 隔离？ <docs/tracks/linux-kernel/97-page-fault-return-retries-child-store.rst>`_

固定来源
--------

::

   x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

已经完成
--------

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097

最新场景
--------

child 向 fork 后的只读 private anonymous COW 地址执行 store：

::

   userspace store
   → x86 #PF
   → do_user_addr_fault
   → handle_mm_fault / do_wp_page
   → wp_page_copy
   → 分配并复制 4 KiB folio
   → child writable PTE
   → IRETQ 重试原 store

最终 child 映射并修改 new folio，parent仍映射 old folio；child ``min_flt`` 增加 1。下一运行期场景尚未选择，优先候选是 child ``execve()``。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和 manifest。
