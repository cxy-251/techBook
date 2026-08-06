第183章：kselftest 与用户态驱动的内核测试
=========================================

核心知识点
----------

kselftest 验证用户态可见契约
   它从普通进程可触达的 Syscall、Ioctl、Netlink、Socket、Procfs、Sysfs、BPF、Cgroup、Namespace 和权限接口进入内核，检查返回值、Errno、事件和状态语义。

测试源码与运行内核是两个版本对象
   测试程序来自某个内核源码树，真正被验证的是当前启动内核。两者的 Commit、UAPI、Config 和工具版本必须记录，避免把版本不匹配误判为回归。

测试集合按子系统组织
   ``tools/testing/selftests/`` 下的 Target、Makefile、辅助程序和脚本共同定义测试范围。应先确定目标集合，再追踪实际运行项和用户入口。

构建、安装、执行和解析相互独立
   构建成功只证明测试程序可生成；安装成功只证明文件已部署；只有在目标内核上执行并完成断言，才证明契约得到验证。

Fixture 必须隔离宿主状态
   Namespace、Cgroup、Mount、Socket、BPF Object、qdisc、临时文件和设备配置应具有唯一作用域，并在成功、失败和 Timeout 后恢复。

权限前提必须显式表达
   Config、Architecture、Capability、LSM、Seccomp、硬件和文件系统能力决定路径是否可达。前提缺失应 ``SKIP``，行为违反合同则必须失败。

TAP/KTAP 描述测试结果结构
   Plan、Case 编号、``ok``、``not ok``、Directive 和 Diagnostic 便于 CI 解析。提前退出、Signal、Panic 和不完整 Plan 必须与普通断言失败分开处理。

用户态库可能改变观测边界
   C Library、VDSO、自动重试和兼容回退可能遮蔽原始系统调用结果。验证精确 Errno 或入口行为时，应确认测试实际经过的用户态封装路径。

异步测试需要有界同步
   多进程、多线程、Signal、Timer、Futex 和网络事件应使用明确状态、fd 或等待原语协调。固定 Sleep 既不能证明事件发生，也容易形成 Flaky Test。

高权限通过不等于安全合同正确
   Root 测试只能证明允许路径。权限测试还应使用普通 Credential、User Namespace 和有限 Capability 验证拒绝边界。

Kernel Log 是结果的一部分
   测试项显示 ``ok``，但运行期间出现 KASAN、KCSAN、Lockdep、WARN、Refcount 或 Oops，CI 仍应判定失败。

回归测试应固定稳定外部行为
   测试应断言返回值、Errno、事件、权限和文件语义，而不是依赖私有函数顺序或内部结构布局，使内核能够重构而不破坏用户合同。

关键路径
--------

kselftest 执行链：

::

   tools/testing/selftests Target
   → Makefile 构建程序和脚本
   → 可选安装测试包
   → 在目标内核上运行
   → 用户态接口进入内核
   → 收集 TAP / KTAP 与退出状态
   → 关联 Kernel Log 和环境元数据

用户契约验证：

::

   构造用户输入和 Credential
   → Syscall / Ioctl / Netlink / File / Socket
   → 内核对象路径执行
   → 返回值 / Errno / Event / State
   → 断言稳定 UAPI 行为
   → 清理临时对象和宿主状态

权限边界测试：

::

   建立允许主体与拒绝主体
   → 固定 User Namespace / Capability / LSM
   → 对同一对象执行同一操作
   → 验证允许路径成功
   → 验证拒绝路径返回预期错误
   → 确认没有扩大其它权限

概念辨析
--------

* **kselftest 与 KUnit**：kselftest 验证用户态合同；KUnit 验证内核内部逻辑和局部对象不变量。
* **测试源码版本与运行内核版本**：前者定义预期，后者提供实际行为；版本错配会造成假失败或错误解释。
* **构建成功与行为通过**：构建只验证工具链和依赖；运行断言才验证内核契约。
* **``SKIP`` 与 ``PASS``**：``SKIP`` 表示目标行为未执行；``PASS`` 表示路径已执行且断言成立。
* **TAP 结果与 Kernel Log 健康**：结构化结果描述 Case 状态；日志还能暴露测试未捕获的内核运行时违规。
* **Root 成功与非特权边界**：高权限成功不能证明普通主体被正确拒绝，也不能证明 Capability 范围最小。

本章结论
--------

kselftest 通过真实用户态入口固定 Linux 内核对外承诺的行为，使返回值、事件、权限和对象状态能够随每次内核修改持续回归验证。
