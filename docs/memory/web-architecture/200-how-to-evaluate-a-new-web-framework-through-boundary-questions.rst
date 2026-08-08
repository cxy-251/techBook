第200章：How to Evaluate a New Web Framework Through Boundary Questions
=======================================================================

核心知识点
----------

* 评估新框架的可靠入口是边界图，而不是脚手架、语法、benchmark 或 marketing term。
* 第一步画出 ``browser / server / edge / build / CDN / framework cache / database / object storage / deployment``，并把真实用户路径放进去。
* 把宣传语翻译成系统路径：SSR 要落到 HTML 生成 runtime；server action 要落到 mutation；edge-ready 要落到 API 能力和 region；zero JS 要落到 browser artifact；smart cache 要落到 key/freshness/invalidation。
* 必须明确每段关键代码 runs where。Browser、server、edge、build time、worker、queue、database-adjacent runtime 的能力、状态和生命周期不同。
* 评估不能停在“源码怎么写”，要检查 generated artifacts：client bundle、server bundle、edge bundle、manifest、route output、HTML、data payload、cache header 和 source map。
* Client artifact 用来验证哪些代码真正发送到浏览器；server artifact 验证 server-only 依赖、数据库 client 和运行时包体；edge artifact 验证平台兼容性。
* Framework default 必须逐项审查：render mode、cache、prefetch、client/server split、error boundary、adapter、region、environment scope 都是隐含架构决策。
* 用 production-like path 验证框架，而不是只跑 hello world：session、tenant、permission、slow data、mutation、retry、cache invalidation、streaming 和 deployment rollback 都应覆盖。
* Failure path 比 happy path 更能暴露框架边界。要测试 upstream timeout、chunk missing、cache stale、action double submit、edge API unsupported、hydration mismatch 和 deploy rollback。
* Observability 是抽象安全的必要条件。框架可以隐藏实现，但 request id、runtime、cache status、route、artifact/release version、server/client error 必须可追踪。
* Escape hatch 决定框架遇到复杂场景时能否安全退出默认抽象，包括 raw Request/Response、custom server、manual cache control、adapter、SQL、worker/queue integration 等。
* 最终采用标准不是“功能多”，而是框架是否清楚封装需要的系统路径、是否最少隐藏必须控制的边界、是否保留可逆性。

关键路径
--------

新框架评估：

::

   choose one real production user flow
   → draw boundary map
   → translate framework terms into system paths
   → mark what runs where
   → inspect generated artifacts
   → inspect defaults and runtime limits
   → test failure/rollback paths
   → inspect observability and escape hatches
   → decide fit/reversibility

宣传语还原：

::

   SSR        → HTML production runtime + request context
   server action → mutation/auth/idempotency/error path
   edge-ready → supported APIs + data distance + platform limits
   zero JS    → actual browser bundle/activation requirements
   smart cache → cache object/key/freshness/invalidation/recovery

概念辨析
--------

* **Framework Demo 与 Production Path**：demo 证明 happy path 可用，production evaluation 必须覆盖真实状态、权限、缓存和失败。
* **Feature Claim 与 Runtime Evidence**：feature 名称只是声明，artifact、headers、logs、bundle 和平台行为才是证据。
* **Zero JS 与 No Client Cost**：即使框架减少 hydration，图片、CSS、analytics、browser work 和局部交互成本仍然存在。
* **Edge-Ready 与 Edge-Everything**：支持 edge 不代表所有 server logic 都适合移到 edge，数据距离和能力限制仍需单独验证。
* **Abstraction 与 Lock-In**：抽象本身不是锁定；缺少 escape hatch、可观测性和迁移路径才会放大不可逆成本。

本章结论
--------

评估新 Web 框架应按 ``Boundary Map → Runtime Placement → Artifact Evidence → Defaults → Failure → Observability → Escape Hatch`` 执行。框架只有在真实生产路径中能解释代码运行位置、状态所有权、缓存、失败和回滚时，才值得成为系统基础。