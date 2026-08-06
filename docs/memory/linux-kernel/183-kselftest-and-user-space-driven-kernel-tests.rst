第183章：kselftest 与用户态驱动的内核测试
=========================================

核心知识点
----------

kselftest 验证用户态可见合同
   测试从 Syscall、Ioctl、Netlink、Socket、Procfs、Sysfs、BPF、Cgroup 和 Namespace 等入口进入内核，检查返回值、Errno、事件与状态语义。

测试源码与运行内核必须配对记录
   测试程序来自某个源码树，真正被验证的是当前启动内核。Commit、UAPI、Config、Architecture 和工具版本不一致时，可能产生假失败。

构建、安装与执行是不同阶段
   构建成功只说明测试程序可生成，安装成功只说明文件已部署；只有在目标内核上执行并完成断言，才说明合同得到验证。

Fixture 必须隔离宿主状态
   Namespace、Cgroup、Mount、Socket、BPF Object、qdisc 和临时文件应拥有独立作用域，并在成功、失败与超时后恢复。

前提不足应 ``SKIP``，合同违反应失败
   Config、Capability、LSM、Seccomp、硬件和文件系统能力决定路径是否可达。缺少必要条件不等于测试通过。

稳定外部行为才是断言目标
   测试应固定返回值、Errno、事件、权限和文件语义，而不是依赖私有函数顺序或内部结构布局。

结构化结果必须结合内核日志
   TAP/KTAP 和退出状态描述测试项结果；KASAN、KCSAN、Lockdep、WARN、Refcount 或 Oops 仍可能使整次运行失败。

关键路径
--------

kselftest 执行链：

::

   tools/testing/selftests Target
   → 构建与安装
   → 在目标内核运行
   → 用户态接口进入内核
   → 收集 TAP / KTAP 与退出状态
   → 关联 Kernel Log 和环境信息

权限合同验证：

::

   构造允许主体与拒绝主体
   → 固定 Namespace / Capability / LSM
   → 执行同一操作
   → 验证允许路径
   → 验证拒绝路径
   → 清理宿主状态

概念辨析
--------

* **kselftest 与 KUnit**：kselftest 验证用户态合同；KUnit 验证内核内部函数和对象不变量。
* **测试源码版本与运行内核版本**：前者定义预期，后者提供实际行为；二者错配会影响结论。
* **构建成功与行为通过**：构建只验证工具链；运行断言才验证内核行为。
* **``SKIP`` 与 ``PASS``**：``SKIP`` 表示目标路径未执行；``PASS`` 表示路径已执行且满足断言。
* **Root 成功与权限边界**：高权限成功不能证明普通主体被正确拒绝，也不能证明 Capability 范围最小。

本章结论
--------

kselftest 通过真实用户态入口固定 Linux 内核对外承诺的返回值、事件、权限和对象状态。
