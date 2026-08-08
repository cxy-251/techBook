第047章：Permission Enforcement in System Services
===================================================

核心知识点
----------

* Permission Enforcement Point 是实际作出允许、拒绝、受限或降级决定的位置；它可以出现在 Framework、IPC、Service、Kernel 或 Driver 边界。
* Framework 入口检查主要解决参数、API 可用性和开发者体验；真正的权威权限判断必须在系统服务或 daemon 侧再次执行。
* 服务端权限判断应依赖系统提供的调用者身份，而不是 App 自报的包名或字符串身份。
* Android 常组合 UID/PID、package、runtime permission、AppOps、SELinux、token；Apple 常组合 audit identity、bundle/code signature、entitlement、TCC、sandbox 和 session authorization。
* Entitlement 表示代码具备某类平台能力资格，TCC/运行时授权表示用户是否允许访问敏感数据；两者不是同一个层级。
* 权限通过后仍可能因资源占用、前后台限制、电源策略、设备状态或硬件故障失败；“有权限”不等于“调用必然成功”。
* 底层 sandbox、SELinux、文件权限、device node policy 是最后一道对象访问边界，服务端通过不代表内核必然放行。

关键路径
--------

标准权限路径：

``App API → Framework 快检 → IPC caller identity → Service 权威校验 → Policy store → Kernel/Sandbox → Resource``

敏感能力请求应按以下顺序判断：

#. 确认调用者真实身份，而不是信任 App 自报字段。
#. 查询安装身份、签名、runtime grant 或 entitlement。
#. 查询用户隐私授权、AppOps/TCC、前后台和设备管理策略。
#. 校验本次 session/token 是否仍有效。
#. 进入底层对象时继续经过 SELinux、sandbox、file/device permission 等检查。
#. 把拒绝、restricted、limited、temporary grant 或降级结果转换成稳定 API 语义。

概念辨析
--------

``Permission`` 与 ``Entitlement``：permission 多表达用户或系统授予的资源访问权；entitlement 多表达由代码签名绑定的平台能力资格。

``Framework Check`` 与 ``Service Check``：前者可被调用方绕过，主要用于早期反馈；后者位于可信边界，是权威判断。

``Identity`` 与 ``Authorization``：identity 回答“谁在调用”；authorization 回答“这个身份此刻能不能做这件事”。

``Denied`` 与 ``Unavailable``：denied 是授权失败；unavailable 是资源或系统状态失败。两类错误不能混淆。

本章结论
--------

移动 OS 的权限安全依赖服务端权威校验和底层对象边界共同成立。排查权限问题时，应沿“调用者身份 → 授权记录 → 服务策略 → session/token → 内核/沙箱”逐层确认，而不是只检查 App 是否曾弹出过权限对话框。