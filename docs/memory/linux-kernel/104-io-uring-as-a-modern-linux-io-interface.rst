第104章：io_uring 作为现代 Linux I/O 接口
=========================================

核心知识点
----------

``io_uring`` 是共享队列协议
   用户态与内核通过 Submission Queue、Completion Queue 和 SQE 数组交换请求与结果，减少高频系统调用、描述复制和逐请求同步开销。

Ring 实例由 fd 管理
   ``io_uring_setup()`` 创建实例并返回 ring fd。用户态根据 ``io_uring_params`` 映射实际 SQ、CQ 和 SQE 布局，不能假设固定 feature。

SQE 描述请求，CQE 描述结果
   SQE 的字段意义由 opcode 决定；CQE 通过 ``user_data``、``res`` 和 ``flags`` 返回身份、结果和附加状态。

队列发布需要内存顺序
   用户态必须先完整填写 SQE，再发布 SQ tail；内核必须先完整填写 CQE，再发布 CQ tail。直接操作 ring 时要遵守 UAPI 的 acquire/release 规则。

发布不等于完成
   SQ tail 推进只表示请求可被内核看到。内核消费 SQE、底层完成和 CQE 被用户读取是三个不同阶段。

``user_data`` 是生命周期锚点
   它可保存 ID、索引、generation 或受控指针。若使用指针，对象必须存活到所有相关终结 CQE 被消费。

CQE 结果按请求语义解释
   ``res >= 0`` 常表示字节数或操作结果，``res < 0`` 表示负 errno。短 I/O、EOF 和部分完成不能被简化成布尔成功。

完成顺序可乱序
   不同文件、缓存命中、设备和 worker 会让 CQE 顺序偏离提交顺序。应用必须按 token 关联请求，不能依赖数组位置。

Multishot 请求拥有多个完成
   一个 SQE 可以产生多个 CQE。只有 flags 明确表示终结后，业务对象、buffer 和 token 才能完整释放。

数据路径由具体操作决定
   ``io_uring`` 可提交 buffered I/O、Direct I/O、网络和其它操作。它不自动绕过 Page Cache，也不改变文件系统持久化规则。

请求可能走不同执行上下文
   有些操作可在提交上下文快速完成，有些原生异步派发，有些转交 ``io-wq``。因此 ``io_uring`` 不等于没有线程或所有操作都不阻塞。

Fixed file 减少重复 fd 查找
   注册文件后 ring 持有 ``struct file`` 引用，请求以固定索引访问。关闭原 fd 不会自动释放 ring 的引用。

Registered buffer 减少重复准备
   预注册可摊销地址验证和页固定成本，但会延长内存被 pin 或保留的时间，并不自动形成端到端 zero-copy。

SQ 与 CQ 都是有限资源
   SQ 满表示缺少可发布槽位，CQ 积压表示完成消费太慢。正常路径必须持续 reap，并设置独立于 ring 大小的业务在途上限。

Polling 用 CPU 换延迟
   SQPOLL 轮询提交队列，IOPOLL 轮询设备完成。二者作用阶段不同，均可能增加 CPU、功耗和同核干扰。

Linked operations 表达依赖
   Link、drain、timeout 和 cancel 可组织请求顺序，但不会把多个文件操作自动变成文件系统事务或业务原子操作。

取消与超时存在竞态
   目标可能尚未开始、正在完成或已经完成。Timeout CQE、原请求 CQE 和 cancel CQE 都要由状态机去重和收束。

能力必须探测
   Opcode、flag、fixed resource 和安全限制持续演进。程序应根据 feature/probe 结果选择能力，并提供降级路径。

Teardown 必须先收束请求
   停止新提交，终止 multishot、poll 和 timeout，持续消费 CQE，注销 fixed resources，最后关闭 ring fd。

关键路径
--------

创建与发布请求：

::

   io_uring_setup
   → 取得 ring fd、entries 和 features
   → mmap SQ / CQ / SQE
   → 取得空闲 SQE
   → 填写 opcode、参数和 user_data
   → 把 SQE 索引加入 SQ array
   → release 发布 SQ tail
   → io_uring_enter 或 SQPOLL 触发消费

完成请求：

::

   内核消费 SQE
   → 建立内部 request 与资源引用
   → 快速执行 / 原生异步 / io-wq
   → VFS、网络或设备完成
   → 填写 CQE
   → release 发布 CQ tail
   → 用户 acquire 读取 CQE
   → 处理 res 与 flags
   → 推进 CQ head
   → 释放终结请求资源

Fixed file 生命周期：

::

   register files
   → ring 持有 struct file 引用
   → SQE 使用 fixed-file 索引
   → 请求绕过普通 fdtable lookup
   → 更新或注销前等待使用者结束
   → 释放 ring 持有的引用

安全关闭：

::

   标记 stopping
   → 拒绝新 SQE
   → cancel multishot / poll / timeout / 普通请求
   → 持续 reap CQE
   → 确认 token 全部终结
   → unregister buffers 和 files
   → 解除业务对象引用
   → close ring fd

概念辨析
--------

* **SQE 被消费与请求完成**：SQE 槽位可在内核消费后复用，buffer 和业务对象仍需等待终结 CQE。
* **``io_uring_enter`` 返回与 CQE 结果**：前者描述 ring 入口动作；后者描述具体请求结果。
* **Registered buffer 与 zero-copy**：注册减少重复准备，不保证文件系统、协议和设备路径完全无复制。
* **SQPOLL 与 IOPOLL**：前者减少提交系统调用，后者轮询底层完成。
* **Link 顺序与事务原子性**：Link 表达依赖与失败传播，不提供跨操作事务提交。
* **关闭 ring 与业务资源安全**：内核会清理 ring，但用户对象必须先通过 CQE 和在途计数证明不再被引用。

本章结论
--------

``io_uring`` 把 I/O 交互改造成共享的提交与完成队列协议。它的正确性依赖内存顺序、请求身份、有限队列、资源引用和终结 CQE，而具体数据路径仍由文件系统、网络和设备决定。
