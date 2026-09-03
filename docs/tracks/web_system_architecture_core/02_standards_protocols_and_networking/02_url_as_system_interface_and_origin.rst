========================================================================
Chapter 7: URL 架构角色：资源定位、状态载体与同源安全边界
========================================================================

.. note:: 前置背景与认知承接
   前一章解构了四大标准组织（WHATWG, W3C, TC39, IETF）的分层契约。在 Web 这一跨全球分布式系统中，URL（统一资源定位符）不仅是人机交互的地址栏输入，更是整个 Web 架构中最核心的系统级接口。URL 兼具全球唯一寻址、分布式状态序列化、前端路由解析输入以及浏览器安全同源边界（Origin）判定的四重身份。本章将从 WHATWG URL 标准状态机算法出发，系统剖析 URL 的微架构构成、编码规则、查询参数状态机，以及同源策略（Same-Origin Policy）的精确代数定义与安全隔离机制。

------------------------------------------------------------------------
7.1 URL 的四重系统架构角色
------------------------------------------------------------------------

在现代 Web 架构中，URL（Uniform Resource Locator）绝非普通的字符串，而是承载了四重关键系统职责的统一接口：

.. list-table:: URL 的四大系统架构角色与物理功能
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 架构角色
     - 解决的核心系统问题
     - 物理微架构体现
   * - 1. 全球资源唯一定位 (Addressing)
     - 解耦物理 IP 地址、机器名与抽象逻辑资源
     - 驱动 DNS 域名解析、CDN Anycast 路由与服务端反向代理分发
   * - 2. 分布式状态载体 (State Carrier)
     - 跨设备持久化、深度链接 (Deep Linking) 与无状态共享
     - 将视图筛选条件、分页索引与导航锚点编码为纯文本状态机
   * - 3. 跨端路由匹配输入 (Routing Input)
     - 驱动客户端与服务端的组件/处理函数调度
     - 路由引擎正则匹配、Path 参数提取 (`/users/:id`) 与子路由匹配
   * - 4. 浏览器安全边界原点 (Origin Anchor)
     - 划定网络资源、DOM 访问与本地存储的安全隔离范围
     - 驱动同源策略 (SOP)、Cookie 作用域与进程级站点隔离 (Site Isolation)

URL 标准结构与网络传输敏感度
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

依据 WHATWG 标准，标准 URL 由以下八个微架构组件严密拼接而成：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       标准 URL 微架构组件拆解                           |
   +-------------------------------------------------------------------------+

     https://alice:secret@example.com:8443/products/101?sort=desc&page=2#reviews
     \___/   \___/ \____/ \_________/ \__/ \__________/ \______________/ \_____/
       |       |     |         |        |        |              |            |
     Scheme  User  Pass      Host      Port     Path          Query       Fragment
     [--- 网络传输携带 ---] [ 寻址基准 ] [ 网络传输携带 ] [ 网络传输携带 ] [ 仅本地 ]

.. list-table:: URL 组件特征与网络传输矩阵
   :widths: 15 25 35 25
   :header-rows: 1
   :class: tight-table

   * - URL 组件
     - 语法形态示例
     - 解析规范与标准化行为
     - 网络请求是否传输
   * - Scheme
     - `https:`, `http:`, `ws:`
     - 大小写不敏感，统一小写化；驱动安全上下文判定
     - 是 (转换为传输协议)
   * - User / Pass
     - `alice`, `secret`
     - 早期 Basic Auth 凭证；现代 Web 严格废弃明文密码
     - 是 (Authorization 头)
   * - Host
     - `example.com`, `192.168.1.1`
     - 域名统一转小写，执行 IDN Punycode 编码
     - 是 (HTTP `Host` 头)
   * - Port
     - `:8443`, `:443`
     - 若为对应 Scheme 的默认端口（如 HTTP 80 / HTTPS 443），自动省略
     - 是 (TCP/IP 寻址端口)
   * - Path
     - `/products/101`
     - 层次化逻辑路径，斜杠标准化并消除 `.` 与 `..` 相对段
     - 是 (HTTP 请求行 Request-URI)
   * - Query
     - `?sort=desc&page=2`
     - `?` 开头的键值对序列，作为路由与动态计算的输入参数
     - 是 (HTTP 请求行 Request-URI)
   * - Fragment
     - `#reviews`
     - `#` 开头的文档内锚点，用于指示页面滚动或客户端内部路由
     - **否 (绝对禁止发送给服务端)**

------------------------------------------------------------------------
7.2 WHATWG URL 标准解析状态机算法
------------------------------------------------------------------------

早期 RFC 3986 规范由于过于抽象，导致不同浏览器在处理反斜杠 `\`、无效端口号与非 ASCII 字符时产生严重的分歧与安全漏洞。WHATWG URL 规范定义了一套**基于逐字符扫描确定性状态机（Deterministic Finite Automaton）**的解析算法。

解析状态机流转核心机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **特殊协议归一化 (Special Schemes)**：
   - 对于 `http`, `https`, `ws`, `wss`, `ftp`, `file` 等特殊协议，解析器强制将反斜杠 `\` 自动修正为标准正斜杠 `/`；
   - 自动移除空 Host 路径中的冗余斜杠，并自动补全缺失的根路径 `/`。
2. **国际化域名 (IDN) 与 Punycode 转换**：
   - 包含非 ASCII 字符的域名（例如 `中文.com`）由解析器自动调用 IDNA 标准，转换为 ASCII 兼容编码格式（Punycode）：
     
     .. math::
        	ext{Host}("中文.com") \xrightarrow{	ext{Punycode}} "xn--fiq228c.com"

3. **相对路径解析基准 (Base URL Resolution)**：
   - 当解析一个相对路径（如 `<img src="../logo.png">`）时，解析器必须强制绑定当前文档的 `document.baseURI`，通过回溯状态栈消除相对段：
     
     .. math::
        	ext{Resolve}("https://example.com/a/b/c", "../logo.png") \implies "https://example.com/a/logo.png"

------------------------------------------------------------------------
7.3 字符集编码与 Percent-Encoding 规则
------------------------------------------------------------------------

URL 必须由 US-ASCII 字符集的一个严格受限子集构成。任何超出该范围的 Unicode 字符（如中文、Emoji）以及具有特殊语法意义的保留字符，必须通过**百分号编码（Percent-Encoding）**进行转义。

百分号编码算法：将字符的 UTF-8 字节序列转换为 `%` 后紧跟两个十六进制字符（例如：汉字“中”的 UTF-8 编码为 `0xE4 0xB8 0xAD`，转义为 `%E4%B8%AD`）。

`encodeURI()` vs `encodeURIComponent()` 的规范差异
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 JavaScript 运行时中，开发者必须严格根据应用场景选择正确的编码函数：

.. list-table:: JavaScript 原生 URL 编码函数规范行为对比
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 编码函数
     - 保留不编码的特殊符号
     - 适用场景与安全边界
   * - `encodeURI(uri)`
     - `; , / ? : @ & = + $ #` 以及 `A-Z a-z 0-9 - _ . ! ~ * ' ( )`
     - **用于编码完整 URL**；保留协议分隔符与路径结构，防止 URL 语法破坏。
   * - `encodeURIComponent(str)`
     - 仅保留 `A-Z a-z 0-9 - _ . ! ~ * ' ( )`，编码其余所有符号
     - **用于编码 Query 参数值或 Path 单一片段**；确保参数内的 `&`、`=`、`/` 不会截断 URL 结构。

------------------------------------------------------------------------
7.4 URLSearchParams 查询参数状态机与序列化
------------------------------------------------------------------------

现代 Web 标准提供了 `URLSearchParams` 接口，将 Query String 建模为一个**有序键值对多重映射（Multimap）**。

.. code-block:: javascript

   const params = new URLSearchParams("category=books&tag=tech&tag=sci-fi");
   params.get("tag");        // 返回 "tech" (首个匹配项)
   params.getAll("tag");     // 返回 ["tech", "sci-fi"] (全部项)
   params.append("page", 1);
   params.toString();        // 输出 "category=books&tag=tech&tag=sci-fi&page=1"

数组参数序列化的三大工业范式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: Query 数组序列化范式对比
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 序列化范式
     - 示例格式
     - 规范程度与解析特征
   * - 1. 重复键范式 (Standard Multimap)
     - `?filter=a&filter=b`
     - **Web 标准与 HTTP 规范天然支持**；`URLSearchParams.getAll()` 直接原生解析。
   * - 2. 括号方括号范式 (PHP/Rails)
     - `?filter[]=a&filter[]=b`
     - 传统服务端框架流行；但在标准 URL 中 `[` 和 `]` 需被编码为 `%5B%5D`，增加长度。
   * - 3. 紧凑逗号分隔范式 (Comma-separated)
     - `?filter=a,b`
     - 体积极其紧凑；但若元素本身包含逗号时易引发转义歧义。

------------------------------------------------------------------------
7.5 同源策略 (Same-Origin Policy) 的数学定义与安全隔离
------------------------------------------------------------------------

**同源策略（Same-Origin Policy - SOP）**是浏览器安全体系的绝对基石。它将 Web 划分为无数个互不信任的安全沙箱。

同源性的精确代数判定公式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于两个 URL 实例 $A$ 与 $B$，当且仅当其 **协议（Scheme）、主机名（Host）与 端口（Port）** 三者完全严格相等时，判定为同源：

.. math::

   	ext{SameOrigin}(A, B) \iff \left( 	ext{Scheme}(A) = 	ext{Scheme}(B) \right) \land \left( 	ext{Host}(A) = 	ext{Host}(B) \right) \land \left( 	ext{Port}(A) = 	ext{Port}(B) \right)

.. list-table:: 以 `https://example.com:443/app/index.html` 为基准的同源判定矩阵
   :widths: 40 20 40
   :header-rows: 1
   :class: tight-table

   * - 对比 URL
     - 判定结果
     - 原因与安全差异
   * - `https://example.com/app/profile.html`
     - **同源 (Same-Origin)**
     - 协议均为 https，Host 相同，默认端口均为 443（路径不同不影响同源性）
   * - `http://example.com/app/index.html`
     - **异源 (Cross-Origin)**
     - 协议不同（http vs https，存在明文与加密安全等级差异）
   * - `https://example.com:8443/app/index.html`
     - **异源 (Cross-Origin)**
     - 端口不同（443 vs 8443）
   * - `https://api.example.com/app/index.html`
     - **异源 (Cross-Origin)**
     - 主机名不同（二级子域名不同属于不同 Origin）
   * - `https://example.com.attacker.com/`
     - **异源 (Cross-Origin)**
     - 主机名完全不同（经典钓鱼域名攻击）

同源策略对三大核心资产的物理保护
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **DOM 树与 JavaScript 上下文隔离**：
   - 页面中通过 `<iframe>` 嵌入的跨源网页，父页面绝对禁止通过 `iframe.contentDocument` 或 `window.frames[0]` 读取或修改其内部的 DOM 树、表单输入与 JavaScript 变量；
   - 通过 `window.open` 打开的跨源弹窗，`window.opener` 仅保留受限的 `postMessage()` 安全通信接口。
2. **客户端本地存储隔离**：
   - `LocalStorage`、`SessionStorage`、`IndexedDB`、`Cache Storage` 以及 `Service Worker` 注册范围，在物理存储层均以 **Origin 字符串为命名空间完全隔离**，恶意站点绝对无法跨源读取其他站点的离线数据。
3. **跨源网络请求与响应体保护**：
   - 浏览器允许跨源发送表单 POST 或 `<script>` / `<img>` 标签的资源嵌入，但通过 `fetch()` 或 `XMLHttpRequest` 发起的跨源异步请求，**默认会被浏览器拦截并禁止 JS 脚本读取响应数据（Response Body）**，除非目标服务端显式返回符合规范的 CORS 响应头。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了 URL 的四重架构角色、WHATWG 确定性解析状态机算法、百分号编码规则、URLSearchParams 数据模型，以及同源策略（SOP）的三元组数学判定与安全隔离机制。

在确立了 URL 寻址与安全原点之后，下一章我们将深入计算机网络底层——**传输层连接建立全景：DNS 递归解析、TCP 三次握手、TLS 1.3 协商与 QUIC 协议**，逐一解构一个 URL 是如何通过物理光纤与无线网络，在毫秒级时延内完成底层安全加密连接建立与通道复用的。
