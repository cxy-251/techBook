第091章：File Access as Security Boundary
=========================================

核心知识点
----------

* 文件访问是权限系统的一部分：一次 ``open/read/write/share/backup`` 都应绑定调用者身份、资源 owner、授权来源、访问模式和生命周期。
* Path Traversal、symlink 与 file descriptor 泄漏分别攻击路径解析、对象重定向和已授权句柄生命周期；文件安全必须从字符串一直检查到内核文件对象。
* 外部文件名、归档条目和 provider metadata 都应视为不可信输入；稳定做法是限制目标根目录、生成内部安全文件名、使用独占创建和原子替换。
* fd/URI/URL 一旦跨进程传递，就等于传递访问能力；应限制读写模式、接收方、有效期和关闭时机。
* Shared File、Temporary File、Cache File 即使包含同样内容，也因 owner 与生命周期不同而具有不同安全责任。
* 原始敏感数据派生出的缩略图、OCR、索引、日志和缓存同样继承敏感级别；复制到私有缓存并不会自动消除数据泄漏风险。
* Android 通过 app-specific directory、Content Provider、SAF、URI grant、MediaStore 等机制组织文件能力；Apple 通过 container、security-scoped URL、App Group、File Provider 和 file coordination 组织文件能力。
* 跨 App 共享优先使用平台授权入口和受控副本，不应暴露原始私有路径或长期持有超出用户意图的资源句柄。

关键路径
--------

::

   User/App intent
     → path / URI / URL / fd
     → validate input and target owner
     → permission / sandbox / provider check
     → open file object
     → read / write
     → optional derived copy/cache
     → share via controlled grant
     → close / revoke / cleanup
     → backup policy

分享用户选择的 PDF：

::

   Picker grant
     → App reads original
     → create minimal temporary export if needed
     → system share API
     → receiver gets scoped URI/URL capability
     → sender cleans temporary artifact

概念辨析
--------

* **Path validation vs authorization**：路径校验防止目标逃逸；授权判断决定调用者是否有权操作目标，两者缺一不可。
* **Path vs file descriptor**：路径需要重新解析；fd 已绑定具体文件对象，泄漏后可能绕过后续路径级检查。
* **Shared file vs temporary file**：shared file 有明确跨主体使用语义；temporary file 只服务短任务并应及时回收。
* **Cache vs harmless copy**：缓存只是生命周期类别，不代表内容不敏感；敏感数据的派生副本仍需保护和清理。
* **App Group/shared container vs arbitrary cross-App access**：共享容器由签名、entitlement 或平台身份建立受控参与者集合，不是公共目录。

本章结论
--------

文件安全要沿完整对象生命周期分析：输入名称是否可信、最终打开的是哪个对象、谁获得了句柄、产生了哪些副本、什么时候关闭与清理、是否进入备份。移动平台真正保护的是受控访问能力，而不只是路径权限。