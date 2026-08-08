第068章：IPC as the Mobile OS Service Spine
===========================================

核心知识点
----------

* IPC 是移动 OS 的系统服务脊柱，用来连接彼此隔离的 App、Framework、System Service / Daemon、HAL 和 Driver。
* App 持有用户意图和业务状态；Framework 提供稳定 API；System Service 持有全局资源状态、权限策略和仲裁权；HAL / Driver 负责设备执行。
* IPC 传递的不只是参数，还包含远程对象引用、调用者身份、回调通道和错误状态，因此它同时支撑能力调用、安全检查和生命周期管理。
* System Service 必须在可信服务端重新做权限、前后台状态和资源占用检查，不能把 App 进程里的前置检查当作最终授权。
* 跨进程调用天然具有独立失败模型：远程对象死亡、服务重启、连接断开、超时和回调丢失都必须被客户端视为正常系统事件。
* 同进程调用只跨函数边界；IPC 还跨地址空间、线程调度和失败边界，因此有序列化、队列等待、阻塞和重入成本。

关键路径
--------

``App intent → Framework API → IPC proxy / endpoint → System Service / Daemon → identity & policy check → resource arbitration → HAL / Driver → Hardware``

返回路径为：

``Hardware / Service result → reply / callback → IPC → Framework → App``

以相机预览为例：App 调用相机 API，Framework 把请求转换成远程 transaction；相机服务读取 caller identity、权限、前台状态和设备占用；通过后才配置 HAL / Driver；设备结果通过 callback 返回 App。大图像数据通常走共享 buffer，IPC 主要传递控制消息和句柄。

概念辨析
--------

* **Framework API ≠ System Service**：前者是开发者可见接口，后者才是系统能力所有者和权威策略执行点。
* **Remote reference ≠ remote object itself**：客户端持有的是 Binder handle、Mach port / XPC endpoint 等受控能力引用，不是服务端内存对象。
* **API 调用成功返回 ≠ 硬件操作完成**：很多 IPC 只完成请求提交，真正结果由异步 callback 返回。
* **Permission granted ≠ resource available**：权限通过后仍可能因后台策略、资源被占用、设备关闭、温控或 HAL 故障失败。
* **IPC failure ≠ App bug**：服务死亡和连接失效是进程隔离带来的正常失败模式，客户端需要重连或重建 session。

本章结论
--------

理解移动系统能力时，应先把任何“本地 API 调用”还原成一条 IPC 能力链。IPC 让系统在保持进程隔离的同时集中执行身份校验、权限控制、资源仲裁和故障收束，是 App、Framework、Service 与硬件边界之间最重要的连接机制。
