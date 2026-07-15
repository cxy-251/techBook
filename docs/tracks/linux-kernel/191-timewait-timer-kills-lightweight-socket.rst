第一百九十一章：TIME_WAIT timer怎样撤销最后的四元组并释放TW？
==================================================================

上一章结束时，parent已经从 ``close(8)`` 返回到CPU0上的x86-64 CPL 3。
fd 7和fd 8都已关闭，完整client ``C`` 与server child ``H`` 也都结束了；
但是连接并没有从TCP命名空间里完全消失。四元组

::

   127.0.0.1:40000 → 127.0.0.1:28080

仍由轻量 ``inet_timewait_sock TW`` 占据。它同时还保有三类生命周期依据：
established hash里的四元组身份、bind表里的本地端口身份，以及peer FIN到达时重新
启动的60秒timer。listener ``L`` 则是另一条独立身份，仍通过fd 6监听
``127.0.0.1:28080``。

现在没有新系统调用。parent继续在用户态运行，CPU0上的时钟中断不断推进内核时间。
当peer FIN之后的 ``TCP_TIMEWAIT_LEN`` 用尽，TW的timer从timer wheel到期；
CPU0把 ``TIMER_SOFTIRQ`` 标记为pending，并在合适的中断返回边界进入softirq处理。
执行者仍在CPU0，但mode已经从被中断的CPL 3切到内核态；这不是parent主动调用
``schedule``，也没有另一项用户任务接管TW。

timer callback只负责死亡，不再重走TCP状态机
-----------------------------------------------

TW的timer函数是 ``tw_timer_handler``。它通过 ``timer_container_of`` 从
``struct timer_list`` 找回外层 ``inet_timewait_sock``，随后只做一件事：

.. code-block:: c

   static void tw_timer_handler(struct timer_list *t)
   {
       struct inet_timewait_sock *tw =
           timer_container_of(tw, t, tw_timer);

       inet_twsk_kill(tw);
   }

这里没有把 ``tw_substate`` 再推进到某个新TCP状态，也没有发送最后一个报文。
真正的TIME_WAIT已经在第一百八十九章由server FIN建立；60秒等待的目的，是让旧连接
报文越过其可能存活的时间，并在等待结束后撤销内核中的剩余身份。callback因此直接
进入 ``inet_twsk_kill``。

创建TW时，``inet_twsk_hashdance_schedule`` 把 ``tw_refcnt`` 固定为3。这三个引用
分别对应bind hash、established hash与已安排的timer。timer到期并不意味着callback
一进入就已经失去timer引用；相反，当前callback正借最后这份timer所有权安全地访问
TW。接下来每撤销一种身份，就会准确放掉相应的一份引用。

先从ehash撤销四元组可查身份
----------------------------

``inet_twsk_kill`` 要求bottom half已经在本CPU关闭。当前来自timer softirq的执行环境
满足这一前提。函数先定位TW所在的ehash bucket，并取得该bucket的锁。此时并发的
TCP输入lookup不能一边把TW当作有效成员，一边看见半拆除的hash节点。

``sk_nulls_del_node_init_rcu((struct sock *)tw)`` 把TW的nulls hlist节点从
established hash删除并重新初始化。删除采用RCU可见的hash规则：已经开始的读侧lookup
可以按RCU规则走完，但新的四元组lookup不再从ehash找到TW。辅助函数在节点确实处于
hash中时同时执行 ``__sock_put``，所以TW引用由3降到2。

这一刻首先消失的是“入站TCP段还能按四元组命中TW”的身份。它还不是完整释放点：
bind表仍认为本地端口40000有owner，当前timer callback也仍持有最后的执行期引用。

再从bind与bind2撤销本地端口身份
--------------------------------

ehash bucket解锁后，``inet_twsk_kill`` 继续取得与TW对应的bind bucket和bind2 bucket锁。
本场景的TW同时保留普通bind hash与按本地地址区分的bind2身份；这让端口分配和冲突
检查在TIME_WAIT期间仍能看见 ``127.0.0.1:40000`` 的旧连接约束。

``inet_twsk_bind_unhash`` 从bind owner链删除TW，把 ``tw_tb`` 与 ``tw_tb2`` 清成
``NULL``，并在owner链已经为空时销毁对应的bind2 bucket与普通bind bucket。
本场景没有第二个socket共享client端口40000，也没有并发bind或connect，所以这些
bucket在删除TW后正好为空。bind身份放掉的 ``__sock_put`` 使引用由2降到1。

现在，端口40000不再由这个TW占用。这里说“可再次分配”只表示旧TW的hash/bind
所有权已经撤销；下一次socket是否恰好获得40000，仍由正常的显式bind冲突检查、
临时端口选择策略和当时命名空间状态决定，不能把“旧限制消失”写成“下一次一定分配
同一个端口”。

最后一份timer引用触发轻量对象释放
------------------------------------

bind锁释放后，``inet_twsk_kill`` 递减death row记录的TIME_WAIT对象计数。这个计数
描述全局或per-net TIME_WAIT负担，不等同于 ``tw_refcnt`` 中某一种对象所有权。
随后函数调用 ``inet_twsk_put`` 放掉当前到期timer对应的最后一份TW引用。

固定场景没有并发ehash reader额外取得TW引用，也没有其他路径重新安排timer，因此
引用由1准确降到0。``inet_twsk_put`` 进入 ``inet_twsk_free``：先调用协议提供的
``tcp_twsk_destructor`` 完成TCP轻量对象的析构，再把对象归还 ``twsk_slab``，最后
放掉创建该time-wait socket时取得的协议模块引用。

这条顺序不能倒过来。ehash节点与bind owner必须先不可见，timer的最后引用才能归零；
否则lookup或端口检查就可能指向已经回到slab的内存。反过来，只从timer wheel取下
timer而不执行两个unhash，也不能宣称四元组已经消失。

callback返回后，timer softirq继续检查本轮到期timer。固定场景没有其他待处理timer，
``TIMER_SOFTIRQ`` 结束，CPU0从中断/softirq返回路径恢复被打断的parent用户态执行。
整个过程没有TCP报文、没有lo设备收发，也没有把parent置为睡眠状态。

TCP连接身份已经清空，listener仍然独立存在
-------------------------------------------

TW释放以后，fd 7和fd 8代表的连接侧对象不再留下任何TCP hash身份。ehash中没有C、H、
request sock或TW；client bind表中也没有40000的旧owner；重传、TIME_WAIT timer、
socket backlog和lo backlog都为空。

但fd 6没有参与这次callback。listener ``L`` 仍是 ``TCP_LISTEN``，仍在精确地址
``127.0.0.1:28080`` 的 ``lhash2`` bucket里，并仍通过显式bind拥有28080的bind与
bind2身份。它的request queue与accept queue都是空的，``sk_ack_backlog`` 仍为0。
因此，TIME_WAIT结束只收掉已完成连接，不能顺便关闭server监听端点。

parent下一条固定动作是 ``close(6)``。这将先让fd 6对用户态不可达，再沿F6的最后引用
进入 ``sock_close``、``inet_release`` 与 ``tcp_close(L,0)``；listener身份的拆除从
那里开始，而不是从本章的TW callback开始。

本章结束状态
------------

* current executor：parent，timer softirq已经返回；
* CPU/mode：CPU0，x86-64 CPL 3；
* parent：``TASK_RUNNING``，本章没有调用 ``schedule``；
* fd 7/8：closed；完整 ``C`` 与 ``H``：gone；
* ``TW``：ehash节点、bind/bind2 owner与timer引用均已撤销；
* ``TW.tw_refcnt``：``3 → 2 → 1 → 0``，轻量对象已归还 ``twsk_slab``；
* client端口40000：不再由旧TW占用；
* packet、lo backlog与socket backlog：empty；
* fd 6：open、blocking、close-on-exec；
* listener ``L``：``TCP_LISTEN``，``127.0.0.1:28080``；
* listener lhash2与bind/bind2身份：active；
* listener request/accept queue：empty，``sk_ack_backlog=0``。

关键边界
--------

#. 到期timer通过 ``TIMER_SOFTIRQ`` 执行；它不要求parent主动进入系统调用。
#. ``tw_timer_handler`` 直接调用 ``inet_twsk_kill``，不再进行新的TCP状态迁移。
#. 初始三份TW引用分别对应ehash、bind与timer，不是三个任意临时引用。
#. ehash删除先让新的四元组lookup不再命中TW，并放掉第一份引用。
#. bind与bind2删除再解除本地端口40000的旧owner身份，并放掉第二份引用。
#. death row对象计数与 ``tw_refcnt`` 是不同维度，不能混写成同一个引用。
#. timer callback持有最后一份对象引用；最后的 ``inet_twsk_put`` 才把引用降为0。
#. 固定场景无并发lookup附加引用，因此 ``inet_twsk_free`` 在callback内到达。
#. 端口40000不再受旧TW占用，不等于下一次分配必然选择40000。
#. TW释放不影响独立listener；fd 6、lhash2和端口28080仍然有效。
#. 本章没有TCP报文、lo收发或任务调度。

下一入口
--------

parent在CPU0用户态调用 ``close(6)``；从 ``file_close_fd`` 先撤销fd 6开始，追踪
``tcp_close(L,0)`` 怎样让listener离开 ``lhash2``、进入 ``TCP_CLOSE``，同时解释
为什么显式bind的28080不会在 ``tcp_set_state`` 那一步提前释放。

资料
----

* `固定源码：net/ipv4/inet_timewait_sock.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_timewait_sock.c>`_
* `固定源码：include/net/inet_timewait_sock.h <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/net/inet_timewait_sock.h>`_
* `固定源码：include/net/sock.h <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/net/sock.h>`_
* `固定源码：kernel/time/timer.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/timer.c>`_
* `固定源码：kernel/softirq.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/softirq.c>`_
* `RFC 9293：Transmission Control Protocol <https://www.rfc-editor.org/rfc/rfc9293>`_
