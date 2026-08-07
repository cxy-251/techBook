第044章：Import Failure、Finder/Loader Contracts 与 Diagnostics
================================================================

核心知识点
----------

* 导入失败应按阶段分类：缓存/名字解析 → finder 查找 → ``ModuleSpec`` → loader 加载 → 模块顶层执行 → 导入后的属性访问。
* ``ModuleSpec`` 是 finder 与 loader 之间的加载合同；它描述模块名、来源、加载器、缓存位置和 package 搜索位置。
* ``importlib.util.find_spec(name)`` 适合验证“导入系统能否形成加载计划”，但 spec 存在不代表模块执行一定成功。
* 顶层模块查找的 path 通常为 ``None``；子模块查找依赖父 package 的 ``__path__``。子模块失败时必须同时检查父包状态。
* finder 无法处理当前名字时应返回 ``None`` 让后续 finder 继续；自定义 finder 的异常会直接改变导入结果。
* 现代 loader 的核心协议是 ``create_module(spec)`` 与 ``exec_module(module)``；``exec_module`` 负责把代码执行进 module namespace。
* 导入系统会在 ``exec_module`` 前把 module 放入 ``sys.modules``；执行失败后会清理当前失败模块缓存项，但成功导入的依赖模块可能保留。
* ``ModuleNotFoundError`` 通常指向搜索/父包上下文问题；``ImportError`` 的来源更广，既可能来自 loader，也可能是模块代码主动抛出。
* 模块顶层抛出的 ``RuntimeError``、``ValueError`` 等普通异常会保留原类型传播，说明模块已经找到并进入执行阶段。
* ``AttributeError: module has no attribute ...`` 通常说明 module object 已经存在，问题进入 namespace/初始化顺序或导入后接口检查层。
* “partially initialized module” 是循环导入的强证据：module 已缓存，顶层代码尚未完成，目标名字尚未绑定。
* 自定义 finder/loader 必须保持 ``spec.name``、package ``submodule_search_locations``、loader 能力和实际 module 状态一致。
* import side effects 发生在模块顶层执行阶段；环境变量读取、注册表修改、文件 I/O、线程启动等都会受首次导入时机控制。
* ``from x import y`` 会复制当前对象引用到调用方，后续 reload 或重新绑定不能自动更新这些外部引用。
* ``importlib.invalidate_caches()`` 适用于“新文件已出现但 finder 仍看不到”等搜索缓存问题；它不能修复顶层代码异常或循环依赖。
* 诊断时应保留原始 traceback 和 exception chaining；只把所有 ``ImportError`` 包成统一业务异常会损失关键阶段证据。

关键路径
--------

诊断主路径：

::

   requested fullname
       ↓
   inspect sys.modules
       ↓
   verify parent package and parent.__path__
       ↓
   find_spec(fullname)
       ↓
   inspect spec.name / origin / loader / submodule_search_locations
       ↓
   import module
       ↓
   if import fails: read original traceback and execution point
       ↓
   if import succeeds but API missing: inspect module.__dict__
       ↓
   check circular import / reload / stale external references

失败阶段：

::

   no spec
       → search configuration problem

   spec exists, loader fails
       → loader / extension / format contract problem

   loader executes module, top-level code raises
       → module execution problem

   module returned, expected attribute missing
       → module API / initialization-order problem

概念辨析
--------

* **查找失败与执行失败**：``find_spec`` 返回 ``None`` 属于搜索失败；有 spec 后模块顶层抛错属于执行失败。
* **``ModuleNotFoundError`` 与 ``AttributeError``**：前者通常还没得到目标 module；后者往往已经得到 module，只是目标绑定不存在。
* **finder contract 与 loader contract**：finder 必须给出正确 spec；loader 必须按 spec 创建/执行并填充 module。
* **父包失败与子模块失败**：``pkg.child`` 的搜索范围来自 ``pkg.__path__``，不能只检查 child 文件是否存在。
* **import failure 与插件接口失败**：``import_module`` 成功后 ``getattr(module, 'load')`` 失败已经不是搜索问题。
* **循环导入与路径错误**：循环导入中 finder/loader 可能完全正常，失败来自 module namespace 的时序。
* **缓存失效与 module reload**：finder cache 决定能否发现来源；module cache/reload 决定现有运行时对象状态。
* **异常包装与根因保留**：业务层可以转换异常，但应通过 ``raise ... from exc`` 保留导入链和原始阶段证据。

本章结论
--------

导入诊断最有效的方法是先定位失败阶段，再看对应对象证据。搜索阶段检查 ``sys.meta_path``、``sys.path``、父包 ``__path__`` 与 ``find_spec``；加载阶段检查 ``ModuleSpec`` 与 loader；执行阶段阅读模块顶层 traceback 和 ``sys.modules`` 中间态；导入后接口失败则检查 ``module.__dict__`` 与循环依赖。只看异常名称容易把路径、loader、模块代码和半初始化状态混在一起，按阶段追踪才能得到稳定结论。