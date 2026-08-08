第088章：Apple Storage Access Model
===================================

核心知识点
----------

* Apple 文件模型把“资源位置”和“访问授权”分离：相同 URL 只有在当前 sandbox、entitlement、security scope 和 provider 状态允许时才可访问。
* App bundle 保存签名代码与只读资源；data container 保存私有数据；App Group container 用 entitlement 为主 App 与 extension/相关 App 提供受控共享。
* 标准目录语义稳定：``Documents`` 放用户文档，``Library/Application Support`` 放长期内部支持数据，``Library/Caches`` 放可重建缓存，``tmp`` 放短期中间态。
* Files App 与 Document Picker 把容器外文档访问转换成用户选择；open-in-place 需要处理 security-scoped access、file coordination 和 provider 状态。
* Security-scoped URL 是当前访问窗口；bookmark 用于保存并恢复以后访问同一外部资源的能力，解析后仍需处理 stale、移动、删除和撤销。
* iCloud Documents / ubiquity container 把文件加入多设备同步；本地 URL 可能对应尚未下载、正在同步或存在冲突的云端文档。
* File Provider 让第三方或系统存储后端以统一文档模型接入 Files；App 应依赖 provider 协议和协调机制，而非假定资源永远是普通本地文件。

关键路径
--------

::

   App file request
     → own container?
       → yes: FileManager / normal file I/O
       → no: Document Picker / Files / Provider
     → user grants access
     → security-scoped URL
     → startAccessingSecurityScopedResource
     → file coordination / provider / iCloud
     → read / write
     → stop access

持久最近文档：

::

   User selects file
     → security-scoped URL
     → create bookmark
     → persist bookmark in App private data
     → next launch resolve bookmark
     → detect stale / provider state
     → re-enter security scope

概念辨析
--------

* **Bundle container vs data container**：bundle 主要保存签名代码和资源；data container 保存可变 App 数据。
* **Documents vs Application Support**：前者面向用户文档语义；后者面向用户不直接管理的长期内部状态。
* **Security-scoped URL vs bookmark**：URL scope 解决当前会话访问；bookmark 解决后续重新定位并恢复授权。
* **iCloud Backup vs iCloud Documents**：前者是设备/App 状态恢复；后者是用户文档持续同步。
* **Local file vs File Provider item**：provider item 可能按需下载、远程存储或被其他设备修改，不能假定始终驻留本地。

本章结论
--------

Apple 存储访问的稳定读法是：先判断资源属于哪个 container，再判断用户选择和 entitlement 提供了什么能力，随后检查 security scope、provider/iCloud 状态和 file coordination。路径存在只是访问成功的一个条件。