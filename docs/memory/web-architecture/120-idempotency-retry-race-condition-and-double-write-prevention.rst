Idempotency, Retry, Race Condition, and Double Write Prevention
==============================================================

核心知识点
----------

* 网络失败只说明调用方没有拿到结果，不能证明服务器没有提交；因此写入重试必须先设计幂等边界。
* Idempotency key 表示“一次业务意图跨多次尝试的稳定身份”，生命周期应绑定 checkout、upload、create 等具体 mutation，而不是组件 render。
* 相同 key 必须同时绑定用户、tenant、目标资源和请求指纹；同 key + 不同意图应返回冲突，而不是复用旧结果。
* 幂等记录必须存放在多个实例都能观察到的持久化或共享边界；单进程内存无法覆盖 serverless、水平扩容与多区域请求。
* HTTP 的 ``PUT``、``DELETE`` 等幂等语义只提供协议层预期；业务副作用仍可能重复，需要独立去重。
* Race condition 来自多个写入基于旧假设交错执行，例如自动保存旧请求晚到覆盖新值；version、ETag、compare-and-swap、唯一约束和事务用于约束顺序。
* Double write prevention 要同时覆盖重复请求、并发请求与副作用重复；按钮 disabled 只能降低用户重复触发，不能代替服务端唯一性与原子性。

关键路径
--------

``User Intent`` → 生成/恢复 idempotency key → 发出 mutation → server 校验 key + request fingerprint → 在数据库原子 reserve 或命中既有记录 → 校验权限与资源版本 → 执行业务事务 → 记录 canonical result → 对外部 provider 使用同一或映射后的幂等标识 → 响应可能丢失 → 重试仍携带同一 key → server 返回既有结果或处理中状态，而不是再次执行写入。

对于自动保存等顺序敏感写入，还要加入 ``expectedVersion`` 或等价 compare-and-swap 条件，防止请求到达顺序与用户操作顺序不同。数据库唯一索引负责把并发竞争变成可处理的确定结果。

概念辨析
--------

* **retry vs replay**：retry 是恢复动作；若服务端无法识别同一意图，它就可能退化成危险 replay。
* **HTTP idempotency vs business idempotency**：前者描述 method 预期效果；后者还覆盖订单、支付、通知等领域副作用。
* **duplicate request vs race condition**：重复请求可能表达同一意图；竞态是多个写入基于不同或过期假设交错影响同一状态。
* **disabled button vs write safety**：disabled 只管理当前 document 的交互入口；服务端/数据库才拥有跨页面、跨设备、跨实例的最终保护。
* **unique constraint vs idempotency record**：唯一约束防止非法重复事实；幂等记录还能把重复 attempt 映射回第一次结果。

本章结论
--------

可靠重试建立在“同一意图可识别、同一事实只能提交一次、重复 attempt 能拿到同一结果”之上。幂等键、版本检查、唯一约束、事务和副作用去重必须作为一套写入协议设计，而不是在出现重复订单后再补一个前端防抖。