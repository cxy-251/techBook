第157章：TypeScript, JSX, Babel, SWC, and Language Lowering
==========================================================

核心知识点
----------

* TypeScript 属于构建期语言层，提供静态类型检查、接口约束和开发体验，最终通常输出 JavaScript；runtime 不会自动保留类型检查。
* Type erasure 造成 compile-time 与 runtime 的边界：API response、database row、cookie、localStorage、第三方事件仍需 runtime validation 或 parser。
* JSX 是 UI 描述源语法，需要在构建时转换为函数调用、runtime instruction 或 framework-specific output；浏览器并不直接执行 JSX。
* Type checking 与 transpilation 是不同责任。某些工具只转译不类型检查，CI 必须显式保留 typecheck，否则“能构建”不等于类型正确。
* Babel、SWC、TypeScript compiler、esbuild 等工具可承担不同 transform；真正要追踪的是谁负责 parse、typecheck、JSX、syntax lowering、module transform 和 minify。
* Target 决定需要把哪些新语法降级。面向更旧环境会引入 helper、regenerator、class transform 或 polyfill 需求，影响 bundle 体积与运行时语义。
* Polyfill 与 syntax transform 不同：transform 改写语法，polyfill 补运行时缺失 API。只转译 optional chaining 不会自动获得旧浏览器缺失的 Web API。
* Browser、Node、edge、worker、test 和 library target 能力不同，同一源码不能假设一套 lowering 配置覆盖所有输出。
* Server/client boundary 必须在语言工具链中保持可见；server-only env、Node builtin、browser global 不应被错误转换后悄悄进入另一个 target。
* Source map 需要贯穿多级 transform，否则最终压缩产物无法可靠映射回 TSX/JSX 原始位置。

关键路径
--------

语言转换：

::

   TS/TSX source
   → parse
   → typecheck diagnostics
   → remove type syntax
   → lower JSX
   → lower target syntax
   → module transform if needed
   → bundle/minify
   → browser/server/edge JavaScript

运行时输入：

::

   external unknown data
   → runtime schema/parser
   → validated application model
   → TypeScript-checked internal code
   → UI/domain logic

概念辨析
--------

* **Type Checking 与 Runtime Validation**：前者验证源码类型关系，后者验证真实运行时输入。
* **Transpile 与 Typecheck**：transpile 生成可执行 JS，typecheck 生成静态诊断；可以由不同进程完成。
* **JSX 与 DOM**：JSX 是源语法，DOM/HTML 是 runtime 输出之一。
* **Syntax Transform 与 Polyfill**：前者改写语法，后者补运行时 API。
* **Target 与 Runtime**：target 是构建假设，runtime 是实际执行环境；两者必须匹配。

本章结论
--------

语言工具链应按 ``Source Syntax → Static Types → JSX/Language Lowering → Target JavaScript → Runtime Validation`` 阅读。TypeScript 和编译器提升构建期可靠性，但真实 Web 边界仍由输出 JavaScript、运行时能力和外部数据共同决定。