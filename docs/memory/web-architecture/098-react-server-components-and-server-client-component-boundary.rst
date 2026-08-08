第098章：React Server Components and Server-Client Component Boundary
=====================================================================

核心知识点
----------

* React Server Components（RSC）解决的是组件执行位置：哪些 component usage 留在 server/build，哪些进入 browser client runtime。
* RSC 与 SSR 是不同维度。SSR 负责把 render result 转成 HTML；RSC 负责划分 server/client component tree，并通过 RSC payload 连接两侧。
* Server Component 适合读取数据库、内部 API、secret、权限上下文和 server-only helper，并把过滤后的结果组合成 UI。
* Client Component 标记交互浏览器边界：``state``、``effect``、event handler、DOM API、``window``、storage、focus、media 等能力必须位于 client side。
* ``'use client'`` 的影响沿 module dependency subtree 传播；边界放得越高，进入浏览器 bundle 的代码越多。
* Server Component 向 Client Component 传递的数据必须满足框架规定的序列化契约；数据库连接、secret、请求对象、文件句柄等 server-only 对象不能跨边界。
* RSC 首屏通常同时涉及 HTML、RSC payload 与 Client Component JavaScript；三类 payload 的到达和激活时间不同。
* server/client boundary 的位置会同时决定 bundle size、数据读取路径、缓存、权限、测试方式和错误恢复责任。

关键路径
--------

::

   Browser Navigation
     → Server Route / RSC Runtime
     → Read Request Context / Data / Permission
     → Execute Server Components
     → Produce RSC Payload
        ├─ Server Component rendered result
        ├─ Client Component placeholders / references
        └─ Serializable props
     → Optional SSR → HTML Preview
     → Browser receives HTML + RSC payload
     → Download Client Component chunks
     → Hydrate / Activate Client Components
     → User Event
     → Mutation back to trusted server

* 分析一个组件时先问：它是否真的需要浏览器能力；若不需要，应优先留在 server boundary，避免无意义扩大 client bundle。
* 跨边界传值时只传客户端完成任务所需的最小数据；敏感字段应在 server 读取和裁剪后再序列化。

概念辨析
--------

* **Server Component ≠ SSR component**：Server Component 定义组件在哪里执行；SSR 定义某次 render 是否生成 HTML。
* **Server Component ≠ 长驻服务器状态对象**：它通常随 build/request 执行，不在浏览器里持续拥有 state。
* **Client Component ≠ 只在客户端首次渲染**：它可以参与 server 预渲染 HTML，但其交互代码仍必须进入浏览器并激活。
* **RSC payload ≠ 普通业务 JSON**：它是 React/framework 协作使用的组件传输协议，包含 server result、client reference 与 props 等信息。
* **``'use client'`` ≠ 单组件开关**：它建立 module graph 边界，导入依赖也可能被带入 client bundle。

本章结论
--------

RSC 应被理解成 server/client 执行边界系统：可信数据读取、secret 和非交互 UI 尽量留在服务器；真正需要用户事件和浏览器 API 的部分才进入客户端。边界越精确，浏览器 JavaScript 越小，数据暴露面越清晰；任何跨边界数据都必须经过序列化、权限和失败恢复审查。
