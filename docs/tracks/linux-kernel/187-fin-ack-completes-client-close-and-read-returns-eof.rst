第一百八十七章：FIN ACK怎样完成client关闭并让read返回EOF？
=========================================================

上一章结束时，server已经消费client FIN，client对FIN的确认则停在C的socket backlog中：

::

   parent / CPU0 / close(7) kernel call stack

   client C
       state         = TCP_FIN_WAIT1
       shutdown      = SHUTDOWN_MASK
       snd_una       = C_ISN + 6
       snd_nxt       = C_ISN + 7
       write_seq     = C_ISN + 7
       retrans q     = [CFIN-original]
       sk_backlog    = [HACK]
       owned         = by parent

   server H
       state         = TCP_CLOSE_WAIT
       shutdown      includes RCV_SHUTDOWN
       SOCK_DONE     = true
       rcv_nxt       = C_ISN + 7
       copied_seq    = C_ISN + 6
       receive q     = [zero-payload FIN skb]

   HACK.seq          = S_ISN + 1
   HACK.ack_seq      = C_ISN + 7

fd 7已经从parent的fdtable撤销， ``close(7)`` 仍在同步 ``__fput`` 路径中。fd 8已经EOF-readable，parent尚未发起新的read。

本章先完成client close： ``tcp_send_fin`` 返回后，zero-timeout close不会睡眠；C成为orphan，parent通过 ``__release_sock`` 消费HACK，确认original FIN并进入 ``TCP_FIN_WAIT2``。默认60秒配置使完整C转换成一个 ``tw_state=TCP_TIME_WAIT``、 ``tw_substate=TCP_FIN_WAIT2`` 的轻量time-wait socket。随后 ``close(7)=0`` 返回用户态，parent执行 ``read(8,buf,1)``，消费H receive queue中的FIN标记并得到0。

本章固定条件
------------

* 只有CPU0 online，parent保持唯一执行者；
* ``SO_LINGER`` 未设置， ``tcp_close`` 的timeout为0；
* HACK合法且正好确认 ``C_ISN+7``；
* client没有未确认data，retransmission tree中只有CFIN original；
* ``tcp_fin_timeout`` 使用默认值 ``TCP_FIN_TIMEOUT=60*HZ``；
* ``TCP_TIMEWAIT_LEN=60*HZ``；
* time-wait socket分配成功，没有orphan memory pressure；
* fd 8为blocking socket，H receive queue中只有一个零payload FIN skb；
* 没有signal、RST、丢包、超时、内存失败或并发系统调用。

tcp_send_fin返回后为什么close不等待peer FIN
-----------------------------------------

上一章的嵌套NET_RX完成后，返回链结束CFIN发送：

::

   __dev_queue_xmit returns
   → ip_output returns
   → tcp_transmit_skb returns
   → __tcp_push_pending_frames returns
   → tcp_send_fin returns

``__tcp_close`` 接着调用：

::

   sk_stream_wait_close(C, timeout=0)

这个等待入口允许设置了linger的调用者等待状态变化。当前timeout从 ``inet_release`` 开始就是0，所以等待循环没有可供 ``schedule_timeout`` 使用的时间：

::

   schedule_timeout = skipped

parent保持 ``TASK_RUNNING``，C仍由parent持有用户锁。close会把余下TCP生命周期交给orphan与time-wait机制，而不是等待server应用调用 ``close(8)``。

sock_orphan怎样切断C与用户socket的关系
------------------------------------

``__tcp_close`` 保存当前状态并取得一个临时引用：

::

   state = C.sk_state = TCP_FIN_WAIT1
   sock_hold(C)

随后执行：

::

   sock_orphan(C)

关键效果是：

::

   C.SOCK_DEAD = true
   C.sk_socket = NULL
   C.sk_wq     = NULL

从这里开始，C不再属于一个用户可调用的 ``struct socket``。它仍保留四元组、TCP状态与必要引用，用来处理已经在途的ACK，并在需要时完成FIN重传。

orphan不是立即释放内存。TCP必须先决定由完整 ``tcp_sock`` 继续存活，还是转换成轻量的 ``inet_timewait_sock``。

为什么显式调用__release_sock
---------------------------

HACK在softirq到达时被阻挡在：

::

   C.sk_backlog = [HACK]

``__tcp_close`` 现在执行：

::

   local_bh_disable()
   bh_lock_sock(C)
   __release_sock(C)

注释所说的目标是“remove backlog without releasing ownership”。parent仍然保持C的逻辑user ownership；这里只摘下并处理已有backlog链。

``__release_sock`` 把HACK从C backlog整体摘下，暂时释放内部spinlock，然后通过：

::

   sk_backlog_rcv(C, HACK)
   → tcp_v4_do_rcv(C, HACK)
   → tcp_rcv_state_process(C, HACK)

主动消费ACK。执行环境是parent的kernel process context，不是另一个NET_RX softirq。

tcp_ack怎样确认client FIN
------------------------

HACK携带：

::

   SEG.ACK = C_ISN + 7

client当前：

::

   CTP.snd_una   = C_ISN + 6
   CTP.snd_nxt   = C_ISN + 7
   CTP.write_seq = C_ISN + 7

ACK严格推进 ``snd_una``，且没有超过 ``snd_nxt``。 ``tcp_ack`` 因而写入：

::

   CTP.snd_una : C_ISN + 6 → C_ISN + 7

并从retransmission tree中删除CFIN original。处理后：

::

   C retransmission tree = empty
   C packets_out         = 0
   CFIN retransmission   = no longer pending

HACK是纯ACK，没有payload或FIN，不推进C的 ``rcv_nxt``。

TCP_FIN_WAIT1怎样进入TCP_FIN_WAIT2
--------------------------------

状态处理随后检查：

::

   CTP.snd_una == CTP.write_seq
   C_ISN + 7   == C_ISN + 7

条件成立，说明本地FIN已经完全确认。 ``TCP_FIN_WAIT1`` 分支执行：

::

   tcp_set_state(C, TCP_FIN_WAIT2)
   C.sk_shutdown |= SEND_SHUTDOWN

此时TCP正在等待server方向的FIN。由于C已经由 ``sock_orphan`` 标为 ``SOCK_DEAD``，状态机不会唤醒用户socket。

默认 ``tcp_fin_time(C)`` 为：

::

   sysctl_tcp_fin_timeout = TCP_FIN_TIMEOUT = 60 * HZ

处理HACK时parent仍持有C的用户锁，所以FIN_WAIT1 receive分支先保留完整C并设置相应timer，避免在当前backlog回调尚未返回时替换对象。

``__release_sock`` 完成HACK处理后重新取得内部spinlock，确认没有新backlog，把：

::

   C.sk_backlog.len = 0

并返回 ``__tcp_close``。

为什么__tcp_close还要再次处理FIN_WAIT2
------------------------------------

``__tcp_close`` 增加orphan accounting后重新读取C状态：

::

   C.sk_state = TCP_FIN_WAIT2

C没有negative ``linger2``，所以不会发送active reset。它计算：

::

   tmo = tcp_fin_time(C) = 60 * HZ

并与：

::

   TCP_TIMEWAIT_LEN = 60 * HZ

比较。条件：

::

   tmo > TCP_TIMEWAIT_LEN

为false。于是调用：

::

   tcp_time_wait(C, TCP_FIN_WAIT2, tmo)

这里传入的state不是“已经收到server FIN后的真正TIME_WAIT”，而是轻量对象需要保留的 ``TCP_FIN_WAIT2`` 子状态。

tcp_time_wait怎样建立轻量TW对象
-------------------------------

``tcp_time_wait`` 调用：

::

   inet_twsk_alloc(C, tcp_death_row, TCP_FIN_WAIT2)

分配轻量对象 ``TW``。通用状态字段固定为：

::

   TW.tw_state    = TCP_TIME_WAIT
   TW.tw_substate = TCP_FIN_WAIT2

这两个字段承担不同含义：

* ``tw_state`` 标识这是一个由time-wait基础设施管理的轻量socket；
* ``tw_substate`` 表示协议仍在等待peer FIN，而不是真正的最终TIME_WAIT计时阶段。

TW复制C处理后续packet所需的最小状态：

::

   tuple          = 127.0.0.1:40000 → 127.0.0.1:28080
   tw_rcv_nxt     = S_ISN + 1
   tw_snd_nxt     = C_ISN + 7
   receive window = copied from C
   timestamp      = copied from C
   bind identity  = inherited during hashdance

TW不保留完整userspace socket、send/receive queues或file。应用已经无法再通过fd 7访问这些状态。

hashdance怎样让TW接管四元组
-------------------------

``inet_twsk_hashdance_schedule`` 在ehash与bind结构中完成身份交接：

::

   before:
       client-direction ehash → full tcp_sock C

   after:
       client-direction ehash → inet_timewait_sock TW
       TW.tw_substate         = TCP_FIN_WAIT2
       TW timer               = armed for 60 seconds

随后 ``tcp_time_wait`` 调用 ``tcp_done(C)``。完整C进入 ``TCP_CLOSE``，从剩余协议hash身份退出；最终内存释放要等当前close调用栈持有的临时引用下降。

如果server FIN在60秒内到达，四元组lookup会找到TW。 ``tcp_timewait_state_process`` 看到 ``tw_substate=TCP_FIN_WAIT2``，验证FIN后才把substate改为真正的 ``TCP_TIME_WAIT``，发送ACK并重新按 ``TCP_TIMEWAIT_LEN`` 计时。这是下一批 ``close(8)`` 的入口。

tcp_close怎样释放最后的完整C引用
-------------------------------

``tcp_time_wait`` 返回后， ``__tcp_close`` 执行：

::

   bh_unlock_sock(C)
   local_bh_enable()

外层 ``tcp_close`` 接着：

::

   release_sock(C)
   sock_put(C)

``release_sock`` 释放parent的socket ownership；C已经是 ``TCP_CLOSE``，backlog为空。 ``sock_put`` 放掉 ``__tcp_close`` 为安全收尾持有的引用，完整C可以进入协议销毁流程。TW作为另一个更小的对象继续代表四元组。

控制返回：

::

   tcp_close
   → inet_release
   → __sock_release
   → sock_close
   → __fput
   → fput_close_sync

``inet_release`` 与 ``__sock_release`` 清除CS到C的指针，F7、CS与对应sockfs inode完成最后清理。

close(7)为什么返回0
------------------

本场景：

::

   filp_flush(F7) = 0
   inet_release   = 0

``close`` 的返回值由先前保存的 ``filp_flush`` 结果决定，所以系统调用返回链为：

::

   __x64_sys_close
   → syscall_exit_to_user_mode
   → x86-64 CPL 3

用户态得到：

::

   close(7) = 0

这个0表示fd关闭路径成功完成，不表示peer H已经close，也不表示四元组的轻量TW已经消失。

read(8)为什么不会睡眠
--------------------

parent随后执行：

::

   read(8, buf, 1)

fd lookup仍能得到：

::

   fd 8 → F8 → AS → H

H当前：

::

   H.sk_state            = TCP_CLOSE_WAIT
   H.sk_shutdown         includes RCV_SHUTDOWN
   H.SOCK_DONE           = true
   H.sk_receive_queue    = [FIN skb]
   HTP.copied_seq        = C_ISN + 6

通用read路径进入：

::

   vfs_read
   → sock_read_iter
   → sock_recvmsg
   → inet_recvmsg
   → tcp_recvmsg
   → tcp_recvmsg_locked(H, len=1)

receive queue非空，路径无需安装wait entry，也无需调用 ``schedule_timeout``。

tcp_recvmsg_locked怎样消费FIN
----------------------------

队首FIN skb记录：

::

   seq         = C_ISN + 6
   end_seq     = C_ISN + 7
   payload len = 0
   flags       includes FIN

``copied_seq`` 正好指向它的 ``seq``。没有payload可以复制到 ``buf``，累计用户字节仍为：

::

   copied = 0

receive循环随后检查TCP flags并进入：

::

   found_fin_ok

FIN本身占用一个sequence number，所以写入：

::

   HTP.copied_seq : C_ISN + 6 → C_ISN + 7

本次不是 ``MSG_PEEK``，于是：

::

   tcp_eat_recv_skb(H, FIN skb)

把FIN skb从H receive queue删除并释放。 ``rcv_nxt`` 早在packet到达时已经是 ``C_ISN+7``；现在 ``copied_seq`` 追上它。

为什么返回0而不是一个FIN字节
----------------------------

FIN只存在于TCP sequence space，不是userspace data。 ``tcp_recvmsg_locked`` 返回累计复制量：

::

   copied = 0

外层把它原样返回给read：

::

   read(8, buf, 1) = 0

对stream socket，read返回0就是有序字节流已经到达EOF。 ``buf`` 没有新增有效字节，errno也没有被设置。

H保持 ``TCP_CLOSE_WAIT``。消费EOF不会自动发送server FIN；只有server应用关闭fd 8或显式shutdown send side，TCP才会进入 ``TCP_LAST_ACK`` 并发送自己的FIN。

本章结束状态
------------

* current executor：parent；
* CPU/mode：CPU0，返回x86-64 CPL 3用户态；
* latest syscall/result： ``read(8,buf,1)=0``；
* ``close(7)`` result：0；
* parent schedule count in close与EOF read：0；
* fd 7：closed，fdtable条目为NULL且open位已清除；旧close-on-exec位由未来fd重用覆盖；
* F7/CS/full client C：已完成用户可见生命周期，完整C进入销毁流程；
* client tuple lookup identity：轻量 ``inet_timewait_sock TW``；
* ``TW.tw_state=TCP_TIME_WAIT``；
* ``TW.tw_substate=TCP_FIN_WAIT2``；
* ``TW.tw_rcv_nxt=S_ISN+1``；
* ``TW.tw_snd_nxt=C_ISN+7``；
* TW timer：默认60秒，等待server FIN；
* client FIN original：已确认并从retransmission tree清除；
* fd 8：open、blocking、close-on-exec；
* ``AS.state=SS_CONNECTED``；
* ``H.sk_state=TCP_CLOSE_WAIT``；
* H ``sk_shutdown``：包含 ``RCV_SHUTDOWN``；
* H ``SOCK_DONE``：true；
* ``HTP.rcv_nxt=HTP.copied_seq=C_ISN+7``；
* H receive queue：empty；
* ``HTP.snd_una=HTP.snd_nxt=S_ISN+1``；
* listener fd 6与L：保持open、 ``TCP_LISTEN``；
* network packet backlog：empty；
* next userspace entry： ``close(8)``。

关键边界
--------

#. zero-timeout close不会等待peer FIN，也不会在 ``sk_stream_wait_close`` 中schedule。
#. ``sock_orphan`` 切断完整C与用户socket的关系，协议引用仍允许它处理已入backlog的ACK。
#. ``__release_sock`` 在parent process context消费HACK，确认FIN并清理retransmission state。
#. ``snd_una==write_seq`` 是 ``TCP_FIN_WAIT1`` 进入 ``TCP_FIN_WAIT2`` 的确认条件。
#. 默认 ``tcp_fin_timeout`` 与 ``TCP_TIMEWAIT_LEN`` 都是60秒，比较使用严格大于；相等时转换为轻量TW。
#. TW的通用 ``tw_state`` 为 ``TCP_TIME_WAIT``，协议 ``tw_substate`` 仍为 ``TCP_FIN_WAIT2``。
#. hashdance让TW接管四元组，完整C随后进入 ``TCP_CLOSE`` 并结束生命周期。
#. ``close(7)=0`` 不等于server H已经关闭，也不等于四元组已经释放。
#. FIN到达时推进 ``rcv_nxt``，read消费FIN时才推进 ``copied_seq``。
#. FIN占用TCP sequence number，不向userspace提供字节。
#. blocking read遇到已排队FIN立即返回0，无需真正睡眠。
#. EOF read不会替server应用发送FIN；H继续停在 ``TCP_CLOSE_WAIT``。

下一入口
--------

下一章从：

::

   close(8)
   → remove accepted fd 8
   → fput_close_sync(F8)
   → inet_release(AS)
   → tcp_close(H, timeout=0)

开始。H会从 ``TCP_CLOSE_WAIT`` 进入 ``TCP_LAST_ACK`` 并发送server FIN。client方向lookup将命中 ``TW.tw_substate=TCP_FIN_WAIT2``；TW确认FIN、发送最终ACK并转入真正 ``TCP_TIME_WAIT``，H收到ACK后结束 ``TCP_LAST_ACK``。

资料
----

* `Linux 7.2-rc1 net/ipv4/tcp.c：__tcp_close、tcp_fin_time与tcp_recvmsg_locked <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp.c>`_
* `Linux 7.2-rc1 net/core/sock.c：sock_orphan、__release_sock与release_sock <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_input.c：FIN ACK推动TCP_FIN_WAIT2 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_input.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_minisocks.c：tcp_time_wait与FIN_WAIT2子状态处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_minisocks.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_timewait_sock.c：inet_twsk_alloc与hashdance <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_timewait_sock.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_ipv4.c：默认tcp_fin_timeout <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_ipv4.c>`_
* `Linux 7.2-rc1 include/net/tcp.h：TCP_FIN_TIMEOUT与TCP_TIMEWAIT_LEN <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/net/tcp.h>`_
* `Linux 7.2-rc1 net/socket.c：sock_read_iter与sock_recvmsg <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
