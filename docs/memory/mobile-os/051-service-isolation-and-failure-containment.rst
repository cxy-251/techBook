第051章：Service Isolation and Failure Containment
==================================================

核心知识点
----------

* Service Isolation 的目标是限制 blast radius：一个组件失效时，把崩溃、权限、资源和性能影响控制在最小边界内。
* App、system service、native daemon/HAL、kernel/driver 处在不同故障层级；故障位置越低，潜在影响范围越大。
* App crash 通常只影响当前应用；独立 service crash 会影响所有依赖该能力的 client；``system_server`` 故障接近系统级；kernel fault 可能导致整机冻结或重启。
* Privilege Separation 要让每个服务只拥有完成职责所需权限，避免相机、媒体、图形、网络等能力集中在单一高权限进程。
* 服务必须拥有资源回收权，不能只依赖 client 主动释放。client 进程死亡后，应通过 Binder death、XPC invalidation 或监督机制回收 session、buffer、wakelock 和设备所有权。
* 高负载工作适合独立服务或硬件队列隔离，以便单独调度 CPU/GPU/ISP/codec、限制内存带宽并执行温控降级。
* 服务重启通常只能恢复“可重建状态”；旧 session、in-flight buffer 和事务上下文通常失效，需要 client 重新建立。

关键路径
--------

故障定位顺序：

#. 先看影响范围：单 App、单能力、系统 UI 还是整机。
#. 找到最近的进程/IPC 边界，确认是谁崩溃、超时或失联。
#. 确认故障时谁持有 camera/session/buffer/fd/token 等资源。
#. 检查服务监督者是否重启进程，以及旧资源是否被完整释放。
#. client 收到 disconnected/dead-object/invalidation 后，关闭旧状态并重新绑定。
#. 若故障穿过所有进程边界并出现 panic/freeze，再进入 kernel/driver/硬件层分析。

典型恢复链：

``Client death → Service detects disconnect → Release resource → Restart/keep service → Client reconnects → Recreate session``

概念辨析
--------

``Isolation`` 与 ``Recovery``：isolation 限制故障范围；recovery 负责故障发生后的状态重建，两者缺一不可。

``Service crash`` 与 ``Kernel fault``：service crash 仍受进程边界约束；kernel fault 会破坏所有用户态服务共同依赖的底层资源管理。

``Privilege separation`` 与 ``Process separation``：不同进程不代表权限已经最小化；还需限制 UID/domain/entitlement、可访问对象和 IPC 接口。

``Restart`` 与 ``Resume``：服务重启只是进程重新出现，旧会话通常已失效，client 必须按协议重新建立资源上下文。

本章结论
--------

移动系统可靠性取决于“故障能否停在清晰边界”和“边界失效后资源能否被收束”。排障时应先按影响范围定位 App、service、system_server 或 kernel 层级，再检查资源所有权、死亡通知和重建路径。