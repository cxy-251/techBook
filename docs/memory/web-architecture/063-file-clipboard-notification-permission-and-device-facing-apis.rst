第063章：File, Clipboard, Notification, Permission, and Device-Facing APIs
=========================================================================

核心知识点
----------

* Device-facing API 让页面跨出 document，访问用户文件、系统剪贴板、通知中心、摄像头、麦克风、蓝牙、USB、传感器或文件系统句柄。
* 这类能力统一受浏览器守门：安全上下文、用户激活、权限提示、Permissions Policy、浏览器设置、操作系统状态和设备可用性都可能共同决定结果。
* 页面代码只是能力使用方，外部资源并不归页面长期所有。权限由浏览器和用户共同拥有，设备与系统状态由用户环境拥有，服务端只拥有其接收到并确认的数据。
* File API 的基本模型是“用户显式选择后，页面获得被选中的 ``File`` 对象”；这与任意文件系统访问完全不同。拖拽只是另一种用户选择入口。
* 文件名、MIME、大小等客户端检查只用于早期反馈，上传后的安全校验、解码、权限和存储策略必须由服务端重新执行。
* Object URL 属于页面持有的临时资源引用；不再需要预览时应 ``URL.revokeObjectURL()``，避免无期限保留资源。
* Clipboard 读写操作会影响系统共享剪贴板。写入适合明确的“复制”用户动作；读取风险更高，应围绕 paste 意图、权限和降级路径设计。
* Notification 把输出带到页面之外；Push 进一步允许 Service Worker 在页面未打开时接收服务端事件。Push subscription 是浏览器、push service、Service Worker 和后端共同维护的状态。
* 摄像头、麦克风等媒体权限可被拒绝、撤销或因设备占用而失败；应用必须将 permission denied、device unavailable、track ended 等状态视为正常分支。
* 设备能力应遵循 progressive enhancement：核心业务先有不依赖高权限 API 的路径，再用设备能力增强体验。

关键路径
--------

文件选择与上传：

::

   User selects file
     → Browser exposes File
     → client preview / basic validation
     → upload request
     → server validates bytes and authorization
     → object storage / database
     → confirmed profile state

剪贴板写入：

::

   Explicit user action
     → secure context / policy checks
     → navigator.clipboard.writeText
     → OS clipboard
     → success feedback
        or manual-copy fallback

通知 / Push：

::

   User opts in
     → permission request
     → Service Worker registration
     → Push subscription
     → backend stores subscription
     → business event
     → Push service
     → Service Worker push event
     → system notification

媒体设备：

::

   User intent
     → getUserMedia constraints
     → browser permission + OS/device checks
     → MediaStream tracks
     → app consumes tracks
     → stop / revoke / device loss
     → cleanup and fallback

概念辨析
--------

* File API 与任意磁盘访问：File 通常来自用户显式选择；页面不能借此遍历任意本地文件。
* 客户端文件校验与服务端校验：前者改善体验，后者决定可信性和最终写入。
* Clipboard convenience 与业务结果：复制失败不应让邀请、分享等核心业务失败，应提供可选择文本或其他分享路径。
* Notification 与 Push：Notification 负责系统通知呈现；Push 负责把服务端事件送到 Service Worker，即使页面未打开也可触发处理。
* permission state 与业务授权：浏览器 permission 只控制设备能力，服务器仍需单独执行账户、租户和业务权限检查。
* capability available 与 capability usable：API 存在不代表当前设备、上下文、权限和策略都允许成功调用。

本章结论
--------

设备能力的稳定判断顺序是 ``User Intent → Secure Context / Policy → Browser Permission → External Resource → App Processing → Server Confirmation / Cleanup``。把拒绝、撤销、设备缺失和浏览器差异当作正常状态，并为核心业务保留无高权限的降级路径。Web 页面可以获得强大设备能力，但每项能力都必须围绕最小权限、明确用户意图和可撤销生命周期设计。