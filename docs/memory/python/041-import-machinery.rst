第041章：Import Machinery
=========================

核心知识点
----------

* Import machinery 的核心链条是 ``finder → ModuleSpec → loader → module object``。
* finder 负责回答“给定 fullname 和搜索范围，是否能找到模块”；loader 负责创建或执行模块；``ModuleSpec`` 保存两者之间的加载合同。
* 对顶层模块，finder 的搜索范围通常来自 ``sys.path``；对子模块，搜索范围来自父包的 ``__path__``。
* ``ModuleSpec`` 常见字段包括 ``name``、``loader``、``origin``、``cached``、``submodule_search_locations`` 和 ``loader_state``。
* ``submodule_search_locations`` 是否存在，是判断某个 spec 是否代表 package 的重要信号。
* 现代 loader 的关键方法是 ``create_module(spec)`` 与 ``exec_module(module)``；普通情况下 ``create_module`` 可返回 ``None`` 让导入系统创建标准 module object。
* ``sys.meta_path`` 是导入搜索的第一层 finder 链；自定义 meta path finder 可以在路径搜索之前接管某些 fullname。
* 默认路径搜索通常由 ``PathFinder`` 承担；它进一步处理 ``sys.path`` 或 package ``__path__`` 中的 path entry。
* ``sys.path_hooks`` 负责把一个 path entry 转换成对应 path-entry finder；结果会缓存在 ``sys.path_importer_cache`` 中。
* ``importlib.import_module()`` 是动态导入完整模块名的常用高层入口；``find_spec()`` 更适合诊断“能否找到、由谁加载、来源在哪”。
* namespace package 可以把多个目录 portion 聚合成同一个逻辑 package；它不要求统一 ``__init__.py``。
* namespace package 的关键运行时状态是聚合后的 ``__path__``，而不是某一个固定目录。
* ``importlib.invalidate_caches()`` 会通知支持缓存失效的 finder 清理搜索缓存；它不等于清除 ``sys.modules``。
* 模块初始化阶段会先创建/缓存 module object，再交给 loader 执行；finder、loader 与初始化是三个不同故障层级。
* Python 没有把透明 lazy import 作为通用语言默认语义；延迟导入会改变错误出现时机、副作用发生时机和性能分布，必须显式设计。

关键路径
--------

搜索与加载主路径：

::

   fullname
       ↓
   sys.modules lookup
       ↓ miss
   iterate sys.meta_path
       ↓
   finder.find_spec(fullname, path, target)
       ↓
   ModuleSpec
       ↓
   loader.create_module(spec) / default module creation
       ↓
   initialize __spec__ / __loader__ / __package__ / __path__
       ↓
   insert module into sys.modules
       ↓
   loader.exec_module(module)
       ↓
   module namespace ready

路径搜索细化：

::

   PathFinder
       ↓
   sys.path or parent.__path__
       ↓
   sys.path_importer_cache
       ↓ miss
   sys.path_hooks
       ↓
   path-entry finder
       ↓
   find spec for fullname

概念辨析
--------

* **finder 与 loader**：finder 负责定位和描述；loader 负责创建/执行。
* **ModuleSpec 与 module object**：spec 是加载计划和元数据合同；module 是实际运行时对象。
* **``sys.meta_path`` 与 ``sys.path``**：前者是 finder 优先级链；后者只是 PathFinder 常用的一组路径输入。
* **``sys.path_hooks`` 与 meta path finder**：path hook 改变某种路径入口如何搜索；meta path finder 可以直接接管模块名解释。
* **``sys.path_importer_cache`` 与 ``sys.modules``**：前者缓存“路径入口对应哪个 finder”；后者缓存“模块名对应哪个 module object”。
* **普通 package 与 namespace package**：普通 package 通常执行 ``__init__.py``；namespace package 主要聚合多个搜索 portion。
* **``invalidate_caches`` 与 reload**：前者刷新 finder 的搜索视图；后者重新执行已导入 module；两者解决的问题不同。

本章结论
--------

Import machinery 的稳定阅读模型是“fullname 先经过缓存，再经过 finder 形成 ``ModuleSpec``，loader 根据 spec 创建并执行 module”。诊断时先看 ``sys.modules``，再看 ``find_spec()`` 的 ``loader/origin/submodule_search_locations``，最后看 loader 执行是否成功。自定义导入、namespace package、插件路径和动态文件发现都应明确自己改变的是 meta path、path entry、spec、loader 还是 module initialization。