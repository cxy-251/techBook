Frame, Tab, Site Instance, and Isolation Boundary
================================================

核心知识点
----------

* Tab 是用户界面与会话容器；Frame tree 才描述一个页面内部 main frame 与 iframe 的 document 嵌套关系。
* 每个 frame 都有自己的 URL、Document、加载生命周期和脚本执行环境；子 frame 的导航可以发生而不替换 top-level document。
* Origin 主要由 scheme、host、port 决定，是 DOM、storage、跨源读取和脚本直接访问的核心安全边界。
* Site 是更粗的站点分组概念；Chromium 的 SiteInstance 等实现对象用于把 frame/site 与 renderer process 分配、browsing context group 和 Site Isolation 联系起来。
* SiteInstance 是浏览器实现层概念，不是 Web 应用可依赖的标准 API；应用应依赖 origin、sandbox、Permissions Policy、COOP/COEP/CORP 等公开契约。
* 跨 origin iframe 即使能互相取得 WindowProxy 引用，也不能任意读取对方 DOM、cookie 或 storage；受控通信应使用 ``postMessage`` 并校验 ``targetOrigin``、``event.origin`` 和消息 schema。
* ``iframe sandbox`` 默认收紧能力，再通过 token 按需放开；``allow``/Permissions Policy 控制设备和高权限 Web 能力的委托。
* 跨站 frame 可能成为 Out-of-Process iframe，带来更强隔离，也增加 IPC、输入、合成和生命周期协调成本。

关键路径
--------

页面内部结构：

``Tab → Main Frame → Child Frame(s) → Document per Frame → Origin/Site Classification → Renderer Assignment``

跨源 iframe 通信：

``Parent Renderer → postMessage(targetOrigin) → Browser/IPC Boundary → Child Renderer → origin/schema validation → Application Handler``

嵌入能力判断：

``iframe src → origin/site → sandbox → Permissions Policy → browser isolation/process assignment → frame document execution``

概念辨析
--------

* **Tab vs Frame**：tab 是用户可见页面容器；frame 是文档嵌套节点，一个 tab 可以有多层 frame tree。
* **Frame vs Document**：frame 是可导航容器；document 是某一时刻装载在 frame 中的页面实例，导航可替换 document 而保留 frame 位置。
* **Origin vs Site**：origin 更细，关注脚本与数据访问；site 更粗，常用于 cookie/SameSite 或浏览器进程隔离等更高层分组。
* **Same-Origin Policy vs Site Isolation**：前者是 Web 安全语义；后者是浏览器使用进程隔离强化该安全边界的实现策略。
* **跨源不可直接访问 vs 不可通信**：跨源 frame 不能任意读取彼此对象，但可通过 ``postMessage`` 等显式通道通信。

本章结论
--------

分析 iframe、支付、广告、客服组件和第三方登录时，应按 ``Tab → Frame Tree → Document → Origin/Site → Process Isolation → Communication Channel`` 逐层判断。不要把一个可见页面误认为单一进程，也不要把进程隔离当成唯一安全规则；应用真正应依赖的是浏览器公开的 origin、sandbox、权限委托和受控消息契约。