第045章：System Service as Hardware Proxy
==========================================

核心知识点
----------

* Hardware Proxy 指系统服务代表 App 访问真实硬件；App 请求的是能力，系统服务持有真实设备所有权。
* 服务代理至少承担四类责任：识别调用者、检查授权与生命周期、维护资源占用、把语义请求翻译成 HAL / driver 可执行操作。
* Camera 更接近独占 session；Audio 同时包含可混音数据流和受控 route；Location / Sensor 更接近多客户端订阅与合并；Display 由窗口、layer、刷新率与亮度策略共同控制。
* 服务侧必须保存 client token、session、surface/buffer、前后台状态、权限结果和底层设备状态，不能只转发函数参数。
* 服务是安全、稳定性和兼容性边界：权限在这里集中执行，硬件差异在这里被吸收，底层故障在这里被转换成统一结果。
* 多 App 并发时，服务决定独占、共享、聚合、混音、排队、抢占、超时和资源释放。

关键路径
--------

通用硬件代理路径：

``App 意图 → Framework API → IPC → System Service → 权限/策略/资源检查 → HAL/Driver → Hardware``

返回路径：

``Hardware event / buffer / error → Driver/HAL → Service state → Framework callback → App``

视频通话场景中：

#. App 请求 camera preview、audio、location 等能力。
#. 服务确认调用者身份、用户授权、前台状态和设备可用性。
#. Camera 请求变成 stream/session/buffer；Audio 请求变成 route/focus/stream；Location 请求变成 provider/subscription。
#. HAL 或 driver 执行底层设备操作。
#. 服务根据 client 生命周期、温控、电源和并发变化持续调整资源状态。
#. App 退出或连接失效时，服务负责关闭 session、释放 buffer 和撤销所有权。

概念辨析
--------

``Hardware Proxy`` 与 ``HAL``：System Service 负责平台语义、权限和全局资源状态；HAL 负责把标准硬件接口适配到厂商实现。

``Capability`` 与 ``Device``：App 获得的是被授权的能力抽象；系统持有实际 camera、microphone、GNSS、display 等设备资源。

``Exclusive Resource`` 与 ``Shared Resource``：前者围绕唯一或受限 owner 管理；后者围绕订阅、合并、缓存和限速管理。

``API Error`` 与 ``Hardware Error``：API 层错误是服务翻译后的稳定语义；硬件错误只是底层原因之一。

本章结论
--------

系统服务把 App 的高层意图转换为受控硬件操作。排查硬件能力时，应先确认服务是否授予资源和建立正确 session，再进入 HAL、driver 和硬件；直接从 App API 跳到设备驱动会丢失最关键的权限、状态与仲裁边界。