第077章：Process Isolation, File Isolation, User Data Protection
===============================================================

核心知识点
----------

* Process Isolation 负责运行期边界：独立地址空间、进程凭据、系统调用、IPC 身份和系统服务访问控制共同限制一个 App 能触达的执行面。
* File Isolation 负责持久化边界：文件位于私有容器、共享媒体、用户文档、缓存、临时目录还是共享容器，会直接改变默认访问主体、生命周期和备份语义。
* User Data Protection 负责“设备锁定、重启、迁移、丢失”条件下的数据保密性与可用性。它依赖文件级加密、数据保护等级、密钥解锁状态和硬件信任链。
* Android 以 UID、Linux DAC、SELinux、app-specific storage、scoped storage 与 File-Based Encryption 构成主线；Apple 以 sandbox、container、entitlement、App Group 与 Data Protection class 构成主线。
* 路径字符串只表达目标，真正的授权来自调用进程身份和系统策略。知道另一个 App 的私有路径，不代表能够 ``open`` 它。
* App 私有持久数据、缓存、用户文档、媒体、共享文件必须分层管理：长期事实不能放在可随时清理的 cache，敏感私有数据也不应进入宽泛共享目录。
* 跨 App 共享必须通过受控入口完成。Android 常用 ContentProvider、content URI、SAF、MediaStore；Apple 常用 document picker、Photos picker、share sheet、App Group、security-scoped access。
* 文件保护和进程保护是两层问题。进程被杀后私有文件仍可存在；文件可读也不代表当前进程获得了对应系统能力。

关键路径
--------

普通 App 直接读取另一个 App 私有文件的典型路径是：

``App → libc / runtime → open/read syscall → VFS → UID / mode / SELinux or Sandbox Check → deny``

合法跨边界访问则应先由系统产生授权：

``用户选择文件 / 系统分享 → Framework / Provider → 生成 URI、FD、Bookmark 或 Sandbox Extension → App 按授权范围访问 → 授权到期或主动释放``

用户数据保护路径可压缩为：

``App 写入数据 → Private Container → File/Data Protection Policy → Key Material → Device Lock State / Hardware Security → Read Allowed or Denied``

排查文件问题时先确认数据类别，再确认存储位置，再确认调用者身份和授权来源，最后确认锁屏、加密、备份与共享状态。

概念辨析
--------

* **Process Isolation 与 File Isolation**：前者保护正在运行的内存和执行主体；后者保护跨进程、跨启动仍存在的字节。
* **Private Storage 与 Encrypted Storage**：私有表示其他 App 默认不可访问；加密表示即使存储介质被读取，仍需要密钥和解锁条件。两者解决不同风险。
* **Path 与 Capability**：路径是名称；content URI、file descriptor、security-scoped URL、bookmark 等可以携带受控访问能力。
* **Cache 与 Persistent Data**：cache 可被系统清理且应可重建；persistent data 承担用户或业务事实，不能依赖缓存存活。
* **Shared Container 与 Public Storage**：共享容器仍受签名、entitlement 或 group identity 限制；公共或用户选择的数据范围更宽，生命周期由用户和系统共同控制。

本章结论
--------

移动文件安全应按“数据是什么 → 放在哪里 → 谁在访问 → 授权从哪里来 → 密钥何时可用 → 生命周期如何结束”判断。进程、文件和密钥是三层不同边界，稳定架构必须让私有数据默认留在容器内，只通过系统认可的能力通道跨越边界。