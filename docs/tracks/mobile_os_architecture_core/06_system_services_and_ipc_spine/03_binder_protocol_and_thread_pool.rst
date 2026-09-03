========================================================================
Chapter 30: Binder 协议栈与线程池动态调度：BC/BR 状态机、优先级继承与嵌套死锁防御
========================================================================

.. note:: 前置背景与认知承接
   在上一章（Chapter 29）中，我们下沉至 Linux 内核态深入剖析了 Binder 驱动的底层基座，系统解构了基于 `struct binder_proc` 与 `binder_mmap()` 的单次内存拷贝微架构、`binder_node` 与 `binder_ref` 的红黑树寻址网络，以及基于四维引用计数矩阵的跨进程内存生命周期闭环。驱动层为整个 Android 系统铺设了低时延、抗篡改的数据与句柄路由通道。

   然而，在数据通道打通之后，操作系统控制面必须解决更为复杂的并发与调度挑战：用户态框架与内核驱动如何协同解码海量事务？服务端的线程池如何感知系统并发压力并实现微秒级弹性扩容？非阻塞的异步单向调用（`oneway`）如何兼顾保序执行与防爆内存？当高优先级前台 UI 线程向后台服务发起调用时，如何防止发生严重的优先级反转？当跨进程调用形成复杂的嵌套回调链路时，系统如何避免自身发生死锁？

   本章我们将从用户态 `IPCThreadState` 穿透至内核调度核心，全面解密 Binder 的通信协议栈与并发调度中枢。本章将详细剖析 `BINDER_WRITE_READ` 双向状态机、BC 与 BR 命令流互锁机制、线程池动态扩容算法（`BR_SPAWN_LOOPER`）、单向异步事务队列串行化、EAS 拓扑下的实时优先级继承（Priority Inheritance），以及基于事务链回溯的嵌套重入死锁防御体系。

------------------------------------------------------------------------
30.1 Binder 通信协议栈全貌：ioctl、BC 命令与 BR 返回码状态机
------------------------------------------------------------------------

BINDER_WRITE_READ 双向批处理微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在用户态与内核驱动的物理交界面上，Binder 摒弃了频繁执行轻量系统调用的传统设计。如果每一次发送请求和读取响应都分别发起一次系统调用，CPU 在用户态（EL0）与内核态（EL1）之间的频繁陷入（Exception Trap）与模式切换将产生巨大的指令流水线冲刷与 TLB 抖动开销。

Android 设计了高度集约的统一交互接口——`ioctl(mDriverFD, BINDER_WRITE_READ, &bwr)`。该系统调用通过核心结构体 `struct binder_write_read`，允许线程在**单次内核陷入中同时完成“提交待发送数据”与“拉取待处理任务”**：

.. code-block:: c

   // include/uapi/linux/android/binder.h
   struct binder_write_read {
       binder_size_t write_size;                // 写入缓冲区中有效数据字节数
       binder_size_t write_consumed;            // 驱动已成功处理消费的字节数
       binder_uintptr_t write_buffer;           // 用户空间写缓冲区虚拟地址指针 (包含 BC 命令序列)
       
       binder_size_t read_size;                 // 读取缓冲区最大可用字节数
       binder_size_t read_consumed;             // 驱动已填充写回用户空间的字节数
       binder_uintptr_t read_buffer;            // 用户空间读缓冲区虚拟地址指针 (接收 BR 返回码序列)
   };

`IPCThreadState` 在用户空间分配两个私有的连续内存缓冲区：`mOut`（写入缓冲区）与 `mIn`（读取缓冲区）。当线程发起跨进程调用时，工作流程如下：

1. **打包出站数据**：线程将业务数据序列化后生成的 Binder 命令与负载追加写入 `mOut`，设置 `write_size = mOut.dataSize()`，`write_consumed = 0`；
2. **预留入站空间**：设置 `read_size = mIn.dataCapacity()`，`read_consumed = 0`；
3. **单次陷入内核**：执行 `ioctl(BINDER_WRITE_READ)`。内核驱动优先遍历消费 `write_buffer`，执行发送或应答逻辑；随后若 `read_size > 0`，驱动就地将当前线程或进程等待队列中的就绪任务填入 `read_buffer`；
4. **用户态就地解包**：系统调用返回后，`write_consumed` 反映成功发送的字节偏移，`read_consumed` 指示有效接收数据量。`IPCThreadState` 遍历 `read_buffer`，逐条派发返回码。

双向协议命令集分类与状态流转
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Binder 协议栈严格划分为两大指令族系：
- **BC 命令 (Binder Command)**：由**用户态发起，内核态驱动接收并执行**；
- **BR 返回码 (Binder Return)**：由**内核态驱动产生，用户态框架解析并响应**。

.. list-table:: 核心 BC 命令与 BR 返回码矩阵
   :widths: 18 14 20 48
   :header-rows: 1
   :class: tight-table

   * - 协议指令
     - 方向
     - 关联参数负载
     - 微架构动作与语义
   * - **BC_TRANSACTION**
     - 用户 $	o$ 内核
     - `struct binder_transaction_data`
     - 发起跨进程调用。指定目标 Handle、接口 Code、数据缓冲区与 `FLAG_ONEWAY` 标志。
   * - **BC_REPLY**
     - 用户 $	o$ 内核
     - `struct binder_transaction_data`
     - 发送同步调用的结果响应。必须对应前置的一个处于挂起等待状态的入站事务。
   * - **BC_FREE_BUFFER**
     - 用户 $	o$ 内核
     - `binder_uintptr_t` (内存指针)
     - 释放内核之前通过 `mmap` 分配给本次调用的缓冲区，驱动就地执行物理块释放与碎片合并。
   * - **BC_ENTER_LOOPER**
     - 用户 $	o$ 内核
     - 无
     - 当前线程（通常是主线程）主动告知驱动已进入 Binder 循环，注册为非动态生成的固定工作线程。
   * - **BC_REGISTER_LOOPER**
     - 用户 $	o$ 内核
     - 无
     - 响应驱动的 `BR_SPAWN_LOOPER` 指令，告知驱动动态孵化出的新工作线程已就绪，计入工作线程池。
   * - **BR_TRANSACTION**
     - 内核 $	o$ 用户
     - `struct binder_transaction_data`
     - 驱动通知服务端的某个空闲线程：当前收到新的入站调用，需解包并执行 `onTransact()`。
   * - **BR_REPLY**
     - 内核 $	o$ 用户
     - `struct binder_transaction_data`
     - 驱动通知客户端阻塞线程：之前发起的同步事务已收到对端的应答数据，解除挂起状态。
   * - **BR_SPAWN_LOOPER**
     - 内核 $	o$ 用户
     - 无
     - 驱动感知到当前服务并发度极高且线程池尚有余量，指令用户态立即启动一个新的线程加入循环。
   * - **BR_TRANSACTION_COMPLETE**
     - 内核 $	o$ 用户
     - 无
     - 驱动确认：`BC_TRANSACTION` 或 `BC_REPLY` 已成功被驱动入队。对于 `oneway` 事务，客户端收到此码即视为调用结束。
   * - **BR_DEAD_REPLY**
     - 内核 $	o$ 用户
     - 无
     - 驱动检测到目标服务进程在请求处理过程中发生崩溃（Crash）或被 LMKD 杀死，通知客户端调用失败。

------------------------------------------------------------------------
30.2 事务处理状态机与数据流转生命周期 (Transaction Lifecycle)
------------------------------------------------------------------------

struct binder_transaction_data 与内核实体映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

跨进程传输的核心负载由 `struct binder_transaction_data` 承载：

.. code-block:: c

   // include/uapi/linux/android/binder.h
   struct binder_transaction_data {
       union {
           size_t handle;                       // 客户端视角：目标服务的远程 Handle (0 为 SM)
           binder_uintptr_t ptr;                // 服务端视角：本地 BBinder 对象的内存弱引用地址
       } target;
       binder_uintptr_t cookie;                 // 服务端视角：本地 BBinder 对象的强引用实体指针
       uint32_t code;                           // 业务接口方法编号 (AIDL 中的 TRANSACTION_xxx)
       uint32_t flags;                          // 事务行为标志 (如 FLAG_ONEWAY, FLAG_CLEAR_BUF)
       
       pid_t sender_pid;                        // 内核强行注入的调用方真实 PID (只读安全凭证)
       uid_t sender_euid;                       // 内核强行注入的调用方真实 UID (只读安全凭证)
       
       binder_size_t data_size;                 // 业务 Parcel 纯数据负载长度
       binder_size_t offsets_size;              // Parcel 中包含的 Binder 对象偏移量数组长度
       
       union {
           struct {
               binder_uintptr_t buffer;         // 目标进程映射空间内的已拷贝数据首地址
               binder_uintptr_t offsets;        // 对象偏移量数组首地址
           } ptrs;
           uint8_t buf[8];
       } data;
   };

在内核空间内部，驱动将其包裹为更为完整的调度控制块 `struct binder_transaction`：

.. code-block:: c

   // drivers/android/binder.c
   struct binder_transaction {
       int debug_id;
       struct binder_work work;                 // 挂入目标 todo 队列的工作项
       struct binder_thread *from;              // 发起该事务的源线程 (同步调用用于返回应答)
       struct binder_tid sender_euid;
       struct binder_proc *to_proc;             // 目标接收进程
       struct binder_thread *to_thread;         // 目标接收线程 (特定线程寻址)
       struct binder_transaction *from_parent;  // 嵌套事务调用链上的父节点
       struct binder_transaction *to_parent;    // 目标线程正在等待的上一个事务
       
       unsigned need_reply:1;                   // 是否为同步调用 (1: 需等待 BC_REPLY; 0: oneway)
       struct binder_buffer *buffer;            // 在接收方进程中分配的物理内存块
       unsigned int flags;                      // 事务标志
       struct binder_priority saved_priority;   // 继承前的线程原始调度优先级
   };

目标线程定位与派发状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当发送方线程通过 `BC_TRANSACTION` 将数据推入内核时，`binder_transaction()` 函数执行极其严谨的目标定位算法：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Binder 内核事务目标定位与工作队列派发流向                 |
   +-------------------------------------------------------------------------+

   [ 发送方线程发起 BC_TRANSACTION ]
                  |
                  v 提取 target.handle
     +---------------------------+
     | handle 是否为 0 ?         |
     +---------------------------+
       | 是 (定向到 ServiceManager)   | 否 (普通业务服务)
       |                             v
       |                     在 proc->refs_by_desc 红黑树检索 binder_ref
       |                             |
       +------------+----------------+
                    | 获得目标 binder_node
                    v
     +-------------------------------------------------------+
     | 检查 need_reply (是否为同步调用 ?)                    |
     +-------------------------------------------------------+
       |                                     |
       | 同步调用 (need_reply = 1)           | 异步单向 (flags & FLAG_ONEWAY)
       v                                     v
   +------------------------------------+  +---------------------------------+
   | 寻找目标工作线程:                  |  | 进入单向异步队列治理:           |
   | 1. 检查是否存在匹配的嵌套重入线程; |  | 检查 node->has_async_transaction|
   | 2. 检索 to_proc->waiting_threads;  |  | 若已有 oneway 正在服务端执行,   |
   | 3. 若无空闲线程, 目标线程设为 NULL |  | 则追加至 node->async_todo 挂起; |
   |    挂入 to_proc->todo 进程全局队列 |  | 若无冲突, 挂入 to_proc->todo    |
   +------------------------------------+  +---------------------------------+
                  |                                  |
                  v                                  v
   +-------------------------------------------------------------------------+
   | 唤醒目标线程: wake_up_interruptible(&target_thread->wait)               |
   | 若无特定线程, 唤醒进程队列: wake_up_interruptible(&to_proc->wait)       |
   +-------------------------------------------------------------------------+

端到端同步事务完整生命周期
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

一次经典的跨进程同步 RPC 完整流转如图所示：

.. code-block:: text

   [ 客户端线程 (Process A) ]           [ Linux 内核 Binder 驱动 ]         [ 服务端线程 (Process B) ]
            |                                    |                                  |
            | 1. transact(code, data, reply)     |                                  |
            |    追加 BC_TRANSACTION 至 mOut     |                                  |
            |    执行 ioctl(BINDER_WRITE_READ)   |                                  |
            +----------------------------------->|                                  |
            | (客户端线程挂起等待 BR_REPLY)      | 2. 检查 target.handle            |
            |                                    |    分配目标进程物理页            |
            |                                    |    copy_from_user() 写入         |
            |                                    |    就地转换 Binder/FD 对象       |
            |                                    | 3. 构建 binder_transaction       |
            |                                    |    压入服务端 todo 队列          |
            |                                    | 4. 唤醒服务端空闲线程            |
            |                                    +--------------------------------->|
            |                                    |                                  | 5. 服务端线程从 wait 队列唤醒
            |                                    |                                  |    从 read_buffer 读取 BR_TRANSACTION
            |                                    |                                  |    调用 onTransact(code, data, reply)
            |                                    |                                  | 6. 执行核心业务逻辑，填充 reply Parcel
            |                                    |                                  | 7. 发起回复：
            |                                    |                                  |    写入 BC_REPLY + BC_FREE_BUFFER
            |                                    |                                  |    执行 ioctl(BINDER_WRITE_READ)
            |                                    |<---------------------------------+
            |                                    | 8. 释放接收缓冲区物理块          | (服务端线程回到 looper 循环
            |                                    |    依据 transaction->from 寻址   |  继续等待新的 BR_TRANSACTION)
            |                                    |    将回复数据写入客户端内存映射  |
            |                                    | 9. 唤醒客户端挂起线程            |
            |                                    |    塞入 BR_REPLY                 |
            |<-----------------------------------+                                  |
            | 10. 客户端线程唤醒恢复运行         |                                  |
            |     解包 reply Parcel 数据         |                                  |
            |     发送 BC_FREE_BUFFER 归还物理页 |                                  |
            |     业务代码获得跨进程调用结果     |                                  |
            v                                    v                                  v

整个流转严格遵循“请求打包 $	o$ 驱动单次拷贝 $	o$ 服务端唤醒执行 $	o$ 响应打包 $	o$ 驱动单次拷贝写回 $	o$ 客户端唤醒解包”的闭环，每一步都在内核精确跟踪之下。

------------------------------------------------------------------------
30.3 Binder 线程池架构与内核动态扩容机制 (Thread Pool & BR_SPAWN_LOOPER)
------------------------------------------------------------------------

ProcessState 初始化与线程池上限配置
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Android 进程模型中，任何支持接收跨进程调用的服务端进程都必须拥有一个 Binder 线程池。线程池的初始化在 C++ 原生层通过单例 `ProcessState` 完成：

.. code-block:: cpp

   // frameworks/native/libs/binder/ProcessState.cpp
   #define DEFAULT_MAX_BINDER_THREADS 15

   ProcessState::ProcessState(const char *driver) {
       mDriverFD = open_driver(driver);
       if (mDriverFD >= 0) {
           // 1. 设置最大驱动可主动请求孵化的线程上限 (默认 15)
           size_t maxThreads = DEFAULT_MAX_BINDER_THREADS;
           ioctl(mDriverFD, BINDER_SET_MAX_THREADS, &maxThreads);
       }
   }

通过 `BINDER_SET_MAX_THREADS`，进程向驱动声明了其**动态扩容的上限（`max_threads = 15`）**。这意味着驱动后续最多能要求该进程启动 15 个额外的子线程。加上进程显式调用 `startThreadPool()` 启动的 1 个初始主循环线程，一个标准的 Android 进程默认拥有最多 **16 个 Binder 线程并发处理入站事务的能力**。

主线程与子线程的协议注册差异
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

线程池中的线程虽然行为相同，但在与驱动建立关系时有严格的语义区分：

1. **主 Binder 线程 (Main Looper)**：
   应用主线程或服务初始化线程调用 `IPCThreadState::self()->joinThreadPool(true)`。参数为 `true` 表示该线程由用户空间主动开启。该线程向驱动发送 **`BC_ENTER_LOOPER`** 命令，内核将该线程标记为 `BINDER_LOOPER_STATE_ENTERED`。**该线程不计入 `requested_threads` 动态计数**。
2. **辅助孵化线程 (Spawned Worker)**：
   由驱动通过 `BR_SPAWN_LOOPER` 动态请求启动的线程，在执行 `joinThreadPool(false)` 时，参数为 `false`。它向驱动发送 **`BC_REGISTER_LOOPER`** 命令，内核将其标记为 `BINDER_LOOPER_STATE_REGISTERED`。**此线程会使内核中的 `proc->requested_threads_started` 计数加 1**。

内核触发 BR_SPAWN_LOOPER 的判定算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Binder 驱动绝非在进程启动时立刻把 16 个线程全部创建出来（这会白白消耗 16 个线程的内核 `task_struct`、栈内存与调度实体）。相反，内核采用**按需懒加载（On-Demand Lazy Spawning）**机制。

在 `drivers/android/binder.c` 的 `binder_thread_read()` 中，每当一个线程即将退出空闲等待、准备返回用户空间处理事务时，驱动都会执行扩容检测：

.. code-block:: c

   // drivers/android/binder.c 线程池扩容判定
   static void binder_thread_read(...) {
       // ... 准备返回 BR_TRANSACTION 处理事务 ...
       
       if (proc->requested_threads == 0 &&
           proc->ready_threads == 0 &&
           proc->requested_threads_started + proc->threads < proc->max_threads &&
           (thread->looper & (BINDER_LOOPER_STATE_ENTERED |
            BINDER_LOOPER_STATE_REGISTERED))) {
           
           proc->requested_threads++;
           put_user(BR_SPAWN_LOOPER, (uint32_t __user *)ptr);
           ptr += sizeof(uint32_t);
       }
   }

驱动触发 `BR_SPAWN_LOOPER` 的充要条件包括：
1. `proc->ready_threads == 0`：当前没有任何空闲处于等待状态的工作线程；
2. `proc->requested_threads == 0`：此前驱动发出的孵化请求已经全部被用户态处理完毕，没有在途未决的孵化任务；
3. `proc->requested_threads_started + proc->threads < proc->max_threads`：当前实际存在的线程总数加上已启动线程数，尚未触碰 15 的硬性天花板；
4. 当前正在返回的线程自身必须处于合法的 Looper 循环状态。

当满足上述四重约束时，驱动会在当前返回数据中紧随业务返回码注入一条 `BR_SPAWN_LOOPER`。

用户态线程创建闭环
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

用户态 `IPCThreadState::executeCommand()` 捕获到 `BR_SPAWN_LOOPER` 后的执行流如下：

.. code-block:: cpp

   // frameworks/native/libs/binder/IPCThreadState.cpp
   case BR_SPAWN_LOOPER:
       mProcess->spawnPooledThread(false);
       break;

`ProcessState::spawnPooledThread(false)` 立即调用底层 `pthread_create()` 创建一条名称为 `Binder:pid_x` 的新线程。该新线程启动后立刻执行：

.. code-block:: cpp

   IPCThreadState::self()->joinThreadPool(false);

该调用向驱动写入 `BC_REGISTER_LOOPER`，驱动执行 `proc->requested_threads--`，并将新线程置入 `proc->waiting_threads` 队列等待任务到达。至此，全系统完成一次闭环的微秒级自适应弹性伸缩。

线程池耗尽 (Thread Pool Exhaustion) 与系统级假死
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

如果一个服务端的 16 个 Binder 线程全部被长时间运行的操作阻塞（例如每个线程都在执行耗时的大文件 I/O、死锁互斥、慢网络请求或复杂的数据库全表扫描），此时：

1. `proc->ready_threads` 归零；
2. 当前活跃线程总数达到 `max_threads`，驱动拒绝继续下发 `BR_SPAWN_LOOPER`；
3. 后续所有发往该服务的跨进程调用，只能被驱动强制排入 `proc->todo` 全局队列；
4. 客户端的同步发起线程全部被物理挂起在内核等待队列中（`wait_event_interruptible`）；
5. 若客户端是应用主线程，5 秒后触发系统 **ANR (Application Not Responding)**；若客户端是系统核心服务，整个系统的图形界面与服务网格将发生严重的级联级停滞（Cascading Freeze）。

因此，系统架构准则明令禁止：**严禁在 Binder 线程池主干路径执行同步耗时阻塞 I/O；所有重型任务必须异步移交至独立的业务 WorkQueue 线程池解耦执行**。

------------------------------------------------------------------------
30.4 同步事务 vs 异步单向事务 (Oneway Transactions) 调度差异
------------------------------------------------------------------------

FLAG_ONEWAY 语义与非阻塞执行模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 AIDL 接口定义中，若方法声明了 `oneway` 关键字（如 `oneway void reportStatus(int code);`），该调用被标记为异步单向事务。其生成的 Binder 封包标志位将被置位为：
$$	ext{flags} \ |= 	ext{FLAG\_ONEWAY}$$

同步事务与异步事务的核心机制对比如下：

.. list-table:: 同步事务与异步单向事务 (Oneway) 核心调度对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - 同步事务 (need_reply = 1)
     - 异步事务 (FLAG_ONEWAY)
   * - **客户端行为**
     - 发起后当前线程立即挂起，等待服务端回复 `BR_REPLY`。
     - 发送数据包进入驱动后，驱动立刻返回 `BR_TRANSACTION_COMPLETE`，客户端不等待、直接继续执行。
   * - **返回值与输出参数**
     - 支持任意复杂返回值与 `out/inout` 形参反向传输。
     - 方法返回值强制要求为 `void`，严禁任何 `out` 形参。
   * - **目标调度队列**
     - 优先寻找空闲专属线程，直接定向派发。
     - 受到目标 `binder_node` 内部的 `async_todo` 队列严格流控约束。
   * - **执行顺序保证**
     - 依赖客户端调用时序，不同线程并发调用无序竞争。
     - **严格保证时序性**：同一客户端发往同一服务实体的 oneway 事务严格按序串行化执行。
   * - **异常反馈**
     - 服务端抛出的异常（如 `SecurityException`）能原路抛回客户端。
     - 服务端异常无法通知调用方（调用方已继续执行），仅在服务端控制台报错。

内核 Oneway 异步队列串行化与防爆机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

异步调用带来极高吞吐的同时，也带来了巨大的系统性隐患：如果某个应用以极端极速（如死循环）向系统服务疯狂投递 `oneway` 事务，由于客户端完全不被挂起，瞬间数万个事务将挤爆内核缓冲区；或者服务端并发分配多个线程同时处理同一对象的配置更改，导致服务端状态严重错乱。

为化解这一危机，Linux 内核 Binder 驱动在 `binder_node` 内部设计了精巧的**异步流控状态机（Async Transaction Serializer）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             Binder 内核 oneway 事务串行化与缓冲队列管理                 |
   +-------------------------------------------------------------------------+

   [ 客户端连续快速发起 3 次 oneway 事务: T1, T2, T3 (发往同一 binder_node) ]
                                    |
                                    v 进入内核 binder_transaction()
   +=========================================================================+
   | Linux 内核态 (目标 binder_node)                                         |
   |                                                                         |
   | 检查 node->has_async_transaction 标志位:                                |
   |                                                                         |
   | 1. 处理 T1:                                                             |
   |    - 此时 has_async_transaction 为 0;                                   |
   |    - 设置 node->has_async_transaction = 1;                              |
   |    - 允许 T1 立即挂入服务端的全局 proc->todo 队列, 唤醒线程执行!        |
   |                                                                         |
   | 2. 处理 T2:                                                             |
   |    - 检查到 has_async_transaction == 1 (T1 尚在执行中!);                |
   |    - 驱动拒绝将 T2 挂入 proc->todo, 而是将 T2 压入 node->async_todo 挂起! |
   |                                                                         |
   | 3. 处理 T3:                                                             |
   |    - 同理, 将 T3 顺序追加在 node->async_todo 队尾 (T2 之后).            |
   +=========================================================================+
                                    |
                                    | 服务端线程执行完 T1 业务逻辑,
                                    | 调用 freeBuffer() 发送 BC_FREE_BUFFER
                                    v
   +=========================================================================+
   | 内核捕获 BC_FREE_BUFFER:                                                |
   | 1. 释放 T1 所占用的接收端物理内存页;                                    |
   | 2. 检测到该 node 的 async_todo 队列非空 (存在等待中的 T2);              |
   | 3. 将 T2 从 node->async_todo 移出, 挂入 proc->todo 队列, 唤醒线程执行;  |
   | 4. 保持 node->has_async_transaction = 1, 直至整个 async_todo 清空!      |
   +=========================================================================+

这一机制揭示了两个极其关键的系统特性：
1. **天然防错乱的时序一致性**：发往同一个 Binder 实体的所有 `oneway` 事务，**永远不会在服务端被两个不同线程并发乱序执行**。即便服务端有 16 个空闲线程，T2 也必须等待 T1 执行完毕并释放内存后，才会被派发执行；
2. **异步内存防爆保护**：由于串行化执行，任何时候同一节点在服务端活跃执行的 oneway 物理内存块只有一个。如果应用发起 oneway 过于凶猛，`async_todo` 积压导致分配缓冲区失败时，驱动会向调用方抛出错误，阻止其无节制挤占内核映射区。

------------------------------------------------------------------------
30.5 优先级继承 (Priority Inheritance) 与实时性保障
------------------------------------------------------------------------

优先级反转 (Priority Inversion) 物理场景
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

移动系统的核心生命线是**交互流畅度（60Hz/120Hz 零掉帧）**。前台交互线程（Top-App UI 线程与 RenderThread）在 Linux 调度体系中通常被赋予极高的调度优先级（例如 `SCHED_NORMAL` 下通过 CFS 赋予较低的 nice 值，如 `nice = -10`，或者直接赋予实时调度策略 `SCHED_FIFO`）。

然而，当一个前台高优先级线程通过 Binder 调用后台共享系统服务（如 `PackageManagerService`）时，极易诱发致命的**优先级反转**：

.. code-block:: text

   [ 前台交互线程 (High Priority: nice = -10) ]
       |
       | 1. 发起同步 Binder 调用
       v
   [ 目标服务工作线程 (Low Priority: 默认分配 nice = 0) ] <====== 被抢占阻塞!
                                                                  ^
   [ 某个后台计算任务 (Medium Priority: nice = -2) ] -------------+
       抢占 CPU 执行权! 导致后台服务工作线程无法获得 CPU 时间片,
       进而导致前台高优先级线程被无限期卡死挂起!

此时，原本意图让后台线程慢速运行的低优先级机制，反向拖垮了处于绝对最高优先级的用户界面响应。

Binder 驱动的优先级继承算法与 EAS 联动
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为根除这一隐患，Binder 驱动深度集成了**优先级继承（Priority Inheritance - PI）**算法。

在 `drivers/android/binder.c` 的 `binder_transaction()` 中，当驱动组装同步调用时，会自动对比调用方与目标服务端的调度属性：

.. code-block:: c

   // drivers/android/binder.c 优先级继承逻辑
   static void binder_transaction(...) {
       // ... 锁定调用方线程与服务端线程 ...
       
       if (!t->need_reply) {
           // oneway 事务不执行优先级继承
           return;
       }
       
       // 1. 备份服务端线程的原始优先级
       t->saved_priority.sched_policy = target_thread->task->policy;
       t->saved_priority.prio = target_thread->task->normal_prio;
       
       // 2. 获取调用方当前优先级
       int caller_prio = current->normal_prio;
       
       // 3. 比较并执行继承: 若调用方优先级更高 (prio 数值更小)
       if (caller_prio < target_thread->task->normal_prio) {
           binder_set_priority(target_thread->task, caller_prio);
       }
   }

具体执行流程与系统效应：

1. **瞬时优先级提升**：驱动调用内核调度器接口 `sched_setscheduler_nocheck()`，将目标服务端工作线程的调度策略与 `nice` 值瞬间提升至与调用方完全一致（`nice = -10`）；
2. **EAS 能耗感知调度器联动**：在 ARM DynamIQ 大小核芯片架构下，由于服务线程优先级被瞬时拉升，内核 EAS 调度器的负载容量追踪模型（WALT/PELT）立刻感知到该线程的急迫性，**瞬间将该服务工作线程从低功耗小核（Cortex-A520）迁移放置到超大核心（Cortex-X4）**，并强制激发 CPUFreq 调速器执行毫秒级提频（Frequency Boosting）；
3. **完成调用后平滑降级**：服务端线程执行完毕向客户端发送 `BC_REPLY`。内核在注销该事务时，读取之前保存在 `t->saved_priority` 中的基准数值，**原样将服务端线程还原至其原始的常规优先级**。

这套机制确保了系统服务无论自身基准配置为何，都能在响应前台交互的微秒级窗口内享受全系统顶级的算力倾斜。

------------------------------------------------------------------------
30.6 嵌套事务、重入与死锁防御体系
------------------------------------------------------------------------

跨进程循环依赖诱发死锁
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

随着移动系统服务网格的不断扩张，跨进程服务调用链变得高度纵深与网状化。最典型的场景即为**双向嵌套回调（Nested Re-entrant Calls）**：

.. code-block:: text

   [ 进程 A (客户端) ]              [ 进程 B (系统服务) ]
           |                                  |
           | 1. A 发起同步调用 f()            |
           +--------------------------------->|
           | (A 线程挂起等待 B 响应)           | 2. B 线程在执行 f() 的过程中,
           |                                  |    需要向 A 进程反向调用 g()
           |                                  |    获取最新的设备上下文状态
           |                                  | 3. B 发起向 A 的同步调用 g()
           |<---------------------------------+
           | ???
           v

如果处理不当，上述模式必然引发死锁：
- 假设进程 A 的 Binder 线程池此时已经耗尽（或者进程 A 只有 1 个主工作线程）；
- 进程 A 正在处理最初的业务，该线程正挂起阻塞在第 1 步的等待队列中；
- 此时进程 B 发送的第 3 步反向调用到达进程 A，由于进程 A 没有可用的就绪工作线程，该调用被排入进程 A 的 `todo` 队列挂起等待；
- 结果：**A 等待 B 完成 f()，而 B 等待 A 完成 g()**，形成双向跨进程死锁，直至系统崩溃。

事务调用栈 (Transaction Stack) 拓扑与线程偷取机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Binder 驱动通过在内核维护精密的**事务栈（Transaction Stack）**，从物理机制上彻底终结了上述嵌套死锁：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Binder 内核事务调用链回溯与线程复用机制                   |
   +-------------------------------------------------------------------------+

   [ 进程 A (Thread A1) ]                   [ 进程 B (Thread B1) ]
            |                                         |
            | 1. 发送事务 T1 (need_reply = 1)         |
            +---------------------------------------->| (Thread B1 唤醒执行 T1)
            |                                         |
            | 内核记录:                               |
            | T1->from      = Thread A1               |
            | T1->to_thread = Thread B1               |
            | Thread B1->transaction_stack = T1       |
            |                                         |
            |                                         | 2. Thread B1 在处理 T1 时,
            |                                         |    发起向 A 的同步反向事务 T2!
            |<----------------------------------------+
            |
   +=========================================================================+
   | Linux 内核态检测逻辑 (binder_transaction):                              |
   |                                                                         |
   | 驱动寻找承接 T2 的目标线程:                                             |
   | 1. 沿当前线程 Thread B1 的 transaction_stack 向上回溯;                  |
   | 2. 发现 T1 存在父依赖关系: T1->from 是进程 A 的 Thread A1;              |
   | 3. 命中重入循环依赖!                                                    |
   | 4. 驱动裁决:                                                            |
   |    - 绝不向进程 A 请求分配新的空闲线程!                                 |
   |    - 将 T2 的目标直接指定为 Thread A1: T2->to_thread = Thread A1;       |
   |    - 将 T2 挂入 Thread A1 的私有 todo 队列!                             |
   +=========================================================================+
            |
            | 3. 驱动唤醒正在挂起的 Thread A1!
            v
   [ Thread A1 从 ioctl 返回, 但收到的不是 BR_REPLY, 而是嵌套的 BR_TRANSACTION (T2)! ]
            |
            | 4. Thread A1 就地执行本地回调业务逻辑 g()
            | 5. Thread A1 发送 BC_REPLY 响应 T2
            +---------------------------------------->|
                                                      | 6. Thread B1 收到 T2 响应, 恢复执行
                                                      | 7. Thread B1 完成 T1, 发送 BC_REPLY
            |<----------------------------------------+
            |
   [ Thread A1 最终收到原始的 BR_REPLY (T1), 全流程闭环结束! ]

这种机制被称为**挂起线程复用（Thread Stealing / Re-entrant Re-use）**：
- 驱动能够精准识别一条跨越多个进程的封闭环状事务链（Transaction Chain）；
- 当环路形成时，发起源头处于挂起状态的原始调用线程被安全唤醒，就地承接反向请求；
- **该机制完全不消耗目标进程空闲线程池配额，即便利程内部只配置了 1 个线程，也能完美支持无限层级的嵌套跨进程回调**。

多进程环路死锁的检测极限
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

必须注意区分**同一调用链上的嵌套重入**与**不同调用链之间的资源死锁**：
1. **链路自身重入**（如上述 $A 	o B 	o A$）：由 Binder 事务栈完全免疫死锁；
2. **多并发事务交叉死锁**：例如进程 A 的线程 1 调用进程 B 并等待锁 L1，而进程 B 的线程 2 调用进程 A 并等待锁 L2；或者进程 A 在持有 Java 内部对象监视器锁（`synchronized`）的同时发起阻塞 Binder 调用，而服务端又尝试回调 A 并争夺同一把 Java 监视器锁。

后一种死锁发生在**用户态语言虚拟机内部或多并发链路之间**，超越了内核单个事务栈的回溯范畴。针对这种死锁，移动架构规范设立了两大铁律：
- **铁律一：跨进程 Binder 调用前严禁持有本地互斥锁**。所有状态更新应在本地锁保护下完成后释放锁，再发起无锁的远端 IPC 调用；
- **铁律二：双向重型交互采用异步解耦设计**。将紧密耦合的同步双向 RPC 拆解为独立的 `oneway` 消息流水线，彻底切断物理等待链路。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章深入 Android Binder 的中枢控制面，系统解构了支撑移动系统高并发运行的协议与调度拓扑：
- 解构了 `BINDER_WRITE_READ` 双向批处理微架构，详细梳理了核心 BC 命令与 BR 返回码的流转状态机；
- 深入推导了 `struct binder_transaction_data` 的端到端时序流转与内核派发机制；
- 剖析了 Binder 线程池的 `max_threads = 15` 配置、主/子线程注册差异以及基于 `BR_SPAWN_LOOPER` 的内核懒加载扩容机制与防耗尽准则；
- 揭秘了 `oneway` 异步单向事务在内核 `node->async_todo` 驱动下的串行化保序与内存防爆控制流；
- 阐释了优先级继承（PI）在 EAS 能耗感知调度器下的联动原理，确保前台交互算力倾斜；
- 剖析了利用内核事务栈（Transaction Stack）识别调用链重入并就地复用挂起线程的死锁防御体系。

至此，我们已经完整建立了 Binder IPC 在物理内存、驱动数据结构与并发协议调度三个维度的深层认知。在下一章——**Chapter 31: 硬件能力仲裁与多租户并发访问控制** 中，我们将视角从通用数据传输转向具体的物理外设治理，深入相机子系统独占抢占、音频焦点状态机以及低功耗传感器数据聚合的软硬件中介控制面。
