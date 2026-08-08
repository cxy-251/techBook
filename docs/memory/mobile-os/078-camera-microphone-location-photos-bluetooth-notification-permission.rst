第078章：Camera, Microphone, Location, Photos, Bluetooth, Notification Permission
================================================================================

核心知识点
----------

* 移动端权限把传感器、位置、媒体库、附近环境和用户注意力包装成可授权、可撤销、可审计的系统能力。
* 权限请求必须先按风险分类：Camera / Microphone 属于实时采集；Location 属于位置与轨迹；Photos 属于用户内容；Bluetooth / Nearby Devices 属于环境感知；Notification 属于注意力控制。
* 授权状态只是入口条件。系统服务仍会继续检查前后台状态、设备占用、全局隐私开关、功耗策略、通知渠道、定位精度和用户当前设置。
* Camera / Microphone 的关键额外状态是硬件占用和持续采集语义。有权限仍可能因为设备被占用、后台策略、隐私开关或 session 配置失败而不可用。
* Location 至少包含“前台 / 后台”和“精确 / 近似”两个维度，还叠加全局定位开关、采样策略和功耗预算。持续后台定位必须有更强的用户可见理由。
* Photos / Media Library 应优先使用最小授权。单项 picker、有限图库或系统选择器比整库枚举暴露更少数据。
* Bluetooth 扫描可以推断附近设备、配件关系甚至位置，因此扫描与连接通常都进入隐私和附近设备策略。
* Notification 权限控制的是用户注意力；即使总授权存在，channel、category、Focus、摘要、静默状态或系统设置仍可能改变实际展示结果。
* 权限状态不是永久常量：用户可撤销、系统可自动收回、一次性授权会过期，App 必须在每次敏感操作前重新确认当前状态并支持降级。

关键路径
--------

通用敏感能力路径是：

``用户触发功能 → App 检查当前授权 → 必要时请求系统 Prompt → Framework API → IPC → Service 重新检查 Identity / Permission / Lifecycle / Policy → Hardware or User Data → Result / Error``

Camera / Microphone：

``App → Camera / Audio Framework → Permission → CameraService / AudioService → Resource Arbitration → HAL / Driver → Sensor / Codec → Buffer``

Location：

``App → Location Framework → Permission + Precision + Foreground/Background Policy → Location Service → Provider Fusion → GNSS / Wi-Fi / Cell / Sensors → Location Result``

Photos：

``App → Photo / Document Picker or Library API → User Selection / Library Grant → System Media Service → Scoped Asset Result``

Notification：

``App → Notification API → Authorization + Channel / Category / Focus Policy → System UI → Lock Screen / Banner / Notification Center``

概念辨析
--------

* **Permission Granted 与 Resource Available**：已授权只表示允许请求；设备占用、后台限制、系统总开关仍可让调用失败。
* **Precise Location 与 Background Location**：精度描述“返回多精确”；后台描述“界面不可见时能否继续访问”，是两个独立维度。
* **Full Library Access 与 Picker Access**：完整权限允许枚举较大数据面；picker 把用户一次选择转成最小数据能力。
* **Bluetooth Permission 与 Location Permission**：蓝牙扫描可能具备位置推断风险，但现代平台会逐步拆分附近设备和定位权限，不能简单等同。
* **Notification Authorization 与 Delivery**：授权允许系统接受通知请求；真正是否展示还取决于系统通知策略和用户设置。

本章结论
--------

分析敏感能力时，不要停在“权限开没开”。正确顺序是“能力类型 → 当前授权范围 → 生命周期 → 服务端策略 → 资源状态 → 用户设置 → 实际结果”。移动 OS 通过细粒度授权和服务端二次检查，把一次用户同意限制在具体能力、具体时间和具体数据范围内。