第182章：Electron, Tauri, Desktop Web Runtime, and Native Boundary
==================================================================

核心知识点
----------

* Desktop Web runtime 把 Web UI 与桌面原生能力打包为同一个应用，安全边界从 browser origin 扩展到进程、文件系统、安装包和本地长期状态。
* Electron 常用 main process + renderer process；Tauri 常用 core process + system WebView。实现不同，但都需要把 UI runtime 与 native capability owner 分开。
* Renderer/WebView 负责 DOM、UI state 和用户输入；main/core 负责文件、窗口、shell、通知、本地数据库、系统权限和应用生命周期。
* Renderer 不应直接获得通用系统能力。稳定设计通过 preload/contextBridge、Tauri command/capability 等暴露小而具体的业务 API。
* IPC 是 privilege boundary。每个 channel/command 都要验证 sender/source、payload schema、路径、权限、operation allowlist 与返回错误。
* 文件系统操作应由宿主计算和限制路径；页面只提交 noteId、export intent 等业务标识，不能直接获得任意路径读写能力。
* Shell/opener、clipboard、native network、process 等能力都应被重写成窄业务动作，否则 XSS 或依赖漏洞会升级为本机攻击。
* 桌面应用的本地持久化比网页更长寿：SQLite、配置、token、cache、附件需要加密、schema migration、backup、cleanup 和 data export 策略。
* Desktop packaging 引入 code signing、installer、auto-update、channel、rollback 与平台分发边界；“刷新网页即可更新”的假设不再成立。
* Update package 必须验证签名和版本链，应用代码、runtime、native plugin、WebView/Chromium 依赖都可能需要安全更新。
* Electron 自带 Chromium/Node，Tauri 更依赖系统 WebView；这会改变包体、升级责任和平台差异，但不改变 native boundary 的核心风险。
* 桌面资源更充足不等于浏览器约束消失；renderer 仍会受到 JS、DOM、layout、GC、GPU 与主线程拥塞影响。

关键路径
--------

桌面能力调用：

::

   user action in renderer
   → narrow bridge API
   → IPC command/channel
   → main/core validates sender + schema + scope
   → OS/file/database/native API
   → normalized result/error
   → renderer updates UI

桌面发布：

::

   source + dependencies
   → build web/native artifacts
   → package application
   → sign artifact
   → distribute/update channel
   → verify update signature/version
   → migrate local state if needed
   → rollback/forward recovery

概念辨析
--------

* **Renderer 与 Main/Core**：renderer 是不应默认信任的 Web UI，main/core 是高权限系统能力所有者。
* **IPC 与 Local Function Call**：IPC 跨进程/权限边界，需要显式 contract、校验和错误模型。
* **Electron 与 Tauri**：runtime/package 技术不同，稳定比较应落在 WebView/renderer、native owner、IPC 与更新边界。
* **Local Persistence 与 Browser Cache**：桌面本地数据更持久、更接近用户资产，迁移、加密和备份责任更高。
* **Web Deploy 与 Desktop Update**：网站由服务器/CDN切换版本，桌面应用需要安装包、签名、渠道和客户端升级生命周期。

本章结论
--------

桌面 Web 应用应按 ``Renderer/WebView → IPC → Main/Core → Native Capability → Local Persistence → Signed Update`` 设计。Web 技术并没有消除原生安全边界；真正可靠的架构是让页面只能触达最小业务能力，并让本地数据和更新链条与系统权限同等受控。