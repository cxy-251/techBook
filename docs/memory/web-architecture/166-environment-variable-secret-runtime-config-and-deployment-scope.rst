第166章：Environment Variable, Secret, Runtime Config, and Deployment Scope
=============================================================================

核心知识点
----------

* 配置的第一条边界是读取时机：build-time config 会进入构建决策甚至被内联进 artifact，runtime config 则在部署后的请求/实例生命周期中读取。
* 只要值进入 client bundle、HTML、source map、static asset 或公开 response，它就属于 public artifact，不能再被当作 secret。
* Public config 不等于“毫无风险”，但它必须可以被任意用户看到；analytics id、公开 API base、UI flag 等属于这一类。
* Secret 是受信任 runtime 才能读取的敏感凭据，应按最小权限和最小作用域分配给 server、edge、CI、preview 或 production。
* Browser、edge、serverless、origin server、CI、preview environment 的 trust level 不同，不能共享同一组全权限 secret。
* Runtime config 适合控制无需重新构建即可改变的行为，如 feature flag、endpoint、region、log level、rate limit 和实验开关。
* Build-time config 跟 artifact 版本一起发布和回滚；runtime config 跟 deployment/config-store 生命周期一起变化，两者的回滚路径不同。
* Preview 与 production 必须是独立 trust boundary。Preview 应使用 sandbox credential、隔离数据与受控访问，不能默认连接生产数据库和生产 secret。
* Secret rotation 必须考虑旧实例、连接池、session 签名、webhook 校验、background job 和 edge region 仍在使用旧值的过渡窗口。
* Secret 不应进入普通日志、trace、错误响应和 client error report；可观察性记录 secret 名称、版本或安全摘要即可。
* 环境相关故障应按 ``build/deploy scope → runtime target → injected config → region/instance → artifact version`` 排查，而不是只检查变量名。

关键路径
--------

配置流：

::

   source references config
   → determine read time: build or runtime
   → determine target runtime
   → classify public / internal config / secret
   → inject through artifact or deployment binding
   → runtime reads scoped value
   → log config version, never secret text

Secret rotation：

::

   introduce new credential/version
   → allow old + new during compatibility window
   → roll new instances/regions/workers
   → update producers/consumers
   → revoke old credential
   → verify no stale instance still depends on it

概念辨析
--------

* **Environment Variable 与 Secret**：环境变量是注入机制，secret 是敏感信息分类；变量名或存储方式本身不构成安全边界。
* **Build-Time Config 与 Runtime Config**：前者随 artifact 固化，后者可在部署运行阶段读取和变化。
* **Public Config 与 Secret**：public config 可以公开，secret 必须限制读取主体和输出面。
* **Preview 与 Production**：二者可运行相同 artifact 形态，但应拥有不同数据、权限和 secret scope。
* **Rotation 与 Replacement**：轮换是新旧凭据有计划地过渡，直接替换可能让仍运行的旧实例立即失效。

本章结论
--------

配置系统应按 ``Read Time → Runtime Trust → Exposure Surface → Deployment Scope → Rotation`` 阅读。环境变量只是载体，真正的架构问题是值何时被捕获、谁能读取、是否进入公开产物、在哪些环境生效，以及轮换和回滚如何跨越仍在运行的旧版本。