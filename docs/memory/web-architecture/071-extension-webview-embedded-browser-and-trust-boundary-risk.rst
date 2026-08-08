第071章：Extension, WebView, Embedded Browser, and Trust Boundary Risk
====================================================================

核心知识点
----------

* 普通网页安全模型并不能覆盖真实运行环境中的所有执行主体。浏览器扩展、密码管理器、企业插件、WebView、Electron/桌面容器和 native bridge 都可能改变页面附近的能力假设。
* Browser Extension 是独立执行主体，拥有自己的 permission、host permission、content script、background/service worker 和 extension API；其权限模型高于普通网页。
* Content Script 与页面共享 DOM 观察面，却通常运行在 isolated world。JavaScript 全局隔离不代表 DOM 是可信输入，页面和扩展都可能修改同一棵 DOM。
* Extension message passing 会把页面附近的数据送到高权限扩展上下文；任何 ``page/content script → extension background → privileged API`` 路径都应按跨信任边界调用校验。
* 扩展可能读取页面、注入 UI、访问 tab/cookie/history、修改或阻断网络请求；页面服务器不能假设客户端 DOM、header 或本地状态不可被扩展改变。
* WebView 把 Web document 放进 native App 的信任模型。除了网页 origin，还存在宿主 App、平台 WebView 实现、native permission 与 server 四个所有权层级。
* Native Bridge（如 Android JavaScript interface、iOS message handler、WebView2 host object、Electron preload API）把 Web 输入连接到更高权限的文件、设备、账号、支付等能力，是高风险 capability boundary。
* Bridge 能力必须绑定 origin、导航生命周期、明确的 method allowlist、参数 schema、用户动作和最小权限；不能把任意页面字符串直接转交 native 高权限 API。
* 页面参数不能成为支付金额、账号权限、文件路径等可信事实。Native 和 Server 必须重新根据受信任状态确认操作。
* WebView 导航后 origin 可能改变；宿主若继续保留旧 bridge 或 host object，就会把原本只授予可信页面的能力泄露给新页面。
* Embedded Browser 常弱化普通浏览器的地址栏、证书提示、站点设置等用户信任信号，因此宿主必须显式控制导航、外链、下载、权限和调试入口。
* 安全分析顺序应从“有哪些执行主体”开始，再看它们能读什么、能改什么、能调用什么、数据会流向哪里。

关键路径
--------

扩展路径：

``Web Page DOM → Content Script → validate/normalize → Extension Message → Extension Service Worker / Background → privileged extension API / remote service``

WebView 路径：

``Native App → WebView loads URL → Browser Engine creates Document → Origin check → optional Native Bridge exposure → Page sends method + params → Native validates origin/schema/user intent → OS capability / Server API → Result``

支付类 bridge 稳定路径：

``Page 提交 orderId → Native/Server 根据可信订单读取 amount/status → Native 调系统支付 → Server 回调/查询确认 durable state → Page 仅展示最终结果``

排查时先识别当前页面是在普通浏览器、扩展增强环境还是 WebView；随后检查注入脚本、host permissions、bridge 暴露时机、当前 origin、导航历史和 server-side confirmation。

概念辨析
--------

* Isolated World ≠ DOM 隔离。Content Script 与页面脚本全局变量可以分开，但双方仍可通过 DOM、事件和消息相互影响。
* 扩展安装 ≠ 扩展拥有所有站点权限。必须看实际 host match、declared permission、optional grant 和运行时状态。
* WebView ≠ 普通浏览器 tab。宿主 App 可以控制导航、cookie、bridge、权限和系统能力，用户可见信任提示也不同。
* HTTPS ≠ Native Bridge 安全。HTTPS 保护网页传输；bridge 还需要 origin allowlist、方法白名单、参数校验和 native/server 授权。
* 页面 DOM ≠ 可信业务状态。DOM 可以被用户、脚本、扩展和调试工具修改，关键金额与权限应回到 server state。
* Native 返回成功 ≠ 服务端状态已持久化。支付、账号、文件同步等操作应由可信服务端确认 durable result。

本章结论
--------

扩展和 WebView 会在网页之外增加新的高权限执行主体。分析模型必须从 ``Page Origin`` 扩展为 ``Page → Extension/Embedded Runtime → Native/Browser Privilege → Server``。任何桥接路径都要坚持最小权限、显式 origin、消息/参数验证和服务端最终确认；客户端环境只能表达用户意图，不能成为高价值业务事实的唯一信任来源。