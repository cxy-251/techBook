Custom Elements, Shadow DOM, Template, and Encapsulation Boundary
=================================================================

核心知识点
----------

* Web Components 是浏览器原生组件原语的组合：Custom Elements 定义元素类型与生命周期，Shadow DOM 定义内部树边界，``template`` 提供惰性可克隆结构，``slot`` 提供 light DOM 到 shadow tree 的内容分发。
* Custom Element 先作为普通 DOM 元素存在，再通过 ``customElements.define`` 注册和升级为带行为的元素；外部接口应尽量稳定在 attribute/property、method、event、slot 和样式协议上。
* 生命周期回调承担不同责任：constructor 建立内部对象；``connectedCallback`` 处理连接到 document 后的工作；``disconnectedCallback`` 负责清理；``attributeChangedCallback`` 同步声明式输入。
* Shadow DOM 提供 DOM 与样式作用域边界，但不是安全边界。``open``/``closed`` 只改变脚本可见性，不替代权限、认证和数据隔离。
* 事件跨 shadow boundary 时受 bubbles、composed 和 retargeting 影响；组件对外通信应通过明确 CustomEvent 协议，而不是依赖内部节点结构。
* 样式封装应通过 CSS custom properties、``::part`` 等显式入口开放；外部代码若依赖 shadow 内部 selector，封装会失去稳定性。
* 组件内部状态、应用业务状态和服务器事实必须分开。Web Component 适合拥有局部 UI 状态，不应偷偷成为路由、登录态、购物车或服务器缓存的事实源。

关键路径
--------

组件建立：

``HTML custom element → DOM host → CustomElementRegistry → upgrade/constructor → connectedCallback → shadow tree/template → slot distribution → visible component``

输入同步：

``attribute/property change → lifecycle/update logic → shadow DOM mutation → style/layout/paint``

对外事件：

``internal control → CustomEvent(bubbles, composed) → shadow boundary → application listener → business action``

生命周期释放：

``DOM removal → disconnectedCallback → remove listeners/observer/timer/subscription``

概念辨析
--------

* **Custom Element vs framework component**：前者是浏览器 DOM 元素类型；后者是框架运行时抽象。框架可以渲染和使用 Custom Element。
* **Shadow DOM vs security sandbox**：Shadow DOM 提供结构和样式封装，不提供可信安全隔离。
* **Light DOM vs Shadow DOM**：light DOM 由宿主页面提供；shadow tree 由组件内部拥有；slot 负责组合二者。
* **Attribute vs Property input**：attribute 适合可序列化、可写入 HTML 的声明输入；复杂运行时对象通常通过 property/method 传递。
* **``template`` vs hidden DOM**：template 内容默认不进入当前渲染树；它是待克隆的惰性片段。
* **Internal event vs public event**：内部点击是实现细节；组件应向外暴露稳定、语义化的业务事件协议。

本章结论
--------

Web Components 把一部分组件边界降到 Web 平台层。可靠设计的重点不是“封住 DOM”，而是明确宿主接口、生命周期、事件出口、样式入口和状态归属。只要组件越过这些边界去隐式拥有应用级事实，封装就会从复用能力变成新的耦合源。