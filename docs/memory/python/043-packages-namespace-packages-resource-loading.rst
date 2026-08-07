第043章：Packages、Namespace Packages 与 Resource Loading
==========================================================

核心知识点
----------

* package 的运行时定义是“带 ``__path__`` 的 module object”；目录只是常见来源，package 语义最终体现在 module 元数据和搜索路径上。
* 普通 package 通常由带 ``__init__.py`` 的目录形成，导入 package 时会执行 ``__init__.py``，结果写入 package namespace。
* 子模块搜索使用父包的 ``__path__``，因此 dotted import 是逐层建立 package/module 对象与搜索范围的过程。
* 成功导入子模块后，导入系统会把子模块绑定为父 package 的属性，并与 ``sys.modules`` 中对应 fully qualified name 保持一致。
* ``__init__.py`` 是 package initialization point；重 I/O、插件扫描和不可控副作用放在这里会让所有子模块导入承担成本。
* namespace package 允许多个物理位置共同贡献同一个逻辑 package 名称，不需要统一 ``__init__.py``。
* namespace package 仍是 module object，仍有 ``__path__``；差别在于 ``__path__`` 可聚合多个 portion，并由 import machinery 动态维护。
* 同一 namespace package 的不同 portion 可以分别提供不同子模块，适合插件和拆分发行包。
* namespace package 没有天然统一初始化点，因此共享 registry、顺序敏感初始化和全局副作用应放在显式模块或入口函数中。
* relative import 依赖当前 module 的 package context，主要来自 ``__package__`` 与 ``__spec__``，不是根据物理文件相邻关系解析。
* 包内文件直接运行成 ``__main__`` 时可能丢失 package context；``python -m package.module`` 能让 import machinery 建立正确模块身份。
* package resource 应通过 ``importlib.resources`` 等 package-aware API 访问，不能假设资源一定存在于普通文件系统目录。
* ``importlib.resources.files(anchor)`` 返回资源抽象入口；资源可能来自目录、zip 或其它 loader 支持的来源。
* ``as_file()`` 用于在确实需要真实 ``Path`` 时临时 materialize 资源；调用方不能把临时路径生命周期误当作永久文件。
* 资源路径应表达所有权，尤其 namespace package 多 portion 场景中，应避免不同插件使用同名资源造成歧义。
* package data、Python module 和发行包是三个不同层级：import name 解决代码对象定位，resource API 解决包关联数据访问，distribution metadata 解决安装单元。

关键路径
--------

普通 package 子模块导入：

::

   import acme.plugins.csv_loader
       ↓
   load/reuse acme package
       ↓
   read acme.__path__
       ↓
   load/reuse acme.plugins package
       ↓
   read acme.plugins.__path__
       ↓
   locate and load csv_loader
       ↓
   sys.modules['acme.plugins.csv_loader']
       ↓
   acme.plugins.csv_loader attribute binding

资源访问路径：

::

   package/module anchor
       ↓
   importlib.resources.files(anchor)
       ↓
   Traversable resource tree
       ↓
   joinpath / iterdir / open / read_text / read_bytes
       ↓
   only if real filesystem path is required
       ↓
   as_file(...) temporary materialization

概念辨析
--------

* **module 与 package**：package 仍是 module；``__path__`` 是两者最关键的运行时差异。
* **regular package 与 namespace package**：regular package 通常有单一 ``__init__.py`` 初始化点；namespace package 聚合多个搜索 portion。
* **package name 与 distribution name**：可导入名称不必等于安装发行包名称，一个 namespace 可由多个 distribution 共同贡献。
* **相对导入与当前工作目录**：相对导入依赖 package context，当前工作目录只会间接影响 ``sys.path``。
* **资源与源码旁边的文件**：资源应视为 package-associated data，不应依赖 ``Path(__file__).parent`` 一定有效。
* **``files()`` 与 ``as_file()``**：前者提供资源抽象视图；后者只在需要真实文件系统路径时建立临时路径语义。
* **namespace package 与统一初始化**：namespace package 擅长聚合搜索空间，不提供天然单一初始化文件。

本章结论
--------

包系统的稳定模型是“package = module object + ``__path__`` 搜索边界”。普通包通过 ``__init__.py`` 建立包级状态，namespace package 通过多个 portion 聚合同一逻辑命名空间，相对导入通过 package metadata 解析名字，资源访问通过 package-aware API 跨越文件系统与 loader 差异。排查包问题时，依次检查 ``__name__``、``__package__``、``__spec__``、``__path__``、``sys.modules`` 和资源 anchor，而不是只查看目录结构。