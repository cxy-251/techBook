Linux Kernel回溯审查前的前向检查点
===================================

本文件冻结开始回溯审查时，历史正文声称已经到达的第193章终点。它用于审查完成后对照，
不是已经验证的一手事实。回溯审查期间，新的对话不需要读取本文件。

冻结日期
--------

2026-07-15。

历史完成声明
------------

历史正文存在 ``LK-BOOT-001`` 至 ``LK-TCPCLEANUP-193``。当时把当前盘点的43条
Linux Kernel源码主线中的19条标记为完成，并把UDP/IPv4列为第20条候选主线。

历史终点声称
------------

::

   TIME_WAIT timer expiration
   → TIMER_SOFTIRQ invokes tw_timer_handler
   → inet_twsk_kill removes TW from ehash
   → inet_twsk_bind_unhash removes bind and bind2 identities
   → tw_refcnt 3→2→1→0
   → inet_twsk_free returns TW to twsk_slab

   close(6) listener teardown
   → file_close_fd clears fdtable.fd[6] and the open bit
   → fput_close_sync enters __fput synchronously
   → sock_close → inet_release → tcp_close(L,0)
   → tcp_set_state removes old TCP_LISTEN L from lhash2
   → explicit SOCK_BINDPORT_LOCK retains port 28080 until destroy
   → inet_csk_listen_stop finishes empty queues
   → tcp_v4_destroy_sock calls inet_put_port
   → bind, bind2 and inet_num are removed
   → SOCK_RCU_FREE delays L storage reclamation
   → close(6) returns 0 before the grace period

历史对象状态
------------

::

   system_state                  = SYSTEM_RUNNING
   current executor              = parent
   CPU/mode                      = CPU0, x86-64 CPL 3
   last syscall/result           = close(6)=0
   server/client/accepted fd     = 6/7/8 all closed
   listener L                    = TCP_CLOSE / orphan / unhashed
   L lhash2, bind, bind2         = removed
   L inet_num                    = 0
   C/H/R/TW                      = gone
   old ports 40000/28080         = no longer owned
   queues/timers/scenario skbs   = empty / none / none

历史下一候选
------------

::

   socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, IPPROTO_UDP)
   → reserve lowest available fd 6
   → allocate sockfs socket/inode and AF_INET protocol socket
   → inet_create selects udp_prot
   → publish a blocking close-on-exec datagram fd

上述入口、顺序、对象状态和19/43进度都必须在001—193回溯审查完成后重新确认，不能因
保存在本文件中就直接继承。
