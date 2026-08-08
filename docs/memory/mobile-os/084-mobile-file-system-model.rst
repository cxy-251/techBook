第084章：Mobile File System Model
================================

核心知识点
----------

* 移动文件系统首先是安全边界，其次才是路径与字节的存储接口；访问结果由 ``身份 + 对象 + 授权 + 生命周期`` 联合决定。
* 数据应先区分为 App 私有数据、用户数据、系统数据、缓存和临时数据，再决定目录、共享入口、备份与同步策略。
* 私有数据依赖 App identity 与 sandbox；用户文档和媒体依赖系统 picker、provider、媒体库或显式授权；系统数据通常只能通过公开 Framework 间接访问。
* ``Path`` 只描述位置；``URI / URL / bookmark / handle`` 还可能承载授权、对象身份和持久访问语义。
* 文件描述符把一次已通过检查的访问转换成内核对象引用；跨进程传递时，传递的是对资源的访问能力。
* 备份、云同步和设备迁移属于文件生命周期的一部分；本地存在不等于应进入备份，也不等于可在另一设备直接恢复使用。
* 移动文件模型的稳定原则是：用户成果放用户空间，可重建数据放缓存，短期中间态放临时目录，业务事实和 App 状态放私有持久目录。

关键路径
--------

::

   App intent
     → 判断数据 owner 与生命周期
     → Framework storage API
     → App identity / permission / entitlement
     → Provider / picker / sandbox / URI grant
     → file descriptor / URL / handle
     → VFS / filesystem / encryption
     → read / write / share
     → backup / sync / cleanup policy

用户选择外部文档时，典型路径是：

::

   User selection
     → System Picker
     → URI / security-scoped URL
     → Provider / sandbox check
     → File Descriptor
     → App I/O
     → Persist grant / bookmark or release

概念辨析
--------

* **App private data vs user data**：前者服务应用运行并默认随 App 数据生命周期管理；后者属于用户，应能通过用户可见位置、媒体库或文档系统持续管理。
* **Path vs capability reference**：路径是名字；URI、bookmark、fd、handle 可能同时包含系统授予的访问能力。
* **Shared storage vs public raw filesystem**：共享存储不等于任意路径开放；现代移动平台通过集合、provider、picker 和授权句柄收缩可见范围。
* **Cache vs persistent data**：缓存必须可重建；业务事实、草稿和用户成果不能依赖缓存存活。
* **Backup vs sync**：备份恢复某个时间点的设备/App 状态；同步让多设备持续收敛，是两套不同的数据连续性机制。

本章结论
--------

移动文件系统的核心不是“文件在哪里”，而是“谁凭什么访问哪一份数据，并且这份访问权和数据要存活多久”。分析任何文件问题都先确定数据归属，再确定授权来源，随后检查句柄、目录语义、备份同步和清理策略。