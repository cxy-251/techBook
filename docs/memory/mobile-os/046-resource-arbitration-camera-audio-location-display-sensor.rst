第046章：Resource Arbitration Camera, Audio, Location, Display, Sensor
======================================================================

核心知识点
----------

* Resource Arbitration 是系统服务在多个客户端争用同一系统资源时，决定接受、排队、合并、降级、抢占或拒绝的过程。
* 独占资源围绕 owner 管理，共享资源围绕 subscriber 管理。Camera、录音输入和关键 audio route 更接近独占；Location、Sensor、Network、Display 更接近共享或聚合。
* 仲裁必须同时考虑 client identity、permission、foreground state、用户可见性、设备状态、电源、温控和当前资源占用。
* 前台交互、通话、录音、系统 UI 等用户可见任务通常具有更高优先级；后台请求更容易被限频、延迟或降级。
* 服务要记录 owner / subscriber 与 token、callback、session 的绑定关系，才能在 client 死亡或连接失效时正确清理资源。
* 抢占不是只把旧 client 踢掉，还要向旧 client 返回 interruption/error，并为新 client 建立完整资源状态。
* 超时、主动释放、进程死亡、权限撤销和服务重启都属于资源 lease 的终止条件。

关键路径
--------

独占资源路径：

``Request → Service policy → Current owner check → Grant / Preempt / Reject → Session → Release``

共享资源路径：

``Subscribe → Service merges requirements → Hardware/provider runs once → Service filters/batches → Multiple callbacks``

以短视频 App 为例：

#. CameraService 检查 camera owner、权限和前台优先级。
#. Audio service 处理录音输入、播放焦点和 route 冲突。
#. Location service 把短视频地理标签请求与导航 App 的高精度请求合并。
#. Sensor service 根据最高采样需求运行底层传感器，并按各客户端要求分发。
#. Display service 在多个 layer、刷新率偏好和热限制之间选择可执行显示策略。
#. client 退出或失效后，服务通过 token/death notification 清理所有权与订阅。

概念辨析
--------

``Owner`` 与 ``Subscriber``：owner 表示资源控制权；subscriber 表示共享数据或状态的订阅关系。

``Priority`` 与 ``Permission``：permission 决定有没有资格进入仲裁；priority 决定多个合格请求如何排序。

``Preemption`` 与 ``Release``：preemption 是系统主动收回控制权；release 是当前 client 主动或生命周期驱动地归还资源。

``Resource Busy`` 与 ``Permission Denied``：前者表示资源状态冲突；后者表示调用者资格不成立，修复路径完全不同。

本章结论
--------

移动资源的正确所有权位于系统服务，而不位于 App。分析资源冲突时，应先判断资源是独占还是共享，再确认当前 owner/subscribers、优先级和终止条件，最后才进入 HAL 或硬件层。