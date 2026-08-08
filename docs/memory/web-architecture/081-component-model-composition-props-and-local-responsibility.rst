第081章：Component Model, Composition, Props, and Local Responsibility
=====================================================================

核心知识点
----------

* 组件是 UI 责任单元，不是单纯的视觉切块。责任应覆盖输入、输出、局部状态、事件和生命周期。
* Props 是父到子的显式输入边界，应表达稳定语义，而不是把模糊的大对象和隐式全局依赖塞进组件。
* Composition 通过 children、slot 等方式组合局部责任，决定状态提升、事件回传和布局边界。
* 局部状态应优先放在最近的责任拥有者处；只有共享范围扩大时才逐级上移。
* 组件可以消费 server state 或 cache snapshot，但不应因此成为远端数据、权限或业务规则的权威所有者。
* 可复用组件需要明确行为契约：props、事件、受控/非受控模式、loading、error、disabled、可访问性和样式覆盖。

关键路径
--------

分析组件时使用固定顺序：

``Input/Props → Local Responsibility → Local State → UI Output → User Event → Callback/Event Upward → External Owner``

以商品卡片为例：

``Product Snapshot → ProductCard → Quantity Local State → DOM → Add-to-Cart Intent → Parent Mutation → Server``

其中：

#. 商品快照由上层数据边界提供；
#. 卡片负责展示与局部交互；
#. 数量输入可由卡片局部持有；
#. “加入购物车”事件只是用户意图；
#. 库存确认、登录检查和持久化属于更外层系统。

拆分组件时，优先按责任差异划分，例如图片加载、数量输入、收藏按钮和购买提交，而不是机械按 DOM 区块数量拆文件。

概念辨析
--------

* **Component ≠ business owner**：组件负责 UI 责任，不天然拥有库存、订单、账号和权限真相。
* **Props ≠ mutable shared state**：props 是输入快照，子组件不应把它当成本地可随意修改的权威状态。
* **Local state ≠ global store by default**：局部交互状态过早全局化会扩大更新范围和认知成本。
* **Composition ≠ deep coupling**：组合应让父级控制结构和上下文，同时保持子组件的局部契约清晰。
* **Reusable ≠ generic config object**：可复用组件更需要具体、可读的行为契约，而不是无限扩张的 ``config``。

本章结论
--------

组件架构的核心问题是责任归属。先定义组件接收什么、输出什么、自己持有什么、向外发出什么事件，再决定拆分和状态位置；只要组件同时吞下数据请求、缓存、权限、路由和业务规则，边界就已经开始失控。