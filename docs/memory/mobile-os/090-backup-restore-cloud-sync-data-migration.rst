第090章：Backup, Restore, Cloud Sync, Data Migration
===================================================

核心知识点
----------

* 数据连续性由四类机制共同完成：Backup 保存某个时间点的 App/设备状态，Restore 把它放回新环境，Cloud Sync 持续同步逻辑数据，Data Migration 让旧格式数据被新版本继续读取。
* 平台备份面向文件、数据库、偏好设置和规则，不理解业务语义；多设备冲突、账号状态和业务一致性仍由 App 与服务端负责。
* Restore 常发生在 App 首次可用之前或首次启动附近；恢复后的本地文件仍需通过 schema migration、账号验证、密钥检查和远端同步才能变成当前可用状态。
* 数据应区分为必须保留的用户数据、可云同步数据、可重建缓存、设备绑定数据和密钥材料；不同类别不能使用同一恢复策略。
* Android Auto Backup / device-to-device transfer 受备份规则、配额、系统版本与账号影响；可重建缓存和设备 token 通常应排除。
* Apple 需要区分 iCloud Backup、iCloud Drive、CloudKit、Keychain 同步等不同路径；已经由同步服务持续维护的数据不等同于普通整机备份数据。
* Schema migration 必须有版本号、可重复执行或明确的事务边界，并处理旧版本、失败重试、部分升级和回滚后的兼容。
* 加密数据恢复必须同时恢复或重新建立可用密钥；设备绑定密钥、硬件密钥或认证状态无法仅靠复制数据库文件恢复。

关键路径
--------

::

   Old device App data
     → backup rules / cloud sync
     → platform account / encrypted transport
     → new device installs App
     → platform restore
     → App first launch
     → schema migration
     → key/account validation
     → cloud reconciliation
     → usable state

数据分类：

::

   user-created facts → backup and/or business sync
   cross-device logical data → sync
   cache/index → rebuild
   device token/device id → reissue
   encrypted DB → restore data + validate key availability

概念辨析
--------

* **Backup vs sync**：备份是时间点恢复；同步是多端持续收敛，冲突模型不同。
* **Restore vs migration**：restore 把旧数据放回本地；migration 把旧格式转换成当前版本可理解格式。
* **User data vs cache**：用户数据丢失是数据损失；缓存丢失只应导致重建成本。
* **Cloud storage vs platform backup**：业务云、CloudKit、iCloud Drive 等同步服务拥有业务/文档语义；平台备份主要处理容器状态。
* **File restored vs feature restored**：文件回来不代表功能已恢复；账号、权限、密钥、push token 和服务器状态可能需要重新建立。

本章结论
--------

换机和重装不是一次“复制文件”，而是恢复本地状态、升级数据格式、重建密钥/账号能力并与云端重新收敛的组合过程。设计数据层时必须提前规定每类数据由谁恢复、从哪里恢复以及恢复失败时如何降级。