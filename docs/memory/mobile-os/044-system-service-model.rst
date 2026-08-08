第044章：System Service Model
==============================

核心知识点
----------

* System Service 是移动 OS 的能力承载单元：它同时持有调用者身份、权限结果、客户端列表、资源状态和平台策略。
* App 面向 Framework API 编程，真正的全局状态和资源所有权位于 service / daemon 侧；Framework manager 只是稳定的客户端入口。
* 服务层适合承担全局仲裁，因为它同时知道前后台状态、用户授权、电源策略、硬件可用性和其他客户端的占用情况。
* Service process、daemon、manager、controller 职责不同：manager 面向 App，service/daemon 持有权威状态，controller 管理内部状态机。
* 服务注册表把“服务位置”与“服务能力名称”分离。客户端按稳定名字取得 handle/port，再通过 IPC 调用真正后端。
* 服务必须把底层 ``busy``、``timeout``、``not available``、权限拒绝等结果翻译成稳定 API 错误或异步回调。
* 系统服务不是纯 RPC 函数集合，而是跨多次请求维护状态、会话和资源生命周期的长期控制面。

关键路径
--------

典型能力路径：

``App → Framework Manager → IPC → System Service → Policy / State → HAL / Daemon / Driver → Hardware``

以定位请求为例：

#. App 通过公开 API 表达精度、频率和回调需求。
#. Framework manager 整理参数并建立远端调用。
#. IPC 把调用者真实身份带到服务端。
#. 服务检查权限、前后台、电源策略、provider 状态和缓存。
#. 服务登记 client/request，必要时启动或调整底层定位来源。
#. 结果经服务过滤、降级或聚合后回调 App。
#. client 退出、权限撤销或服务重启时，服务清理状态并释放资源。

概念辨析
--------

``Framework API`` 与 ``System Service``：前者是公开契约和客户端门面，后者是权威状态与策略执行者。

``Service process`` 与 ``daemon``：前者强调服务运行和隔离的位置；后者强调后台长期或按需运行的进程形态。二者可以重叠。

``Manager`` 与 ``Controller``：manager 通常位于客户端侧包装公开 API；controller 通常位于服务内部管理 session、provider、policy 或状态机。

``Service Registry`` 与 ``Service Backend``：registry 负责发现与取得引用，backend 才执行权限、状态更新和资源操作。

本章结论
--------

移动 OS 的系统能力不是由 App 直接拥有，而是由系统服务集中代理和管理。分析任何系统能力时，应先找到 Framework 入口，再找到 IPC 后的权威 service，最后沿 service 持有的状态、策略和底层资源继续追踪。