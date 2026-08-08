第180章：Browser Extension Execution Model and Permission Boundary
===================================================================

核心知识点
----------

* Browser extension 是由浏览器托管、与普通网页并行运行的高权限代码包；它拥有网页默认拿不到的浏览器能力。
* Extension runtime 要拆成 page、content script、background/service worker、popup、declarative rule、native host 等不同上下文。
* Content script 最接近页面 DOM，适合观察、注入和页面适配；它不应成为高权限能力中心。
* Background/service worker 适合承载扩展级状态、权限 API、跨标签页事件和消息协调；其生命周期可能是事件驱动而非永久驻留。
* Popup 是短生命周期用户交互入口，不适合承担长期状态；稳定状态应进入 extension storage、IndexedDB 或受控后端。
* Extension permissions 定义提升后的能力边界。``host_permissions``、tabs、cookies、storage、network rules、native messaging 的风险和可见数据不同。
* 权限应遵循最小授权：能用 activeTab 临时获得的能力，不必长期覆盖所有站点；能按具体 host 收窄的范围，不应声明全网。
* Content script 与 page JavaScript 即使共享 DOM，也通常处于不同执行世界；两者通信应使用 DOM/message contract，而不是依赖共享变量。
* Extension messaging 是 privilege-transfer boundary。低权限页面/content script 请求高权限 background 执行操作时，必须验证 sender、operation、payload 与用户意图。
* Native messaging 把浏览器权限继续扩展到操作系统进程，必须有严格 allowlist、输入 schema、安装来源和进程审计。
* 扩展会改变网页真实运行环境：广告拦截、密码管理器、翻译、企业策略和恶意扩展都可能改 DOM、请求、cookie 或脚本行为。
* 权限越强，产品对用户说明、撤销路径、数据最小化、安全测试与审核的责任越高。

关键路径
--------

扩展操作：

::

   web page / user action
   → content script observes DOM
   → structured message
   → background validates sender + permission
   → extension API / storage / declarative rule
   → minimal result returned
   → content script updates page

权限设计：

::

   business capability
   → identify required browser resource
   → choose smallest permission/host scope
   → isolate privileged call in background
   → validate messages
   → expose clear user consent/revocation path

概念辨析
--------

* **Page Script 与 Content Script**：前者属于网站 origin，后者属于扩展并靠近页面 DOM；代码来源和权限来源不同。
* **Content Script 与 Background**：content script 负责页面适配，background 负责扩展级高权限和跨页面协调。
* **Host Permission 与 API Permission**：前者限制可接触哪些站点，后者限制可调用哪些浏览器能力。
* **Message Passing 与 Function Call**：消息跨权限和生命周期边界，需要 schema、sender 与错误语义，不能按本地函数调用假设。
* **Extension Bug 与 Site Bug**：用户页面被扩展修改后出现异常，不代表站点代码自身一定错误；调试需要考虑扩展环境。

本章结论
--------

浏览器扩展应按 ``Execution Context → Permission → Message Boundary → Privileged Capability → User Control`` 设计。稳定扩展架构的关键是把接近页面的代码与拥有高权限的代码分开，并让每一次权限提升都能被最小化、验证、审计和撤销。