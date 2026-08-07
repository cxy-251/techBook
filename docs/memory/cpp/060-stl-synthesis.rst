第060章：STL Synthesis
=====================

核心知识点
----------

* STL 可以压缩成五个角色：容器负责拥有对象和维护结构不变量；iterator/range 暴露遍历边界；算法消费这些能力；allocator 改变内存来源；traits/concepts 在编译期描述类型能力和约束。
* 容器与算法解耦的关键不是“算法完全不知道容器”，而是算法只依赖 iterator/range 能力。``ranges::sort`` 仍要求随机访问和可排序语义，``list`` 因能力不足不能直接满足该接口。
* view 是延迟观察层，不拥有源数据。``filter``、``transform`` 等 adaptor 构造时主要保存源 range、callable 和少量状态，真正筛选与转换发生在迭代时。
* ``pmr`` 把运行时内存策略注入容器；``pmr::vector<pmr::string>`` 中既要看 vector 元素数组，也要看每个 string 的字符缓冲是否使用同一 resource。
* traits 与 concepts 都是编译期信息入口：traits 常用于提取关联类型、属性和策略；concepts 把可用操作和语义要求直接写到模板接口上。
* 比较器、谓词、projection、allocator 都是策略对象，它们被注入 STL 主循环；算法负责控制流程，策略对象负责类型或业务规则。
* 生命周期、异常安全、iterator 失效和复杂度是所有 STL 子系统最终汇合的工程边界；任何接口分析都应落回这些维度。
* 现代 STL 的演进方向是让范围、约束、view、constexpr 和运行时内存策略更显式，但底层对象生命周期和数据结构不变量没有被取消。

关键路径
--------

接口调用 → 找拥有者与存储 → 确定 iterator/range 边界 → 检查算法所需能力 → 展开 comparator/predicate/projection → 如涉及分配则追踪 allocator/resource → 用 traits/concepts 解释编译期选择 → 检查对象移动、失效、异常和生命周期 → 得到工程结论。

以 ``pmr::vector<pmr::string> + views + ranges::sort`` 为例：resource 提供存储 → vector/string 拥有对象 → view 观察 names → ranges algorithm 获取 begin/end 与随机访问能力 → projection 生成排序键 → comparator 建立严格弱序 → 排序移动/交换元素 → view 再次遍历时观察排序后的源对象。

概念辨析
--------

* **容器 vs algorithm**：容器维护数据结构与生命周期；算法只在给定能力范围内处理元素，不接管所有权。
* **iterator/range vs view**：iterator/range 描述遍历边界与能力；view 是一种可组合、通常非拥有且延迟求值的 range。
* **allocator vs traits**：allocator 影响运行时存储来源；traits 提取编译期类型事实，二者处在不同层级。
* **traits vs concepts**：traits 常提供类型和值供实现继续分发；concepts 把约束直接组织成模板接口条件。
* **projection vs transform view**：projection 只在某次算法比较/访问前提取键；transform view 建立持续可遍历的变换范围。
* **接口简洁 vs 底层复杂度消失**：ranges、views、pmr 让表达更集中，但分配、比较、移动、遍历和生命周期成本仍然存在。

本章结论
--------

掌握 STL 的标准方法不是记住更多 API，而是形成统一模型：谁拥有对象，谁只定位或观察，算法需要什么能力，内存从哪里来，编译期信息如何控制实现路径，最后哪些操作会改变生命周期、位置有效性和复杂度。能按这条链分析，就能迁移到不同容器、算法和标准库实现。