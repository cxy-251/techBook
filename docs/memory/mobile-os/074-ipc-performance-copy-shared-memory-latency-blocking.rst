第074章：IPC Performance Copy, Shared Memory, Latency, Blocking
==============================================================

核心知识点
----------

* IPC latency 是端到端成本，包含序列化、内核进入、句柄处理、目标线程唤醒、队列等待、服务端执行、reply / callback 派发，而不只是一次系统调用成本。
* 小控制数据适合直接放进 IPC message；大图像、音频、视频、tensor 应使用共享内存或系统 buffer，IPC 只传 handle、metadata、fence 和状态。
* 所谓 zero-copy 通常是避免每次完整复制 payload，并不意味着没有映射、同步、引用计数、cache coherency 和 fence 成本。
* Binder transaction buffer 有大小限制。大列表、bitmap、byte array 和复杂 Parcelable 不应一次塞进 Parcel，应改成分页、file descriptor、SharedMemory、AHardwareBuffer、Surface 或内容 URI。
* Apple Mach / XPC 同样存在消息编码、port right、队列等待和大对象传输成本；大媒体数据通常通过共享资源对象而不是普通 XPC message 逐帧复制。
* 同步 IPC 放在主线程会把远端服务排队、锁、HAL 等待全部转换成用户可见卡顿，严重时触发 ANR 或 watchdog。
* 高频 IPC 可能造成调用风暴、Binder thread pool / daemon queue 拥塞和 backpressure；应优先批处理、缓存、事件合并和异步通知。

关键路径
--------

延迟拆分：

``caller encode → IPC/kernel mediation → target queue → service thread → policy/lock/resource wait → reply encode → caller wakeup / callback queue``

数据选择：

``small control data → Parcel / XPC message``

``large continuous data → shared memory / Surface / AHardwareBuffer / IOSurface / FD + IPC control message``

实时路径如输入、图形、相机和音频必须把 IPC 开销纳入 frame deadline / buffer deadline；控制消息可以跨进程，媒体 payload 应尽量走共享 buffer。

概念辨析
--------

* **System call cost ≠ IPC latency**：服务端排队和执行通常比 trap 本身更重要。
* **Shared memory ≠ free communication**：共享内存减少复制，但增加同步、所有权和生命周期责任。
* **Large Parcel ≠ high-bandwidth channel**：Parcel 适合控制数据，不适合连续大媒体流。
* **Asynchronous ≠ no cost**：异步减少调用线程阻塞，但仍有队列、回调和背压问题。
* **More IPC concurrency ≠ more throughput**：超过服务端线程池和资源容量后，只会增加排队、锁竞争和超时。

本章结论
--------

IPC 性能优化的核心不是消灭跨进程调用，而是让控制语义走小消息，让大数据走共享 buffer，让主线程避免同步远程等待，并控制调用频率和服务端并发。定位卡顿时，应逐段拆开端到端延迟，而不是只归因于“Binder/XPC 很慢”。
