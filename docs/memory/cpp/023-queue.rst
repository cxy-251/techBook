第023章：Queue
==============

核心知识点
----------

* ``std::queue<T, Container>`` 是 FIFO（First-In First-Out）容器适配器：元素从队尾进入，从队首读取和删除。
* 核心接口是 ``push`` / ``emplace``、``front``、``back``、``pop``、``empty``、``size``；适配器不提供 iterator 和中间位置操作。
* 常见转发关系是：``push() → c.push_back()``、``front() → c.front()``、``back() → c.back()``、``pop() → c.pop_front()``。
* 默认底层容器是 ``std::deque<T>``，因为 deque 同时高效支持尾部插入和头部删除。
* 可替换底层容器必须提供 ``front``、``back``、``push_back``、``pop_front``，且 ``value_type`` 与 ``T`` 一致；``std::list`` 可用，``std::vector`` 因没有 ``pop_front`` 不满足条件。
* ``front()`` 和 ``back()`` 返回容器内部元素引用；``pop()`` 删除队首且返回 ``void``。需要消费队首对象时，应先复制或移动，再 ``pop``。
* ``pop`` 完成后，原队首对象生命周期结束，任何指向它的引用、指针或别名立即失效。
* ``std::queue`` 只表达 FIFO 顺序，不提供线程同步、容量上限、背压或阻塞等待；这些属于队列之外的并发与系统设计层。

关键路径
--------

FIFO 主路径：

``push(value)`` → 底层 ``push_back`` 在队尾构造对象 → ``back`` 指向最新元素 → ``front`` 仍指向最早未消费元素 → ``pop`` 调用 ``pop_front`` → 队首对象析构 → 下一个元素成为新队首。

消费 move-only 或高成本对象时，稳定顺序是：

::

   while (!q.empty()) {
       T value = std::move(q.front());
       q.pop();
       consume(std::move(value));
   }

这里移动之后，原队首对象仍存在但处于 moved-from 状态；``pop`` 才真正结束其生命周期。

概念辨析
--------

* **queue 与 deque**：queue 定义 FIFO 行为；deque 只是默认存储实现。两者不是同一种抽象层级。
* **front 与 pop**：``front`` 读取队首引用，``pop`` 删除队首；先 ``pop`` 再访问原引用会形成悬垂访问。
* **queue 与 vector**：vector 缺少 ``pop_front``，无法直接满足 queue 的底层接口；用 ``erase(begin())`` 模拟会引入线性搬移成本。
* **FIFO 与优先级队列**：queue 按到达顺序处理；priority_queue 按比较器定义的优先级处理。
* **FIFO 与并发队列**：``std::queue`` 不负责线程安全。多生产者/消费者场景还需要 mutex、condition_variable、并发容器或其他同步机制。
* **容量与顺序**：标准 queue 没有容量上限；有限缓冲、背压和丢弃策略必须由外层显式实现。

本章结论
--------

``std::queue`` 的稳定模型是“尾部写入、头部读取与删除”。源码阅读时将 ``push/front/back/pop`` 还原为底层容器端点操作即可。默认 deque 提供均衡的两端能力；list 可替换但付出节点成本；vector 不满足 ``pop_front`` 条件。工程上先确认业务确实是 FIFO，再单独处理同步、容量和背压问题。
