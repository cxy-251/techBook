第057章：Fetch, Request, Response, Body, and Streams
====================================================

核心知识点
----------

* ``fetch()`` 是 JavaScript 进入浏览器网络体系的可编程请求边界；应用表达请求意图，浏览器负责安全策略、缓存、Service Worker、网络调度和响应暴露。
* ``Request`` 同时编码 intent、context 与 policy：URL、method、headers、body 表达意图，origin/referrer/client 表达上下文，``mode``、``credentials``、``cache``、``redirect``、``signal`` 表达策略。
* ``fetch()`` resolve 只表示获得了 ``Response``；``404``、``500`` 仍属于正常 resolve。网络失败、CORS 拒绝、abort 等请求级失败才进入 rejected promise。
* ``Response`` 应分三层判断：HTTP status、response metadata、body format。``response.ok`` 不能证明 JSON 合法，也不能证明业务数据符合前端 contract。
* Request/Response body 基于一次性消费的 stream 模型。``json()``、``text()``、``blob()`` 等只是高级消费方式；需要多次读取时必须在消费前 ``clone()`` 或保留原始输入。
* ``ReadableStream`` 允许服务器逐块发送、浏览器逐块接收、JavaScript 增量解码和 UI 渐进更新；同时引入 framing、背压、取消、部分失败和顺序控制问题。
* ``AbortSignal`` 把用户新的 intent、路由切换、组件卸载等状态变化连接到请求生命周期；取消旧请求后仍需防止旧结果覆盖新状态。

关键路径
--------

::

   User Intent
     → Build URL / Request
     → Browser Fetch Policy
     → Service Worker / HTTP Cache
     → Network / Server
     → Response Headers
     → Body Stream
     → Decode / Parse
     → Validate
     → Client State / UI

错误处理应按以下层级展开：

::

   Request failure
     → network / CORS / abort
   Response received
     → HTTP status
     → Content-Type / metadata
     → body decode / parse
     → runtime schema / business validation

流式响应的稳定模型：

::

   response.body
     → byte chunks
     → decoder
     → application framing
     → incremental records
     → guarded UI updates

概念辨析
--------

* ``fetch()`` 与 HTTP 成功：Promise resolve 不等于 HTTP 2xx；HTTP 错误必须显式检查 ``status`` 或 ``ok``。
* ``Request`` 与网络包：Request 是浏览器 Fetch 算法的输入对象，实际网络请求还会受 cookie、CORS、Service Worker、cache、redirect 等浏览器策略影响。
* ``no-cors`` 与“解决跨域”：``no-cors`` 会得到受限 opaque response，不能绕过同源安全模型。
* HTTP cache 与应用状态缓存：前者复用 HTTP response，后者由框架或业务代码保存解析后的数据，两者失效规则不同。
* body stream 与完整 JSON：stream 强调增量消费；完整 JSON 强调一次解析。数据量、首字节体验和恢复要求决定选择。
* abort 与业务撤销：abort 主要终止浏览器侧请求消费，不能保证服务器已经停止业务处理或副作用。

本章结论
--------

分析 Fetch 时固定沿 ``Intent → Request → Browser Policy → Response → Body → Validation → State`` 追踪。先确认请求 contract，再确认浏览器允许什么，随后区分请求失败、HTTP 失败和解析失败；大响应再继续判断 stream、背压和取消。不要把 ``fetch()`` 当成一个普通异步函数调用，它是 JavaScript、浏览器安全模型、缓存、网络和应用状态之间的系统边界。