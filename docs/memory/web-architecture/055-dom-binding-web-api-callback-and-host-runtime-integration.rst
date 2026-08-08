DOM Binding, Web API Callback, and Host Runtime Integration
============================================================

核心知识点
----------

* JavaScript engine 负责 ECMAScript 语言语义；浏览器 host 提供 DOM、Fetch、timer、storage、worker、media、clipboard、WebGPU 等平台能力。
* DOM binding 是 JavaScript object view 与浏览器内部 DOM object 之间的桥接层。``document``、``Element``、``NodeList``、``EventTarget`` 等都属于 host platform objects。
* Web IDL 定义平台接口如何暴露为 JavaScript 属性、方法、类型转换和异常；调用语法是 JavaScript，能力所有权仍在 browser host。
* 许多 Web API 只在同步调用阶段提交工作描述，真实工作在当前 JS call stack 之外继续：``fetch`` 进入网络路径，timer 由 host 计时，Worker 在独立执行环境运行，IndexedDB 由存储系统推进。
* Host 完成工作后，通过 task、microtask、event callback、message 等方式重新进入 JavaScript；reentry 时必须重新验证页面、route、component 和用户意图是否仍有效。
* DOM mutation 会触发浏览器后续工作：selector/style invalidation、layout、paint、accessibility tree、MutationObserver 等。频繁 JS↔DOM 跨界和同步 layout read/write 交错会放大成本。
* ``getBoundingClientRect``、``offsetWidth`` 等同步几何读取要求浏览器给出当前一致的布局结果；若前面刚修改 DOM/CSS，可能迫使 style/layout 提前执行。
* host capability 受 same-origin、CORS、secure context、permission、user activation、lifecycle 等策略约束，失败形态可能是 exception、Promise rejection、``null`` 或 ``DOMException``。

关键路径
--------

DOM 调用：

``JS expression → Web IDL / DOM binding → browser DOM object → tree mutation/read → style/layout/accessibility side effects → JS-visible result``

Fetch：

``JS fetch(Request) → browser host → Service Worker / HTTP cache / network / CORS → Response stream → Promise settled → microtask → JS continuation``

用户事件：

``device/user input → browser event system → DOM event dispatch → EventTarget listener → JavaScript callback → DOM/Web API calls → return to host``

排查 Web API：

``代码在哪个 host runtime → 调用了哪个 platform capability → 同步部分结束在哪里 → 进行中状态由谁持有 → 结果如何 reenter JS → 权限/策略是否允许 → lifecycle 是否仍有效``

概念辨析
--------

* **JavaScript language API vs Web API**：Array、Promise、Map 属于 ECMAScript；DOM、Fetch、timer、Storage 属于 Web host。
* **JS object vs Browser object**：脚本看到的是平台对象的 JavaScript 视图；真实 DOM、网络连接和设备能力由浏览器内部实现管理。
* **API call return vs Work complete**：``fetch()`` 返回 Promise 只表示请求路径已启动；网络、缓存与服务器工作还在继续。
* **DOM mutation vs Render**：DOM 已改变不表示 style/layout/paint 已完成。
* **AbortSignal vs 业务撤销**：signal 能通知 host 停止/忽略工作；已经落到服务器或数据库的副作用需要业务层恢复。
* **Main thread JS cost vs Host cost**：代码本身短也可能触发昂贵 layout、paint、storage 或网络路径；性能分析要跨边界观察。

本章结论
--------

浏览器中的 JavaScript 应按 ``Engine → Binding → Host Capability → Host Work → Callback Reentry`` 理解。DOM 和 Web API 不是普通库函数；它们把 JavaScript 连接到浏览器内部状态、网络、渲染、安全和设备能力。排查问题时先定位 host 边界，再分析语言层代码，才能区分调用成本、平台工作和回调恢复责任。
