第155章：ESM, CJS, Module Graph, and Package Boundary
=====================================================

核心知识点
----------

* Module system 定义代码单元怎样导入、导出、实例化与执行；它同时影响源码结构、bundler 静态分析和目标 runtime 的实际加载行为。
* ESM 使用 ``import/export``，依赖和导出更容易在执行前被静态分析，因此更利于 module graph、tree shaking 与 code splitting。
* CommonJS 使用 ``require/module.exports``，允许更多运行时加载模式；动态 require、条件加载和普通对象导出会降低静态分析能力。
* ESM 与 CJS 互操作会引入 default/named export、module namespace 与 loader 差异；同一包在 bundler、Node ESM、test runner 中可能得到不同结果。
* Module graph 是 build-time 的应用形状：entry、静态 import、dynamic import、CSS/asset import、worker entry 与 package condition 都形成图中的边。
* 顶层 side effect 会影响裁剪与执行顺序，例如 CSS import、polyfill、全局注册、数据库连接和环境读取。
* ``package.json`` 中的 ``type``、``exports``、``imports``、conditions、``browser``、``sideEffects`` 与 types 定义共同形成 package boundary。
* Conditional exports 让同一个 package specifier 在 browser、node、import、require 等条件下指向不同实现；配置错位会把 server-only 代码送进 client graph。
* Dual ESM/CJS package 增加兼容复杂度，适配层可把互操作问题集中在一个边界，避免扩散到业务代码。
* 模块错误最终会表现为 runtime/bundle bug：循环依赖、错误 side-effect 标记、动态 require、export map 错误和错误 target 都会改变产物。

关键路径
--------

模块解析：

::

   entry import specifier
   → package/file resolution
   → package.json type/exports/conditions
   → choose ESM/CJS target
   → add edge to module graph
   → analyze side effects / dynamic import
   → emit runtime-specific bundle

Package 边界检查：

::

   caller runtime
   → selected export condition
   → actual file/module format
   → dependencies + side effects
   → verify browser/server compatibility

概念辨析
--------

* **ESM 与 CJS**：前者偏静态模块图，后者更偏运行时加载；二者并非只差语法。
* **Module Graph 与 Chunk Graph**：module graph 描述源码依赖，chunk graph 描述构建后可加载产物依赖。
* **Side Effect 与 Export Usage**：导出未使用不代表模块可删除；顶层副作用仍可能必须执行。
* **Package Name 与 Package Entry**：同一个包名可因 condition 不同解析到不同文件。
* **Interop 与 API Contract**：ESM/CJS 互操作是模块装载问题，最好通过稳定适配接口隔离。

本章结论
--------

模块系统应按 ``Specifier → Resolution → Package Conditions → Module Graph → Runtime Target`` 阅读。ESM/CJS、export map 与 side effect 都会改变构建图和运行时现实；模块边界正确，后续 tree shaking、code splitting 与多 runtime 输出才有可靠基础。