第070章：Android Binder Service Access Path
===========================================

核心知识点
----------

* Android App 看到的是本地 Java / Kotlin API，真正跨进程执行由 Binder 把 manager 调用转换成 transaction。
* ``Context.getSystemService`` 返回 framework manager。Manager 负责 SDK 级参数整理、兼容适配、异常转换，并持有或查找远程 Binder 接口。
* Binder proxy 位于客户端，负责把方法参数写入 Parcel 并调用 ``transact``；Binder stub 位于服务端，负责解包 transaction、分发到真实 service object 并写回 reply。
* ``ServiceManager`` 解决服务发现：服务端以稳定 service name 注册 Binder object，客户端按名字取得 Binder handle。服务发现成功不等于具体方法调用已经获得授权。
* ``system_server`` 主要承载 Java system services，例如 Activity / Package / Window / Power / Location；图形、音频、相机、媒体等低延迟或硬件近端能力常由 native service 承载。
* Binder driver 在内核中维护跨进程引用、transaction 队列、线程唤醒和死亡通知；真正的权限、AppOps、前后台状态和资源仲裁仍由服务端完成。
* Android 的 Binder 也延伸到 system / vendor / HAL 边界，现代设备越来越多使用 Stable AIDL / AIDL HAL 维持接口稳定性。

关键路径
--------

典型访问链：

``App → Context.getSystemService → Framework Manager → typed Binder proxy → Binder driver → Stub / service object → policy check → native service / HAL → Driver``

服务发现链：

``service process addService(name, Binder object) → ServiceManager registry → client getService(name) → Binder handle``

相机路径可压缩为：

``CameraManager → ICameraService proxy → Binder → CameraService → permission/AppOps/foreground/resource check → camera provider / HAL → callback``

概念辨析
--------

* **Manager class ≠ Binder service**：Manager 是 App 进程中的 SDK 门面，Binder service 才是远程能力所有者。
* **ServiceManager ≠ permission manager**：它负责注册与发现，业务权限仍在目标服务 method 内检查。
* **Proxy / Stub ≠ service logic**：它们负责跨进程编码与分发，真实策略位于 service implementation。
* **system_server service ≠ native service**：前者偏控制面与全局策略，后者常靠近高吞吐数据面和硬件链路。
* **Binder handle available ≠ hardware available**：拿到服务引用后，仍可能因权限、资源占用、HAL 状态或设备故障失败。

本章结论
--------

阅读 Android 系统能力时，稳定顺序是先找到 framework manager，再找到它持有的 Binder 接口和 service name，随后进入服务端实现，最后继续追踪 HAL / vendor / driver。Binder 是 Android 服务路径的骨架，资源所有权和策略判断则始终落在目标服务端。
