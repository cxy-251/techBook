Constraint Validation, Form State, and User Feedback
====================================================

核心知识点
----------

* 浏览器 constraint validation 负责提交前快速反馈：``required``、``type``、``pattern``、``min/max``、``step``、``maxlength`` 与 ``setCustomValidity()`` 都在 browser boundary 内工作。
* 原生校验改善 UX，服务器校验建立信任。身份、权限、CSRF、唯一性、价格、库存、配额和数据库约束必须在服务器再次判断。
* Form state 不只有字段值，还包括 dirty、touched、validity、pending、field error、submitter、autofill、disabled/readonly 状态与 history restoration。
* 反馈时机决定可用性：简单格式问题可以尽早提示，复杂业务错误通常在提交后返回；错误必须告诉用户“哪里错、当前是否保存、下一步怎么做”。
* ``disabled``、``readonly``、``hidden``、``required`` 语义不同：disabled 控件通常不提交，readonly 通常仍提交，hidden 可提交但不可见，required 参与约束校验。
* 可访问错误需要和字段建立语义连接，例如 label、``aria-describedby``、``aria-invalid`` 与合理 focus management；颜色不能成为唯一信号。

关键路径
--------

``User edits field → Browser control state → Constraint validation → Optional client feedback → Form submit → Server revalidation/auth/business rules → Database constraints → Field/form result → Semantic error mapping + focus/retry``

排查“前端通过但保存失败”时，应先判断失败属于浏览器约束、服务器业务规则还是数据库并发约束；三层可以检查同一字段，但拥有不同可信度和恢复责任。

概念辨析
--------

* **Validity vs trust**：``valid`` 只说明当前控件满足客户端约束，不说明服务器允许该 mutation。
* **Dirty vs touched**：dirty 表示值发生改变，touched 表示用户与字段发生过交互；二者用于控制不同反馈时机。
* **Field error vs form error**：字段错误指向可修正输入；权限失效、服务器超时等应作为 form/global error 表达。
* **Disabled vs readonly**：disabled 会改变提交 entry list；readonly 更适合“可提交但不可编辑”的值。
* **Native feedback vs custom feedback**：自定义 UI 可以改善一致性，但仍应保留正确控件语义和无脚本时可理解的服务器结果。

本章结论
--------

稳定表单反馈需要三层协作：浏览器快速发现局部输入问题，服务器裁决可信业务状态，应用把 pending、错误与恢复过程映射回可操作 UI。不要把客户端校验当作安全边界，也不要把所有错误压成一个布尔值。