第071章：Binder Driver, Service Manager, AIDL, Parcelable
========================================================

核心知识点
----------

* Binder driver 是 Android Binder IPC 的内核中介，管理 Binder node / reference、transaction buffer、线程唤醒、等待队列和死亡通知。
* 同步 Binder transaction 会阻塞调用线程，直到目标服务处理完成并返回 reply；``oneway`` 调用只提交请求，不等待同步结果。
* ServiceManager 负责 service name 到 Binder handle 的映射；历史上还存在 ``hwservicemanager``、``vndservicemanager`` 等不同命名空间，用于 framework、HAL、vendor 边界隔离。
* AIDL 定义跨进程接口契约，并生成客户端 Proxy 与服务端 Stub。Stable AIDL 进一步把接口版本和 system / vendor 兼容性纳入构建约束。
* Parcel 是 Binder 的高性能运行期数据容器；Parcelable 定义结构化对象如何 flatten / unflatten。Parcel 可携带值、IBinder 引用和 file descriptor。
* Binder thread pool 决定服务端能同时处理多少 transaction。阻塞调用、嵌套调用、锁顺序错误会导致线程池耗尽、优先级反转和死锁。
* Binder IPC 的安全边界来自内核提供的 caller identity 加服务端检查；Binder driver 传递身份，service 负责 permission / AppOps / resource policy。

关键路径
--------

同步 transaction：

``Proxy writes Parcel → transact() → Binder driver resolves handle → target process/thread wakeup → Stub.onTransact() → service method → reply Parcel → caller wakeup``

AIDL 路径：

``.aidl contract → generated Proxy / Stub → Parcel encoding → Binder transaction → service implementation``

服务发现与 HAL 判断应先确认服务注册在哪个命名空间，再确认接口是 framework Binder、Stable AIDL HAL、HIDL 历史接口还是 vendor 私有服务。

概念辨析
--------

* **Binder driver ≠ ServiceManager**：driver 负责传输和引用管理；ServiceManager 负责名字发现。
* **AIDL ≠ Binder itself**：AIDL 是接口描述与代码生成层，底层传输仍由 Binder 完成。
* **Parcel ≠ Parcelable**：Parcel 是消息容器；Parcelable 是对象编码协议。
* **Synchronous Binder ≠ main-thread safe**：接口同步只说明语义，不保证服务快速，主线程同步调用可能直接导致 ANR。
* **Stable AIDL ≠ 永久不变**：它允许接口演进，但要求版本化、兼容和稳定类型约束。

本章结论
--------

Binder 路径应分成四层理解：ServiceManager 负责发现，AIDL 负责接口契约，Parcel / Parcelable 负责参数封装，Binder driver 负责跨进程 transaction 与引用生命周期。性能和可靠性问题最终常落在同步阻塞、线程池、数据大小和服务端状态上。
