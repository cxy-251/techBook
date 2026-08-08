第023章：System Partitions, Recovery, OTA Update, Rollback Protection
=====================================================================

核心知识点
----------

* 手机 OTA 的主问题不是“下载一个更新包”，而是把新系统安全写入受保护分区，并让 bootloader、Verified Boot、kernel 与用户空间确认新版本可启动且可继续使用用户数据。
* Android 分区按责任拆分系统代码、硬件适配、恢复入口、用户数据和验证元数据。``boot/init_boot``、``system``、``vendor``、``product``、``userdata``、``vbmeta`` 等对象承担不同升级与验证职责。
* A/B seamless update 使用两套可启动 slot。当前系统运行在 active slot，更新组件把新版本写入 inactive slot，重启后再由 bootloader 尝试新 slot。
* A/B slot 的关键状态是 active、bootable、successful。写入完成不等于更新完成，新 slot 只有通过真实启动和用户空间健康确认后才应被标记 successful。
* Recovery Environment 是主系统外的修复入口，负责安装、恢复、factory reset、日志收集或与外部主机工具协作。它的权限高于普通 App 和 framework。
* Android ``vendor`` 边界把通用 framework 与设备特定 HAL、vendor daemon、firmware 依赖和硬件配置分开；Treble/VINTF 用接口与兼容矩阵约束 system/vendor 组合。
* ``vbmeta``、hashtree 和 ``dm-verity`` 让 OTA 后的新分区仍处在 Verified Boot 信任链中；目标 slot 写完后必须通过与新镜像一致的完整性校验。
* Rollback protection 限制设备回退到低于已接受安全版本的旧镜像，防止通过降级重新引入已修复漏洞。
* OTA 可靠性依赖“写新版本时保留可工作的旧版本”。断电、写入失败、post-install 失败或首次启动失败时，系统必须能回退旧 slot 或进入恢复路径。
* 正常 OTA 应尽量保留 ``userdata``；factory reset 则明确改变用户数据状态。系统镜像恢复与用户数据可恢复不是同一个问题。

关键路径
--------

A/B OTA：

::

   running slot A
   → download / stream OTA payload
   → update_engine writes inactive slot B
   → verify target partitions
   → mark B active and bootable
   → reboot
   → bootloader tries B
   → userspace health check
   → mark B successful

失败回退：

::

   new slot boot attempt
   → kernel / init / system health failure
   → retry counter or slot state changes
   → bootloader selects old successful slot
   → old system remains usable

恢复入口：

::

   boot failure / user recovery request / host tool
   → bootloader selects recovery / fastboot / DFU path
   → verify repair image or command
   → rewrite partitions / factory reset / collect diagnostics
   → reboot into verified system

概念辨析
--------

* **分区布局与 slot**：分区说明数据职责，slot 表示可启动版本集合；A/B 设备会让关键分区同时存在 A/B 两套实例。
* **active 与 successful**：active 只是下一次优先尝试，successful 表示该 slot 已被用户空间确认健康。
* **Recovery 与 OTA client**：OTA client 在正常系统中协调下载和写入，Recovery 是主系统不可用时的高权限修复环境。
* **system 与 vendor**：system 偏平台通用实现，vendor 偏设备硬件适配；二者能否组合运行要满足接口兼容约束。
* **Rollback 与普通回退**：启动失败回退到旧 successful slot 是可靠性机制；anti-rollback 阻止回到低于安全版本下限的旧软件，是安全机制。

本章结论
--------

移动系统更新是“分区写入、启动选择、完整性验证、健康确认、失败恢复、版本防回退”组成的事务。分析 OTA 问题时，应把 update_engine、slot metadata、bootloader、Verified Boot、VINTF、Recovery 和 userdata 分开定位；只有新 slot 被验证并成功启动后，一次 OTA 才真正完成。