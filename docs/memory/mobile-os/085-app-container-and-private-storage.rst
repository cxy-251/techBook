第085章：App Container and Private Storage
==========================================

核心知识点
----------

* App Container 是移动平台为已安装应用建立的默认私有文件边界，由应用身份、安装记录、文件权限、sandbox、备份和清理策略共同定义。
* 私有存储中的长期状态、缓存和临时文件必须分开：长期数据需要稳定保留，缓存允许系统回收，临时数据只服务当前任务。
* Android 私有存储主要围绕 package、UID、data directory、``filesDir``、database、``cacheDir`` 与 app-specific external directory 组织。
* Apple 私有存储主要围绕 bundle identity、data container、``Documents``、``Library/Application Support``、``Caches``、``tmp`` 和 App Group container 组织。
* 可执行代码与可变数据必须分离：代码随版本更新替换，数据目录承担数据库、设置、索引和业务状态的延续。
* App 更新通常保留数据容器并由应用执行 schema migration；卸载或“清除数据”通常清除 App 私有数据；恢复结果还取决于备份与签名/身份连续性。
* 跨主 App、extension、widget 或相关 App 共享数据时，应使用平台认可的共享容器、provider 或服务边界，不能直接依赖另一进程的私有路径。

关键路径
--------

::

   App write
     → classify persistent / cache / temporary
     → Framework directory API
     → App identity / sandbox
     → private container
     → filesystem write
     → backup / cleanup / migration policy

目录选择的稳定判断：

::

   用户或业务事实 → persistent data directory
   可重新下载/计算 → cache directory
   当前导入/导出中间态 → temporary directory
   用户明确导出成果 → user-visible shared/document location

概念辨析
--------

* **Container vs directory path**：container 是身份与策略边界；路径只是当前实现中的位置，真实路径可能因多用户、迁移或重装变化。
* **Persistent vs cache vs temporary**：区别来自生命周期承诺，而不是文件扩展名。
* **Internal app data vs external app-specific data**：二者都属于 App 自身；后者可能受可移除介质和外部存储可用性影响。
* **Private storage vs shared container**：私有容器默认只属于单一 App 身份；共享容器要求额外签名、entitlement、provider 或受控 IPC 关系。
* **Update vs reinstall**：更新强调身份连续并保留数据；卸载重装通常重新建立容器，是否恢复取决于平台备份和账号同步。

本章结论
--------

App Container 是移动应用本地状态的默认所有权边界。目录设计要先按生命周期分类，再让平台的身份、备份、清理和迁移机制接管后续行为；用户成果不应被困在可随 App 消失的私有目录中。