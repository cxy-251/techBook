第190章：从本地修复到 Upstream Contribution
===========================================

本章必须记住
------------

#. 本地能运行的改动只是上游贡献的起点，不是可合入性证明。
#. Local Hack 主要恢复当前机器或私有环境；Upstreamable Fix 必须适用于可解释的用户和配置范围。
#. 两者差异不由代码行数决定，而由根因、适用范围、兼容性、可验证性和维护成本决定。
#. 本地绕过可以依赖硬编码设备、私有配置或一次性环境，上游修复不能把个人假设扩散给所有用户。
#. 上游修复必须描述真实症状、触发条件、对象状态和第一条可信失败路径。
#. “我的机器不再崩溃”不能证明根因已修复，也不能证明其它硬件安全。
#. 只删除 Warning、跳过错误路径或增加重试，可能掩盖对象生命周期和同步缺陷。
#. 上游 Patch 应恢复被破坏的不变量，而不是只改变触发概率。
#. 对资源泄漏，应重建申请、所有权转移、失败跳转和释放顺序。
#. 对 Use-after-free，应重建发布、异步使用、撤销、同步和最终 Free。
#. 对数据竞争，应重建两个访问者、共享字段和允许的同步语义。
#. 对硬件兼容问题，应说明受影响设备、Firmware、Capability 或 Quirk 范围。
#. 对性能问题，应证明成本位置、测量口径、收益和副作用。
#. Upstreamable Fix 至少回答：问题是否真实、根因在哪里、修复为何正确、哪些路径保持不变。
#. Patch 还应说明已有 ABI、错误码、配置和用户行为是否保持兼容。
#. 如果行为必须改变，应说明迁移理由和用户影响，不能把破坏隐藏在内部重构中。
#. 公共接口变化需要更广 Review、文档、测试和兼容分析。
#. 本地临时参数或 Debugfs 开关不应未经设计变成稳定用户接口。
#. 硬编码 Vendor/Device 条件只在真实硬件差异被证明且 Quirk 边界清楚时适合上游。
#. “所有同类设备都这样”需要设备能力、规范或维护者证据，不能从单台机器外推。
#. 修改前应搜索 Mainline、Maintainer Tree 和邮件归档，避免重复修复或忽略已有讨论。
#. 上游可能已经存在不同实现的修复，本地 Patch 需要 Rebase 或转为测试验证。
#. 提交基线应符合子系统要求，并包含目标 Bug 与必要依赖。
#. Patch 应一个逻辑问题对应一个 Commit，便于 Review、Bisect、Backport 和 Revert。
#. Commit Message 应自包含地说明问题、根因、修复、影响和测试。
#. ``Signed-off-by``、``Fixes``、``Closes``、``Link`` 和测试标签应真实准确。
#. 上游提交前测试应按 Patch 风险设计，而不是机械执行固定命令清单。
#. 构建测试确认目标配置和受影响架构能够编译或链接。
#. 构建通过不能证明运行路径、错误路径和硬件行为正确。
#. KUnit 适合纯 Helper、小状态机、解析器和内部错误转换。
#. kselftest 适合用户态可见 Syscall、Ioctl、Netlink、Sysfs、Namespace 和其它合同。
#. 子系统专用测试应优先覆盖维护者关心的真实接口和回归场景。
#. 真实硬件运行验证覆盖 Firmware、总线、IRQ、DMA、Reset 和 Power Management 条件。
#. 虚拟机、UML 和 Mock Device 结论不能无边界外推到真实硬件。
#. 正常路径测试必须和原失败路径测试同时存在。
#. 资源回滚修复应逐点制造初始化失败，并验证无残留对象、IRQ、Worker 和引用。
#. Remove 修复应在 I/O、异步回调和用户引用活动时验证 Teardown。
#. Suspend/Resume 相关修复应至少验证重复循环和失败恢复，而不只验证首次恢复。
#. 性能修复应保存修改前后相同负载下的吞吐、延迟分布、CPU 和错误指标。
#. 静态检查可包括 Checkpatch、Sparse、Smatch、Coccinelle 等，精确选择按子系统和改动决定。
#. 静态工具报告是线索，不能替代语义判断。
#. 动态检测可结合 KASAN、KCSAN、Lockdep、UBSAN 或 KFENCE，配置和开销必须记录。
#. 测试说明应诚实写出未覆盖的架构、硬件和配置。
#. “Tested” 应说明测试对象和结果，不应只有一个无上下文单词。
#. Cover Letter 可集中描述 Series 的测试矩阵，每枚 Patch 仍应说明自身验证边界。
#. 提交前应运行 ``git diff --check``、阅读完整 ``git show`` 并检查生成的 Patch Mail。
#. ``scripts/checkpatch.pl`` 通过不等于 Patch 可上游化。
#. ``scripts/get_maintainer.pl`` 只生成候选，最终路由仍需人工判断。
#. 发出 Patch 前应检查当前 Maintainer、列表、子系统规则和开发阶段。
#. 发送 Patch 不是交付完成，而是进入 Review、测试和版本迭代阶段。
#. 作者需要回复 Review、机器人报告、测试失败和维护者问题。
#. 实质修改后应发送自包含 v2/v3，并说明版本变化。
#. Patch 被应用到维护者树后，应核对最终 Commit、分支和任何调整。
#. Patch 进入 ``linux-next`` 后应关注跨子系统构建和运行问题。
#. Patch 进入 Mainline 后应关注 ``-rc`` 期间的用户回归和机器人报告。
#. 作者责任不会在 ``Reviewed-by`` 或 Maintainer Apply 时结束。
#. 真实用户报告可能暴露实验室没有覆盖的 Firmware、拓扑和 Workload。
#. 出现回归时应优先恢复已有用户行为，通过修复或 Revert 收敛风险。
#. Stable Backport 的前提通常是明确修复已进入上游，并符合 Stable 规则。
#. Stable Tree 不是新功能和未验证本地 Patch 的旁路入口。
#. 适合 Stable 的 Patch 通常应小、明确、修复真实问题并具有可回归验证的影响。
#. ``Cc: stable@vger.kernel.org`` 是候选提示，不保证自动接受。
#. Stable Maintainer 会判断目标版本、依赖、风险和 Patch 是否已在上游。
#. Mainline Patch 依赖新 API 时，旧 Stable 版本可能无法直接 Cherry-pick。
#. Backport 应保留原问题和修复语义，同时适配旧版本对象和调用路径。
#. 解决冲突不等于完成 Backport；必须重新构建和运行目标 Stable 版本。
#. 不应为让 Patch 易于 Backport 而破坏 Mainline 的正确设计。
#. 长期维护还包括后续 API 演进、硬件报告、文档和测试更新。
#. 新增参数、Quirk、导出符号和 UAPI 会形成长期维护承诺。
#. 一个短期方便的接口可能多年限制内部重构，因此 Review 会严格检查接口必要性。
#. 贡献者应准备解释为什么现有子系统抽象不足，而不是默认增加新控制面。
#. 新代码应遵循已有对象模型、锁规则、错误码和生命周期惯例。
#. 局部复制现有代码可能带来重复 Bug，应优先复用稳定 Helper 或抽象。
#. 新抽象只有在多个真实用户和清晰边界存在时才有价值。
#. 文档和测试属于 Patch 的维护资产，不是代码通过后可省略的附属品。
#. 回归测试应在旧代码上触发问题，在修复后通过，证明其覆盖真实失败模式。
#. 一次手工复现消失不能替代自动回归资产。
#. 修复内部逻辑可增加 KUnit；修复用户可见行为可增加 kselftest；复杂路径可保留专用 Reproducer。
#. 安全、硬件或时序问题可能无法进入通用测试，仍应保存可重复测试步骤和环境。
#. 上游贡献需要接受公开讨论、修改方案和放弃局部实现的可能。
#. Maintainer 拒绝一个方案不等于否认问题，可能表示抽象、风险或维护成本不合适。
#. 作者应把 Review 结果沉淀回对象模型、测试和 Commit History。
#. 补丁长期无响应时，应重新检查路由、说明、测试、时机和是否已有替代方案。
#. 合理跟进应保留 Thread，不应不断创建新的无关联版本。
#. 最终确认合入应检查目标 Git Tree，而不是仅依赖邮件回复。
#. 最终确认 Stable 回灌应检查具体 Stable Branch 和发布版本。
#. Upstream Contribution 的成功标准不是 Patch 发出，而是问题以可维护方式进入正确历史并持续不破坏用户。
#. 稳定上游化顺序是：本地症状 → 根因和对象不变量 → 通用最小修复 → 测试矩阵 → 逻辑 Patch → 正确路由 → Review/Reroll → Maintainer Tree → Mainline → Stable/长期跟进。

必背路径
--------

本地改法上游化：

::

   本地症状消失
   → 重新确认真实问题和第一条失败路径
   → 重建对象所有权 / 同步 / 状态机
   → 去除硬编码、旁路和临时调试依赖
   → 形成适用于明确范围的最小修复
   → 保持 ABI、错误码和正常路径
   → 编写自包含 Commit Message 与测试证据

提交和跟进：

::

   Build / KUnit / kselftest / Hardware / Static Checks
   → MAINTAINERS 与子系统规则
   → Patch Mail
   → Review 与 v2/v3
   → Maintainer Tree
   → linux-next
   → Mainline -rc
   → 用户回归反馈
   → Stable Backport 或后续修复

必须区分
--------

* Local Hack 恢复当前环境，与 Upstreamable Fix 恢复通用不变量。
* 本地症状消失，与根因已修复。
* 构建通过，与运行和错误路径正确。
* Mock/VM 覆盖，与真实硬件覆盖。
* Mainline 修复，与 Stable Backport。
* ``Cc: stable`` 候选提示，与 Stable 已接受。
* Patch 已发送，与贡献已完成。
* 一次测试通过，与长期维护责任结束。

一句话结论
----------

把本地修补变成上游贡献，必须将局部现象还原为通用对象不变量，用可审查的最小 Patch 和风险匹配的测试证明修复，并持续跟进到主线、回归和 Stable 生命周期。
