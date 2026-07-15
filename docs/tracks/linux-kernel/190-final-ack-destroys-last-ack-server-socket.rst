第一百九十章：最终ACK怎样结束H的LAST_ACK并让close(8)返回0？
=========================================================

上一章结束时，client TW已经接收server FIN并进入真正TIME_WAIT，最终ACK则停在H的socket backlog中：

::

   parent / CPU0 / close(8) kernel call stack

   server H
       state         = TCP_LAST_ACK
       shutdown      = SHUTDOWN_MASK
       snd_una       = S_ISN + 1
       snd_nxt       = S_ISN + 2
       write_seq     = S_ISN + 2
       rcv_nxt       = C_ISN + 7
       retrans q     = [HFIN-original]
       sk_backlog    = [TACK]
       owned         = by parent

   client TW
       tw_state      = TCP_TIME_WAIT
       tw_substate   = TCP_TIME_WAIT
       tw_rcv_nxt    = S_ISN + 2
       tw_snd_nxt    = C_ISN + 7
       timer         = rearmed for 60 seconds

   TACK.seq          = C_ISN + 7
   TACK.ack_seq      = S_ISN + 2

fd 8已经从fdtable撤销，F8的同步 ``__fput`` 尚未返回。本章从server FIN发送返回后的 ``__tcp_close`` 继续：zero-timeout等待不会schedule；H成为orphan，parent通过 ``__release_sock`` 消费TACK。ACK确认HFIN后， ``TCP_LAST_ACK`` 分支调用 ``tcp_done``，H进入 ``TCP_CLOSE`` 并开始协议销毁。最后F8、AS与sockfs inode完成释放， ``close(8)=0`` 返回用户态。TW保持真正TIME_WAIT，60秒timer到期留给下一批。

本章固定条件
------------

* 只有CPU0 online，parent保持当前执行者；
* ``tcp_close(H)`` 的timeout为0，没有linger等待；
* TACK checksum、timestamp与ACK sequence有效；
* H retransmission tree中只有HFIN original；
* H没有新receive data、RST、signal、memory pressure或并发packet；
* TW timer不会在close(8)返回前到期；
* listener fd 6保持open，accept queue为空；
* H、F8与AS没有额外外部引用。

tcp_send_fin返回后怎样结束发送调用
--------------------------------

上一章的嵌套NET_RX完成后，返回链结束HFIN发送：

::

   NET_RX_SOFTIRQ returns
   → rcu_read_unlock_bh returns
   → __dev_queue_xmit(HFIN) returns
   → ip_output returns
   → tcp_transmit_skb returns
   → __tcp_push_pending_frames returns
   → tcp_send_fin(H) returns

HFIN original仍在H retransmission tree，TACK已经在 ``H.sk_backlog``。TCP状态尚未改变：

::

   H.sk_state = TCP_LAST_ACK

只有parent处理backlog中的TACK后，才能确认FIN并结束状态机。

zero-timeout等待为什么不会schedule
---------------------------------

``__tcp_close`` 接着调用：

::

   sk_stream_wait_close(H, timeout=0)

没有linger时间可用，所以等待路径不会执行：

::

   schedule_timeout()

parent保持 ``TASK_RUNNING``。这个“没有等待”不表示最终ACK尚未到达；TACK已经在backlog中，只是受H user ownership保护，尚未交给TCP receive状态机。

sock_orphan怎样结束H的用户归属
-----------------------------

``__tcp_close`` 保存当前状态并取得临时引用：

::

   state = H.sk_state = TCP_LAST_ACK
   sock_hold(H)

随后调用：

::

   sock_orphan(H)

关键变化为：

::

   H.SOCK_DEAD = true
   H.sk_socket = NULL
   H.sk_wq     = NULL

H不再属于accepted ``struct socket AS``。协议对象仍由当前close调用栈、ehash与未确认HFIN的传输状态保持，足以处理TACK。

与client主动关闭不同，H此时已经在 ``TCP_LAST_ACK``。它不需要创建FIN_WAIT2轻量对象；最终ACK到达后可以直接进入 ``TCP_CLOSE``。

为什么__release_sock在释放ownership前处理TACK
------------------------------------------

``__tcp_close`` 执行：

::

   local_bh_disable()
   bh_lock_sock(H)
   __release_sock(H)

H的逻辑user ownership仍属于parent。 ``__release_sock`` 把：

::

   H.sk_backlog = [TACK]

从socket上整体摘下，暂时释放内部spinlock，然后调用：

::

   sk_backlog_rcv(H, TACK)
   → tcp_v4_do_rcv(H, TACK)
   → tcp_rcv_state_process(H, TACK)

执行环境是parent的kernel process context。TACK不需要再次经过NET_RX；它已经由上一章的softirq完成demux并排入正确socket。

tcp_ack怎样确认HFIN
------------------

TACK携带：

::

   SEG.ACK = S_ISN + 2

H当前send状态为：

::

   HTP.snd_una   = S_ISN + 1
   HTP.snd_nxt   = S_ISN + 2
   HTP.write_seq = S_ISN + 2

ACK严格推进 ``snd_una``，且不超过 ``snd_nxt``。 ``tcp_ack`` 写入：

::

   HTP.snd_una : S_ISN + 1 → S_ISN + 2

并从retransmission tree中删除HFIN original。处理后：

::

   H retransmission tree = empty
   H packets_out         = 0
   HFIN retransmission   = no longer pending

TACK没有payload或FIN，不推进H的 ``rcv_nxt``；它只完成server发送方向最后一个sequence number的确认。

TCP_LAST_ACK怎样进入TCP_CLOSE
----------------------------

状态处理到达：

::

   case TCP_LAST_ACK

并检查：

::

   HTP.snd_una == HTP.write_seq
   S_ISN + 2   == S_ISN + 2

条件成立，说明H的FIN已被完全确认。路径执行：

::

   tcp_update_metrics(H)
   tcp_done(H)

然后消费TACK并结束receive处理。这里没有TIME_WAIT转换；H是收到第一个FIN后才关闭的一侧，四次挥手的TIME_WAIT责任已经由client TW承担。

tcp_done怎样关闭协议状态
-----------------------

``tcp_done`` 首先执行：

::

   tcp_set_state(H, TCP_CLOSE)

``tcp_set_state`` 在发布 ``TCP_CLOSE`` 前把H从established ehash中移除，并处理连接端口ownership的退出。以后同一四元组的packet不会再找到完整H。

随后：

::

   tcp_clear_xmit_timers(H)

清除H的retransmission、delayed-ACK、keepalive等连接timer。HFIN已经得到确认，不再需要任何重传timer。

``tcp_done`` 再确保：

::

   H.sk_shutdown = SHUTDOWN_MASK

H已经由 ``sock_orphan`` 设置 ``SOCK_DEAD``，所以不会调用用户socket的 ``sk_state_change``；它直接进入：

::

   inet_csk_destroy_sock(H)

开始释放完整connection socket的协议资源。

为什么tcp_done可以在__release_sock中销毁H
---------------------------------------

当前调用栈仍保存：

::

   sock_hold(H)

所以 ``inet_csk_destroy_sock`` 可以拆除协议身份和资源，而不会让正在执行的 ``__tcp_close`` 使用已经释放的内存。真正对象存储要等最后引用下降后回收。

``__release_sock`` 完成TACK skb释放，重新取得内部spinlock并确认没有新backlog。此时：

::

   H.sk_state       = TCP_CLOSE
   H.sk_backlog.len = 0

然后返回 ``__tcp_close``。

为什么__tcp_close直接跳到out
---------------------------

进入orphan收尾前保存的：

::

   state = TCP_LAST_ACK

backlog处理后的：

::

   H.sk_state = TCP_CLOSE

所以判断：

::

   state != TCP_CLOSE && H.sk_state == TCP_CLOSE

为true。注释把这种情况描述为socket已经被softirq或backlog销毁。路径跳到：

::

   out
   → bh_unlock_sock(H)
   → local_bh_enable()

它不会再执行FIN_WAIT2、orphan OOM或其他close状态分支。

tcp_close怎样放掉H的最后协议引用
--------------------------------

外层 ``tcp_close`` 继续：

::

   release_sock(H)

释放parent持有的socket user ownership。H已是 ``TCP_CLOSE``，backlog与传输timer为空。

随后：

::

   inet_csk_clear_xmit_timers_sync(H)  // when required by net ref state
   sock_put(H)

``sock_put`` 放掉 ``__tcp_close`` 为收尾取得的引用。固定没有其他外部引用，完整H最终由协议destructor回收；route cache、拥塞控制私有状态和剩余socket memory accounting一并结束。

这里没有建立server方向TW。系统中唯一继续代表该连接四元组的对象是client侧真正TIME_WAIT的TW。

inet_release怎样完成AS清理
-------------------------

控制返回：

::

   tcp_close
   → inet_release(AS)

``inet_release`` 写：

::

   AS.sk = NULL

随后 ``__sock_release`` 清理 ``AS.ops`` 与socket/file关联。 ``sock_close`` 返回0， ``__fput`` 继续释放：

* F8的file operations引用；
* F8与sockfs dentry/path引用；
* accepted sockfs inode I8；
* 最终file对象F8。

fd 8早在系统调用入口就已经失效；这里完成的是它背后对象的最后生命周期。

close(8)为什么返回0
------------------

本场景：

::

   filp_flush(F8) = 0
   inet_release   = 0
   sock_close     = 0

``close`` 使用保存的 ``filp_flush`` 结果返回：

::

   __x64_sys_close
   → syscall_exit_to_user_mode
   → x86-64 CPL 3

用户态得到：

::

   close(8) = 0

这个0表示accepted fd及其最后file/socket清理已经完成。client TW仍然存在是正常TCP生命周期，不会让close阻塞60秒。

为什么TW还不能立即释放
----------------------

当前：

::

   TW.tw_state    = TCP_TIME_WAIT
   TW.tw_substate = TCP_TIME_WAIT
   TW.tw_rcv_nxt  = S_ISN + 2
   TW.tw_snd_nxt  = C_ISN + 7

TW timer从HFIN到达时重新按 ``TCP_TIMEWAIT_LEN=60*HZ`` 启动。若server FIN的ACK丢失，H可能重传HFIN；在H已销毁的固定故事中不再发生重传，但协议不能在发送TACK瞬间假定ACK必然到达。

TW继续留在ehash与bind结构中，让迟到或重复segment按TIME_WAIT规则处理，并保护旧四元组sequence空间。它的timer到期、ehash/bind拆除与最终free是新的timer softirq执行边界，留给下一章。

listener为什么完全不受影响
-------------------------

server listener仍由fd 6独立持有：

::

   fd 6       = open, blocking, close-on-exec
   L.state    = TCP_LISTEN
   L endpoint = 127.0.0.1:28080
   accept q   = empty
   ack backlog = 0

H虽然继承并共享本地端口28080的bind体系，但它是具体连接四元组。H的LAST_ACK销毁不会关闭listener，也不会撤销L的lhash2身份。server仍可在同一fd 6上接受新的连接。

本章结束状态
------------

* current executor：parent；
* CPU/mode：CPU0，返回x86-64 CPL 3用户态；
* final syscall/result： ``close(8)=0``；
* parent schedule count in close：0；
* fd 8：closed，fdtable条目为NULL且open位已清除；
* F8/AS/I8：最后生命周期完成；
* server child H： ``TCP_LAST_ACK → TCP_CLOSE``，完整socket完成协议销毁；
* HFIN original：已确认并从retransmission tree清除；
* H established ehash identity：removed；
* H backlog与传输timer：empty/cleared；
* client fd 7：closed；
* ``TW.tw_state=TCP_TIME_WAIT``；
* ``TW.tw_substate=TCP_TIME_WAIT``；
* ``TW.tw_rcv_nxt=S_ISN+2``；
* ``TW.tw_snd_nxt=C_ISN+7``；
* TW tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* TW ehash/bind/timer：active，timer剩余接近60秒；
* server fd 6：open、blocking、close-on-exec；
* listener L：``TCP_LISTEN``，accept queue empty， ``sk_ack_backlog=0``；
* packet与CPU0 NET_RX backlog：empty；
* next entry：TW的60秒timer到期并进入time-wait回收路径。

关键边界
--------

#. TACK已经到达H backlog，所以zero-timeout close无需schedule也能完成协议关闭。
#. ``sock_orphan`` 切断H与AS；当前close引用仍保护backlog处理期间的对象内存。
#. ``__release_sock`` 在parent process context消费TACK。
#. TACK把 ``snd_una`` 推进到 ``S_ISN+2`` 并清除HFIN original。
#. ``TCP_LAST_ACK`` 以 ``snd_una==write_seq`` 判断本地FIN已经确认。
#. H作为passive closer直接进入 ``TCP_CLOSE``，不创建server time-wait socket。
#. ``tcp_done`` 清除ehash身份与传输timer；SOCK_DEAD使它进入协议销毁。
#. ``__tcp_close`` 发现backlog已把H改成TCP_CLOSE后直接跳到out。
#. fd 8撤销发生在对象清理之前，close返回时F8/AS/I8的最后生命周期完成。
#. ``close(8)=0`` 不等待TW的60秒timer。
#. 真正TIME_WAIT的TW是连接留下的唯一四元组对象。
#. listener L与具体child H生命周期独立；H销毁不影响fd 6继续listen。

下一入口
--------

下一章从时间推进到TW timer到期开始：

::

   TW.tw_timer expires after TCP_TIMEWAIT_LEN
   → tw_timer_handler(TW)
   → inet_twsk_kill(TW)
   → remove TW from ehash and bind structures
   → drop timer/hash references
   → inet_twsk_free(TW)

TW释放后client四元组不再由旧连接占用。后续可以继续关闭listener fd 6，拆除 ``TCP_LISTEN``、lhash2、bind bucket与sockfs对象，结束整个TCP loopback场景。

资料
----

* `Linux 7.2-rc1 net/core/sock.c：__release_sock、sock_orphan与release_sock <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_input.c：TCP_LAST_ACK最终ACK处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_input.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp.c：tcp_done与__tcp_close收尾 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_connection_sock.c：inet_csk_destroy_sock <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_connection_sock.c>`_
* `Linux 7.2-rc1 net/socket.c：accepted socket/file release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 fs/file_table.c：__fput完成F8与sockfs path释放 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_timewait_sock.c：TW timer与最终回收入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_timewait_sock.c>`_
