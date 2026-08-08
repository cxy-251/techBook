第069章：IPC Concepts Handle, Message, Transaction, Port, Object Reference
========================================================================

核心知识点
----------

* IPC handle 是客户端对远程能力的受控引用，常见形态包括 Binder handle / proxy、Mach port right、XPC endpoint / connection。
* 远程引用通常分三层：客户端语言对象、IPC runtime 可识别的句柄、服务端真实对象。客户端对象仍存在，并不代表远端对象仍然有效。
* 一次 IPC 调用本质上是 message / transaction，而不是普通函数跳转。消息需要携带目标、操作、参数、附带引用、调用上下文、回复路径和错误状态。
* Request / Reply 适合短操作；耗时能力通常使用异步 callback。Callback 本身也是一条反向 IPC 通道。
* Serialization 负责把当前地址空间中的值转成跨进程表示。Android 使用 Parcel / Parcelable，Mach message 可携带数据与 port right，XPC 用对象图和 connection 封装消息。
* 远程对象生命周期必须独立管理。Binder death recipient、Mach port right 生命周期、XPC interruption / invalidation 都用于处理远端消失和资源释放。
* Caller identity 不能依赖客户端自报字段，应优先使用 Binder UID / PID、Mach / XPC audit credential、代码签名和 entitlement 等系统提供事实。

关键路径
--------

``Framework manager → remote reference → encode request → IPC kernel/runtime → service object → decode request → policy / resource operation → reply or callback``

一个典型 session 模型是：先通过全局服务引用创建会话，再得到新的 session handle；后续控制、回调和释放都围绕该 session handle 展开。相机、音频、窗口和媒体 codec 都常采用这种二级能力引用方式。

概念辨析
--------

* **Handle ≠ memory pointer**：handle 代表访问远端对象的能力，不暴露服务端地址。
* **Message ≠ persistent format**：Parcel、Mach message、XPC message 服务运行期 IPC，不应被当作长期持久化 ABI。
* **Synchronous call ≠ cheap call**：同步远程调用会等待内核转发、目标线程、服务逻辑和 reply，成本远高于普通本地函数。
* **Callback ≠ local listener**：跨进程 callback 仍需要序列化、线程调度和远程引用生命周期管理。
* **Remote object lifetime ≠ local object lifetime**：本地 proxy 还在时，服务端对象可能已经死亡、重启或重新分配。

本章结论
--------

分析 IPC 时，先确定客户端持有什么远程能力引用，再还原 message / transaction 的请求与回复结构，最后检查序列化、调用者身份和远端对象生命周期。系统服务 API 的稳定性很大程度上取决于这些 IPC 抽象是否被正确设计。
