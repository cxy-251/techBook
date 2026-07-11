章节 manifest
===============

每个章节建立一个 TOML 文件，文件名与 RST 章节对应。

必需字段：

.. code-block:: toml

   id = "read-enters-vfs"
   book = "linux-kernel"
   question = "用户态 read() 如何进入 VFS"
   status = "planned"

   [source]
   source_id = "linux"
   commit = ""

   [evidence]
   lab = "labs/linux-kernel/read-enters-vfs"
   command = ""
   output = ""
   failure_case = ""

   [validation]
   lab_passed = false
   source_symbols_verified = false
   rst_audit_passed = false
   sphinx_passed = false

``status`` 只使用 ``planned``、``blocked``、``evidence-pending``、``writing`` 和 ``complete``。所有验证项为 true 后才能进入 ``complete``。
