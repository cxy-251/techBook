Browser Baseline, Feature Detection, Polyfill, and Transpilation Boundaries
============================================================================

核心知识点
----------

* Browser Baseline 把“支持哪些环境”从模糊口号变成架构输入，影响源码选择、构建目标、测试矩阵、bundle 大小和降级策略。
* Feature Detection 在运行时检查“当前环境能做什么”，比根据 User-Agent 推断能力更可靠；存在 API 仍不代表当前权限、secure context 或性能条件允许成功调用。
* Polyfill 在运行时补齐缺失的 API 表面，适合部分语言内建和可模拟能力；它无法复制浏览器内部安全模型、渲染引擎、线程、GPU、媒体、权限等原生语义。
* Transpilation 在 build-time boundary 改写语法或代码表示，使源码能被旧 parser/runtime 接受；它不能凭空提供缺失的宿主 API。
* 兼容策略应把基础路径、增强路径和实验路径分开，并为检测失败、调用失败和不可支持环境分别定义用户结果。
* 支持范围会产生性能成本：目标越旧，通常需要更多转换、helper、polyfill、runtime branch 和测试负担。

关键路径
--------

从源码到用户结果：

``Source Code → Build Target → Transpilation → Bundle/Asset → Browser Parse/Execute → Feature Detection → Native/Polyfilled/Fallback Path → User-visible Result``

运行时能力判断：

``API surface exists → current context permits use → operation succeeds → enhanced result``

任一步失败都应进入：

``fallback/degradation → preserved core task → telemetry``

兼容决策闭环：

``browser support policy → browserslist/build target → runtime checks → fallback behavior → automated tests → RUM/telemetry → policy adjustment``

概念辨析
--------

* **Baseline vs Feature Detection**：Baseline 是产品级支持策略；feature detection 是当前浏览器运行时的能力分支。
* **Feature Detection vs Permission Check**：检测 API 是否存在只能决定是否尝试；权限、用户激活、安全上下文和策略仍需单独处理。
* **Polyfill vs Native Implementation**：polyfill 可以模拟接口行为，但不能获得浏览器没有暴露的底层资源和强制安全能力。
* **Transpilation vs Polyfill**：transpilation 主要解决源码/语法兼容；polyfill 主要解决运行时对象或方法缺失。
* **User-Agent Sniffing vs Capability Detection**：UA 适合少数产品策略、已知 bug 或 telemetry 场景，不应成为普遍能力判断机制。
* **支持特性 vs 支持体验**：API 可调用不代表性能、bug、WebView 行为或低端设备体验已经满足产品要求。

本章结论
--------

Web 兼容性要按边界管理：Baseline 决定支持目标，transpilation 处理构建期语言差异，feature detection 决定运行时能力路径，polyfill 只在可模拟范围内补接口，fallback 保证核心任务可完成。把这些职责混在一起，会产生“构建成功但运行失败”的兼容性错觉。