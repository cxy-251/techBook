第一百九十三章：listener怎样释放bind端口与最后的sockfs对象？
================================================================

上一章停在 ``__tcp_close`` 的 ``adjudge_to_death`` 标签。CPU0仍在parent的
``close(6)`` 系统调用内，mode是x86-64 CPL 0。fdtable中的6号slot已经是 ``NULL``，
listener ``L`` 已经从 ``lhash2`` 删除并发布为 ``TCP_CLOSE``，空request/accept队列
也已停止；但显式bind留下的 ``inet_num=28080``、bind owner与bind2 owner仍然存在。
文件 ``F6``、sockfs socket ``LS`` 和inode ``I6`` 也都还在当前 ``__fput`` release链上。

本章从这个不对用户可见、却对销毁顺序关键的中间状态继续。目标不是再关一次fd，
而是让协议层先放掉端口与队列资源，再让socket、文件和sockfs路径结束生命期，同时
保留listener启用的RCU回收边界。

adjudge_to_death给孤儿socket建立安全销毁条件
--------------------------------------------

``adjudge_to_death`` 先读取L当前状态；它已经是 ``TCP_CLOSE``。``__tcp_close`` 取得一份
临时 ``sock_hold``，确保后面的orphan与协议destroy之间L不会提前消失，然后调用
``sock_orphan``。orphan化把用户socket一侧与协议socket分开，并设置 ``SOCK_DEAD``；
从这一点起，即使LS仍在外层release栈上，L也不再是一个可由应用socket继续操作的端点。

函数随后关闭本CPUbottom half，取得L的BH socket锁。``__release_sock`` 会处理socket
backlog，但listener停止前后的backlog都是空的，所以这里没有TCP输入段可消费，也不会
重走SYN、ACK或FIN状态机。TCP orphan计数在destroy期间记录这个不再由用户socket拥有
的协议对象，便于内存压力与统计路径看见它。

销毁条件现在全部满足：L是 ``TCP_CLOSE``，具有 ``SOCK_DEAD``，已经unhash，且本地
端口非零时仍有合法bind节点。``__tcp_close`` 因此进入
``inet_csk_destroy_sock(L)``，而不是安排一个新的关闭timer。

tcp_v4_destroy_sock在释放存储前清空传输层资源
------------------------------------------------

``inet_csk_destroy_sock`` 调用L所属协议的destroy函数，也就是
``tcp_v4_destroy_sock``。这是TCP/IPv4资源的最终清理点，不是VFS文件释放点。

destroy函数清除可能残留的TCP timer、拥塞控制与ULP状态，清空write queue和
out-of-order queue，并检查传输层内存记账。固定listener从未在这些队列中保存应用
payload，request/accept队列也已在上一章停止，因此这些动作验证为空并完成通用清理，
不会生成skb或网络报文。

紧接着，``tcp_v4_destroy_sock`` 看见 ``icsk_bind_hash`` 仍非 ``NULL``。这正是显式bind
没有在 ``tcp_set_state`` 中提前释放的所有权，于是函数调用 ``inet_put_port``。

inet_put_port最终撤销28080的bind与bind2身份
------------------------------------------

``inet_put_port`` 进入 ``__inet_put_port``，按固定顺序定位并锁住普通bind bucket与
bind2 bucket。锁内，L从两个owner链删除，``icsk_bind_hash`` 与
``icsk_bind2_hash`` 被清为 ``NULL``，``inet_num`` 从28080清为0。

本场景没有另一个socket共享 ``127.0.0.1:28080`` 的bind owner。删除L后，bind2 owner
链与普通bind owner链都为空，对应空bucket可以从hash表销毁。锁释放之后，网络命名空间
里不再有旧listener对28080的端口所有权。

现在才可以准确地说28080可供后续正常bind竞争。上一章只完成了“没有listener lookup
能找到L”，本章才完成“端口冲突检查也不再看见L”。将两者合并会掩盖
``SOCK_BINDPORT_LOCK`` 对显式bind socket的真实作用。

TCP destroy随后撤销TCP socket分配统计。``inet_csk_destroy_sock`` 再清理stream通用
queue、xfrm policy与orphan记账，并放掉destroy阶段持有的socket引用。``__tcp_close``
退出BH锁域、恢复bottom half，``release_sock`` 释放process-context socket锁；先前
``sock_hold`` 对应的最后引用也在close尾部放回。

SOCK_RCU_FREE把L的存储回收推迟到grace period之后
--------------------------------------------------

L在进入 ``lhash2`` 时设置过 ``SOCK_RCU_FREE``。这是listener曾暴露给无锁/RCU读侧
lookup的记录，不能因为本场景只有CPU0就删掉这条边界。最终socket引用归零时，
``sk_destruct`` 不直接在当前栈上释放L的slab存储，而是通过 ``call_rcu`` 安排
``__sk_destruct``。

到这里，L已经不可达：fd 6不存在，LS与L已经orphan，lhash2、bind与bind2都没有L，
队列和timer也为空。RCU延后的是内存回收，不是继续listen，也不是继续占有28080。
在grace period结束前，早先可能开始的RCU读侧仍可安全越过旧指针；之后
``__sk_destruct`` 才调用 ``inet_sock_destruct`` 与 ``sk_prot_free``，把完整L的存储
归还协议slab。

因此，``close(6)`` 不等待RCU grace period。把close返回写成“已经同步执行
``kmem_cache_free(L)``”会过度承诺；把RCU pending写成“listener仍然活着”也同样错误。
正确区分是：TCP身份与端口在close路径内同步结束，L的物理存储可在close返回后延迟
回收。

返回sockfs release链并完成close(6)
----------------------------------

``tcp_close`` 返回 ``inet_release`` 后，socket层把 ``LS.sk``、ops与file关联按release
协议清空。``sock_close`` 返回 ``__fput``，F6不再提供任何socket操作入口。

``__fput`` 接着放掉file operations owner、credential与path相关引用。匿名sockfs dentry
的最后路径引用允许VFS执行inode eviction；``sock_evict_inode`` 清理I6的扩展属性并
调用 ``clear_inode``，最终 ``sock_free_inode`` 把内嵌LS的 ``sockfs_inode`` 容器归还
``sock_inode_cache``。VFS/RCU允许其中某些存储回收晚于逻辑引用消失，因此本章固定的
同步保证是F6、LS与I6已从parent及socket协议关系中不可达，而不是强迫所有cache free
都发生在同一条指令之前。

``file_free`` 结束F6的file对象生命期。固定场景中 ``filp_flush`` 与socket release都
没有错误，``close_fd`` 返回0；CPU0执行系统调用返回，parent恢复x86-64 CPL 3，
仍是 ``TASK_RUNNING``。listener关闭没有发送FIN或RST，也没有等待网络确认，因此
本次 ``close(6)`` 没有调度。

随后，当CPU0越过满足RCU要求的quiescent state、对应grace period结束时，先前安排的
L回调得到执行并释放协议socket存储。这个回调不改变close已经返回0的结果，也不会再
产生TCP状态、端口或报文。至此，本场景创建的fd 6、7、8以及L、C、H、R、TW、LS、AS
等对象都不再形成可达的TCP端点；全局sockfs、网络命名空间、lo设备与TCP协议本身继续
存在，它们不是这个场景的私有对象。

TCP/IPv4 loopback主线在这里闭合
--------------------------------

这条TCP主线从fd 6创建listener开始，经历显式bind、listen、client connect、三次握手、
accept4、数据收发、双方close、TIME_WAIT与listener teardown，现在到达自然终点。
最终没有lhash2 listener、established ehash连接、request socket、time-wait socket、
bind owner、TCP timer、skb或场景私有sockfs对象。端口40000与28080都不再由旧场景占用。

Linux Kernel总体目标仍是完成全部43条源码主线，而不是把第193章当作全书终点。
TCP/IPv4是完成的第19条主线，后面还有24条；章节数继续由源码边界自然决定，不从
``43`` 反推出固定总章数。下一条主线进入UDP/IPv4，首先让parent调用

.. code-block:: c

   socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, IPPROTO_UDP)

追踪datagram socket怎样创建并取得新的最低可用fd 6。UDP没有listen、accept与
TCP连接状态机；它会从自己的hash、bind、route、datagram send/receive与错误报告边界
重新展开，不能把TCP对象模型直接套过去。

本章结束状态
------------

* current executor：parent；
* CPU/mode：CPU0，x86-64 CPL 3；
* last syscall/result：``close(6)=0``；
* parent：``TASK_RUNNING``，listener close没有调度；
* fd 6/7/8：closed；
* ``F6``、``LS``、``I6``：对parent与socket关系不可达，最终VFS生命期已启动/完成；
* listener ``L``：``TCP_CLOSE``、orphan、unhashed，协议资源已销毁；
* L的lhash2、bind与bind2身份：removed；
* ``L.inet_num``：0；
* listener端口28080：不再由旧L占用；
* client端口40000：不再由旧TW占用；
* L的物理存储：按 ``SOCK_RCU_FREE`` 在grace period后由 ``__sk_destruct`` 回收；
* connection对象 ``C/H/R/TW``：gone；
* TCP request/accept/write/retransmission/receive/backlog queues：empty/gone；
* TCP timer与场景skb：none；
* TCP/IPv4 loopback主线：complete；
* Linux Kernel主线进度：19/43完成，24条待完成；
* next mainline：UDP/IPv4。

关键边界
--------

#. ``adjudge_to_death`` 先以临时引用保护L，再orphan化并进入BH锁域。
#. L已是 ``TCP_CLOSE``、``SOCK_DEAD`` 且unhashed，满足 ``inet_csk_destroy_sock`` 前提。
#. 空backlog与传输队列仍经过通用destroy检查，但不产生skb、报文或状态迁移。
#. 显式bind的28080由 ``tcp_v4_destroy_sock`` 中的 ``inet_put_port`` 最终释放。
#. ``inet_put_port`` 同时清除普通bind、bind2与 ``inet_num``，空bucket随后销毁。
#. listener身份从lhash2撤销早于端口身份从bind表撤销，两者不能合并成一步。
#. ``SOCK_RCU_FREE`` 延后L的存储回收，不延后端口释放，也不维持listener可达性。
#. ``close(6)=0`` 不等待RCU grace period；回调晚于返回是允许且预期的。
#. sockfs inode内嵌LS；path/inode生命期结束与TCP L的RCU回收是两套机制。
#. 固定close没有FIN、RST、lo收发、网络等待或任务调度。
#. 全局sockfs、lo、网络命名空间与TCP协议继续存在，不属于场景私有销毁范围。
#. 43是源码主线目标数，不是固定章节总数；后续仍按自然源码边界分章。

下一入口
--------

进入第20条主线UDP/IPv4：parent在CPU0用户态调用
``socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, IPPROTO_UDP)``。从fd预留、sockfs对象创建、
``inet_create`` 协议选择与 ``udp_prot`` 初始化开始，固定新的datagram socket在发布fd 6
之前具有哪些尚未bind、尚未hash的状态。

资料
----

* `固定源码：net/ipv4/tcp.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp.c>`_
* `固定源码：net/ipv4/tcp_ipv4.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_ipv4.c>`_
* `固定源码：net/ipv4/inet_connection_sock.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_connection_sock.c>`_
* `固定源码：net/ipv4/inet_hashtables.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_hashtables.c>`_
* `固定源码：net/ipv4/af_inet.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
* `固定源码：net/socket.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `固定源码：fs/file_table.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `固定源码：include/net/sock.h <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/net/sock.h>`_
