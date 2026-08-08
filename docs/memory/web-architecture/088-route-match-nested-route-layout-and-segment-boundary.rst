第088章：Route Match, Nested Route, Layout, and Segment Boundary
===============================================================

核心知识点
----------

* 路由匹配把 URL 转换成应用内部结构，输出通常不是单个组件，而是一条从根到叶子的 matched route chain。
* 动态 segment 只先得到字符串参数；真正可用的资源上下文还需要语法校验、归一化、资源存在性确认、租户绑定与权限检查。
* Nested route 同时编码 URL 层级、共享 layout、数据 scope、权限上下文、错误边界与状态继承关系。
* Layout boundary 决定导航后哪些 UI、状态和运行时对象继续保留，哪些 segment 需要重新加载或重新挂载。
* Route segment 常同时成为 loader scope、bundle split、prefetch unit、cache key、loading boundary 与 error boundary。
* 匹配成功只说明应用知道“去哪里处理”，不说明资源一定存在或用户一定有权访问。

关键路径
--------

``URL → Segment Match → Params → Route Chain → Layout/Data Scope → Permission/Data Check → Page Commit``

* 对 ``/org/acme/projects/42/settings?tab=members``，静态段与动态段先形成 ``orgSlug=acme``、``projectId=42``。
* 匹配得到 ``OrgLayout → ProjectLayout → ProjectSettingsPage``，query ``tab=members`` 作为叶子页面中的可分享状态。
* 参数进入业务层前转换成可信 context，例如 ``orgId``、内部 ``projectId``、membership role。
* 父 route 建立组织/项目上下文，子 route 只消费已经确认的上层状态，减少重复数据和权限判断。
* 数据缓存键必须覆盖真正的资源边界，例如 tenant、resource、locale、permission view，而不能只使用表面 ID。
* 若上层组织失效，由组织级 boundary 接管；项目失败时保留组织 shell；叶子数据失败时尽量只替换局部内容。

概念辨析
--------

* **Route match vs resource existence**：匹配是结构选择；资源存在性与权限由 loader/server/data layer 确认。
* **URL tree vs route tree**：两者高度相关，但 layout route 可以增加执行层级而不增加 URL segment。
* **Dynamic param vs typed context**：URL 捕获值只是字符串；typed context 是经过校验、授权和资源解析后的业务上下文。
* **Nested route vs component nesting**：nested route 带有 URL、数据、错误、缓存与导航语义；普通组件嵌套只组织 UI。
* **Layout reuse vs stale state**：layout 可跨子路由保留，但保留状态必须属于该 layout 的稳定责任范围。

本章结论
--------

路由树是 URL、数据、权限、布局和失败边界共同形成的执行结构。设计 route 时，应从 segment、params、matched chain、layout ownership、data scope、cache key 和 failure scope 一起判断，而不是只看页面目录。稳定的路由架构让上层 context 可复用、下层失败可局部化，并保证每个 URL 都能落到明确的资源与用户可见状态。
