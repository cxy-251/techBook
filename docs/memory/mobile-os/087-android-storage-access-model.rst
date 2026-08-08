第087章：Android Storage Access Model
=====================================

核心知识点
----------

* Android 存储模型按数据归属分为：internal app-specific、external app-specific、shared media、user-selected documents 与 all-files access。
* 内部私有目录依赖 package、UID、SELinux 与 App sandbox；普通 App 访问自己的 ``filesDir``、database、``cacheDir`` 不需要额外存储权限。
* 外部 app-specific directory 仍属于当前 App，卸载时通常清除；可移除介质不可用时其中数据也不可用。
* Scoped Storage 把“按路径遍历共享盘”收缩为“按数据类型和用户授权访问”；Android 10 开始成为主模型，Android 11 进一步收紧 legacy 路径。
* MediaStore 是图片、视频、音频和部分 Downloads 数据的系统集合入口；App 通过 ``ContentResolver``、URI 和文件描述符访问。
* Storage Access Framework 通过 ``ACTION_OPEN_DOCUMENT``、``ACTION_CREATE_DOCUMENT``、``ACTION_OPEN_DOCUMENT_TREE`` 把用户选择转换成 URI grant。
* Android 13 起媒体读取权限进一步拆分；宽泛的 ``MANAGE_EXTERNAL_STORAGE`` 只适合文件管理等核心功能，并受到平台政策约束。
* 现代 Android 存储问题应先检查系统版本、target SDK、数据类型、授权入口，再看路径；旧路径仍存在并不代表旧访问语义仍然成立。

关键路径
--------

::

   App data need
     → private or user-owned?
     → media or document?
     → choose filesDir / app-specific / MediaStore / SAF
     → permission or user selection
     → ContentResolver / Provider
     → URI / ParcelFileDescriptor
     → filesystem object

共享媒体：

::

   App → MediaStore collection → permission / ownership check
       → content URI → open/query/update → media file

用户文档：

::

   App → DocumentsUI / SAF → user selects object
       → URI grant → ContentResolver → fd/stream
       → optional takePersistableUriPermission

概念辨析
--------

* **Internal storage vs external app-specific storage**：两者都属于当前 App；后者位于共享存储介质上，但不等于公共文件。
* **Scoped storage vs legacy external storage**：前者按集合、归属和授权限制访问；后者依赖大范围路径权限，是兼容历史模型。
* **MediaStore vs SAF**：MediaStore 面向系统媒体集合；SAF 面向用户选择的普通文档、文件和目录树。
* **URI vs raw path**：URI 代表 provider 管理的资源和授权；raw path 只表示文件系统位置，不能替代权限语义。
* **All-files access vs ordinary storage permission**：前者是特殊宽权限，不能作为普通导入导出功能的默认方案。

本章结论
--------

Android 存储模型已经从“能不能访问某条路径”转向“这个 App 对哪类数据拥有什么访问能力”。设计存储功能时先按数据归属和用户意图选 API，再处理 target SDK 与版本兼容，最后才考虑真实文件路径。