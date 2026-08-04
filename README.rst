techBook
========

``techBook`` 现在同时保存两种学习内容：

* 原有的 Linux Kernel 固定源码时间线与回溯审查正文；
* 与 AIBook 章节一一对应、可以直接记忆的必背课本。

两个内容体系位于不同目录，互不覆盖。原有正文保持不变，新内容直接在 ``main`` 的
``docs/memory/`` 中继续增加。

内容入口
--------

* `必背课本总目录 <docs/memory/index.rst>`_；
* `Linux Kernel 必背课本 <docs/memory/linux-kernel/index.rst>`_；
* `原有学习路径 <docs/tracks/index.rst>`_；
* `原有 Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_。

必背课本
--------

必背课本以 AIBook 完整章节为来源，删除铺垫、重复、长案例和互动步骤，只保留稳定、确定、
可以直接记忆的知识点、执行路径、概念区别和一句话结论。

* `必背课本内容合同 <project/MEMORY_CONTENT_CONTRACT.rst>`_；
* `第001章：Linux 内核资源管理模型 <docs/memory/linux-kernel/001-linux-kernel-resource-management-model.rst>`_；
* `第002章：为什么 Linux 内核源码难读 <docs/memory/linux-kernel/002-why-linux-kernel-source-is-difficult.rst>`_。

Linux Kernel 源码时间线当前维护状态
----------------------------------

历史正文已经存在第001—193章；现在暂停继续生成，从第001章开始按固定 QEMU、SeaBIOS、
GRUB 与 Linux 提交顺序回溯审查。已验证游标和下一批只以项目状态与审查账本为准，
避免 README 复制动态进度后失效。

* `稳定生产与回溯审查合同 <project/LINUX_KERNEL_CONTRACT.rst>`_
* `当前接续状态 <project/STATE.rst>`_
* `回溯审查账本 <project/audits/linux-kernel/index.rst>`_

当前源码时间线正文
------------------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百九十一章：TIME_WAIT timer怎样撤销最后的四元组并释放TW？ <docs/tracks/linux-kernel/191-timewait-timer-kills-lightweight-socket.rst>`_
* `第一百九十二章：close(6)怎样撤销listener fd并退出TCP_LISTEN？ <docs/tracks/linux-kernel/192-close-listener-removes-fd-and-listen-hash.rst>`_
* `第一百九十三章：listener怎样释放bind端口与最后的sockfs对象？ <docs/tracks/linux-kernel/193-listener-final-teardown-completes-tcp-scenario.rst>`_

固定来源
--------

::

   x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

历史正文已存在
--------------

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097
   LK-EXEC-098..LK-EXEC-100
   LK-EXIT-101..LK-EXIT-103
   LK-OPEN-104..LK-OPEN-106
   LK-DELALLOC-107..LK-DELALLOC-109
   LK-UNLINK-110..LK-UNLINK-112
   LK-SLEEP-113..LK-SLEEP-115
   LK-SIGNAL-116..LK-SIGNAL-118
   LK-PIPE-119..LK-PIPE-121
   LK-PIPECLOSE-122..LK-PIPECLOSE-124
   LK-FUTEX-125..LK-FUTEX-127
   LK-EVENTFD-128..LK-EVENTFD-130
   LK-EVENTFDCLOSE-131..LK-EVENTFDCLOSE-133
   LK-EPOLL-134..LK-EPOLL-136
   LK-EPOLLCLOSE-137..LK-EPOLLCLOSE-139
   LK-SIGNALFD-140..LK-SIGNALFD-142
   LK-SIGNALFDCLOSE-143..LK-SIGNALFDCLOSE-145
   LK-TIMERFD-146..LK-TIMERFD-148
   LK-TIMERFDCLOSE-149..LK-TIMERFDCLOSE-151
   LK-PIDFD-152..LK-PIDFD-154
   LK-PIDFDCLOSE-155..LK-PIDFDCLOSE-157
   LK-INOTIFY-158..LK-INOTIFY-160
   LK-INOTIFYCLOSE-161..LK-INOTIFYCLOSE-163
   LK-UNIXSOCK-164..LK-UNIXSOCK-166
   LK-UNIXSOCKCLOSE-167..LK-UNIXSOCKCLOSE-169
   LK-TCPLISTEN-170..LK-TCPLISTEN-172
   LK-TCPCONNECT-173..LK-TCPCONNECT-175
   LK-TCPHANDSHAKE-176..LK-TCPHANDSHAKE-178
   LK-TCPACCEPT-179..LK-TCPACCEPT-181
   LK-TCPDATA-182..LK-TCPDATA-184
   LK-TCPCLOSE-185..LK-TCPCLOSE-187
   LK-TCPPEERCLOSE-188..LK-TCPPEERCLOSE-190
   LK-TCPCLEANUP-191..LK-TCPCLEANUP-193

完成目标
--------

历史状态曾把43条 Linux Kernel 源码主线中的19条标记为完成。回溯审查期间，这个数字只作
历史库存参考；当前可信进度读取 ``project/STATE.rst``。审查到193后重新核定主线进度和
后续入口，章节总数仍不预设。

历史前向场景（尚未回溯验证）
----------------------------

::

   TIME_WAIT timer到期
   → tw_timer_handler进入inet_twsk_kill
   → TW依次离开ehash、bind/bind2并释放timer引用
   → tw_refcnt从3降到0，轻量TW释放
   → close(6)先从fdtable撤销listener fd
   → tcp_set_state按旧TCP_LISTEN状态把L移出lhash2
   → 显式bind让28080保留到tcp_v4_destroy_sock
   → inet_put_port撤销bind、bind2与inet_num
   → close(6)返回0，不等待SOCK_RCU_FREE grace period
   → RCU callback最终回收L存储

历史正文声称 TCP/IPv4 loopback 主线已经完成，并把 UDP socket 创建列为下一入口。该终点
保存在 ``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``，在001—193回溯审查闭合前不得
据此继续生产 UDP 章节。

开始工作
--------

新的对话或助手先读取 ``AGENTS.md``，再根据目标目录选择 Linux Kernel 源码时间线合同或必背课本
合同。不得把一条内容线的状态和格式规则带入另一条内容线。
