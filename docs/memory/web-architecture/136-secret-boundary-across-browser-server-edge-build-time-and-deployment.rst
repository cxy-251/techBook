第136章：Secret Boundary Across Browser, Server, Edge, Build Time, and Deployment
================================================================================

核心知识点
----------

* Secret 是能够代表系统身份、访问受限资源、签发可信操作或解密受保护数据的值；数据库密码、支付密钥、OAuth client secret、Webhook signing secret、JWT signing key 都属于能力型资源。
* Secret 和普通 configuration 可能都以环境变量形式存在，但治理方式不同。判断标准不是变量名，而是“泄漏后外部主体能获得什么能力”。
* Browser bundle、HTML、static JSON、source map、Network response、Service Worker cache 等都是公开产物。任何进入这些位置的值都必须按公开信息处理。
* Server runtime 可以持有 secret，但职责是用 secret 代表应用执行受控动作，再返回有限业务结果；不得把 secret 自身序列化、打印或传回浏览器。
* 常见泄漏面不只源码仓库，还包括 log、error report、trace attribute、debug endpoint、third-party SDK metadata、shell argument、crash dump、temporary file 和构建 artifact。
* Edge runtime 的 secret scope 可能与 origin server 不同。边缘节点数量、region、平台复制范围和 runtime 能力决定了 secret 暴露半径，因此应按最小权限单独配置。
* Build-time env 与 runtime env 必须区分。构建阶段读取的 public env 可能被内联进 client bundle并冻结；部署后修改 runtime secret 不会自动改变已发布静态产物。
* public env prefix 本质是发布声明。例如框架把某类前缀变量注入 client bundle 时，这些值已经不再是 secret。
* Secret 必须具备 scope、owner、rotation、revocation 和 audit。无法轮换的凭据一旦泄漏，会把恢复变成部署或代码迁移问题。
* 环境隔离应使用不同 secret：local、preview、staging、production 不共享高权限凭据；tenant-specific integration 还应继续缩小到租户作用域。
* Secret boundary 应由 tooling 强化，包括 secret scanning、server-only import guard、bundle analyzer、CI policy、日志 redaction、权限分级与 KMS/secret manager。
* Secret 泄漏后，删除源码并不能收回已经发布或记录的副本；正确恢复是立即撤销/轮换、确认使用范围、检查日志和下游副本、更新部署。

关键路径
--------

Secret 使用：

::

   deployment control plane
   → inject scoped secret into trusted runtime
   → server / edge reads secret locally
   → perform authorized external or internal operation
   → return limited business result
   → never serialize secret to client/log/telemetry

构建泄漏检查：

::

   env / config
   → build transform
   → client/server/edge bundles
   → static artifact / source map
   → inspect browser-downloadable output
   → rotate immediately if secret crossed public boundary

概念辨析
--------

* **Secret 与 Config**：config 描述行为，secret 代表能力；二者可能同形但风险完全不同。
* **Build-Time Env 与 Runtime Env**：前者可能固化进 artifact，后者由实际运行环境读取。
* **Public Env 与 Secret Env**：public env 可被浏览器下载，secret env 只能停留在可信 runtime。
* **Server Secret 与 Edge Secret**：都可位于可信执行区，但复制范围、权限和资源边界可能不同。
* **Redaction 与 Encryption**：redaction 防止 secret 出现在输出面，encryption 保护存储/传输；两者解决不同泄漏路径。

本章结论
--------

Secret 设计应按 ``Capability → Runtime Scope → Injection → Use → Output Surface → Rotation/Revocation → Audit`` 阅读。最硬的边界是：浏览器可下载内容永远是公开的；secret 只能进入最小可信 runtime，并必须能轮换、撤销和追踪。