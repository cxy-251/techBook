第070章：Permission Prompt, User Consent, and Capability Access Boundary
======================================================================

核心知识点
----------

* 权限是浏览器代表用户管理的 capability grant。页面只能在当前上下文中请求访问位置、相机、麦克风、通知、剪贴板、蓝牙、USB、文件系统、传感器等能力。
* 权限判断至少包含五个维度：请求主体（origin/frame）、能力类型、附加条件（HTTPS、用户手势、可见性、Permissions Policy 等）、授权生命周期、可访问数据范围。
* ``navigator.permissions.query()`` 可读取部分权限的当前状态，常见结果为 ``granted``、``denied``、``prompt``；不同 API 对查询和请求方式并不完全一致。
* ``granted`` 只表示当前权限门槛通过，不保证后续 API 必定成功；设备不存在、系统级权限关闭、文档失焦、能力被占用等仍会失败。
* Permission Prompt 是产品流程的一部分。稳定时机是用户明确触发相关任务之后，而不是页面加载时提前索取未来可能需要的能力。
* 请求前的页面说明应回答三个问题：为什么需要该能力、会访问什么、拒绝后如何继续。
* Notification、Clipboard、Geolocation 等能力常同时要求 secure context；部分能力还要求 transient user activation、focused/visible document 或顶层/iframe 策略允许。
* 权限状态会变化：用户可在浏览器或操作系统设置中撤销，浏览器也可能只提供一次性/临时授权。前端 store 或服务端记录不能替代实时权限状态。
* Permissions Policy 可由顶层页面限制 iframe 是否获得 camera、microphone、geolocation 等能力，嵌入页面自身同意还不够。
* 权限失败必须按类型恢复：用户拒绝、API 不支持、设备缺失、系统设置禁用、策略阻止、授权过期应映射到不同提示与替代路径。
* Data Minimization 是 capability 设计原则：只在完成当前任务时请求最小能力、最短时间和最少数据，不把“用户曾允许”升级成长期采集权。
* 业务系统可以保存“用户订阅了到货提醒”等业务偏好，但浏览器权限仍由用户和浏览器拥有；两者必须分别建模。

关键路径
--------

权限访问主路径：

``User Intent → 页面解释用途 → Secure Context → API Surface → Permissions Policy / iframe allow → 当前 Permission State → Capability API → Browser/System Prompt → Result / Error → 最小化使用 → UI``

权限变化路径：

``Previously granted → 用户/系统/浏览器设置改变 → PermissionStatus / API failure → 应用重新检测 → 降级或指导用户恢复``

失败恢复示例：

``Geolocation denied → 手动输入城市/邮编``

``Notification denied → 站内消息 / email 提醒``

``Clipboard write failed → 显示可选择文本``

排查顺序：先确认当前 browsing context、``isSecureContext`` 和 API 是否存在，再检查 iframe/Permissions Policy、permission state 与 user activation，最后查看实际 API error。

概念辨析
--------

* Permission ≠ 业务授权。浏览器允许摄像头访问，不代表用户拥有某项服务端业务权限。
* ``granted`` ≠ 永久授权。浏览器和系统可以撤销、缩短或改变授权范围。
* Permission Prompt ≠ 唯一门槛。Secure Context、用户手势、顶层策略、设备状态可能在弹窗前后继续限制能力。
* 服务端“用户已开启提醒” ≠ 浏览器通知权限仍有效。业务偏好与设备能力状态属于不同 owner。
* 请求权限 ≠ 必须阻断主任务。高质量产品应为拒绝和不支持提供替代路径。
* Permissions API ≠ 所有能力的统一请求 API。很多能力仍通过自身 API 触发授权流程。

本章结论
--------

权限应记成“用户经浏览器授予的临时能力，而不是应用资产”。设计顺序固定为 ``明确任务 → 最小能力 → 正确上下文 → 用户同意 → 实时状态 → 成功/失败双路径 → 可撤销与降级``。任何功能只在“用户点击允许”时才能工作，都说明它还缺少完整的恢复架构。