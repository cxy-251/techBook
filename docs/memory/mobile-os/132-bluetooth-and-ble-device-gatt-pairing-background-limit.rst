第132章：Bluetooth and BLE Device, GATT, Pairing, Background Limit
===================================================================

核心知识点
----------

* Bluetooth 能力链应按 ``App API → Permission/Lifecycle → System Bluetooth Service → Protocol Stack → Controller → Peripheral`` 理解，App 不直接拥有无线控制器。
* Bluetooth Classic 更适合持续连接、音频和成熟 profile；BLE 更适合低功耗发现、短数据交换、传感器、门锁、Beacon 与附近设备能力。
* BLE discovery 的基本模型是 peripheral advertising、central scanning。App 看到的“发现设备”只是系统在某个扫描窗口中返回符合过滤条件的广播结果。
* Scan window、scan filter、duplicate handling、advertising interval 都会影响发现延迟、功耗和结果数量。持续无过滤扫描是平台重点限制对象。
* GATT 把 BLE 外设组织成 attribute database：service 表示一组能力，characteristic 表示具体数据值，descriptor 补充属性与控制信息。
* Characteristic 常见操作是 read、write、notify、indicate；业务协议应建立在这些原语之上，而不是把 GATT 本身误认为完整应用协议。
* Pairing 用于建立当前连接的信任关系，bonding 保存长期密钥以便未来重连；encrypted link、MITM protection、认证方式属于连接安全层。
* 能扫描到设备不代表能读取敏感 characteristic；连接、加密、配对、GATT permission 与应用层认证是不同控制点。
* Android 需要同时理解 Nearby Devices/Bluetooth permission、Bluetooth service、native stack、HAL/controller 与后台扫描限制。
* Apple Core Bluetooth 以 central/peripheral、service/characteristic、state restoration、background mode 等抽象能力；系统仍可合并扫描、限制后台回调和调度 radio。
* BLE 广播、地址、RSSI、设备出现时间能推断位置和行为，因此附近设备扫描本身属于隐私能力，不只是网络功能。
* 后台 Bluetooth 的稳定原则是“系统保留必要关系，而不是允许 App 持续自由运行”：连接事件、state restoration 或受控 background mode 由平台决定唤醒与恢复时机。

关键路径
--------

BLE 门锁访问：

::

   App starts scan
   → permission + lifecycle check
   → system Bluetooth service
   → controller scan window
   → advertising packet
   → filtered scan result
   → connect
   → discover GATT services/characteristics
   → pairing/encryption if required
   → write command
   → notify/indicate status
   → disconnect or background restoration policy

长期信任路径：

::

   first connection
   → pairing method
   → key generation / authentication
   → encrypted link
   → bonding stores reusable keys
   → later reconnect
   → verify stored trust + current authorization

概念辨析
--------

* **Classic 与 BLE**：Classic 偏持续 profile 与媒体/外设，BLE 偏低功耗发现和短 attribute 数据交换。
* **Advertising 与 connection**：广播用于无连接发现，连接后才进入稳定双向 GATT 会话。
* **Service 与 characteristic**：service 是能力集合，characteristic 才是可读写或订阅的具体值。
* **Pairing 与 bonding**：pairing 建立当前安全关系，bonding 把密钥持久化供后续连接使用。
* **Bluetooth permission 与 GATT authorization**：平台允许 App 使用附近设备能力，不代表外设一定允许访问某个敏感 attribute。

本章结论
--------

BLE 的稳定模型是 ``Discover → Connect → Discover GATT → Establish Trust → Exchange Attributes → Background/Power Policy``。移动 OS 把无线控制、附近设备隐私、连接密钥和后台调度分开管理，因此“扫不到、连不上、写失败、后台断开”分别对应不同系统边界。