DOM Tree, Node, Element, Attribute, and Mutation
================================================

核心知识点
----------

* DOM 是 document 在浏览器中的运行时对象模型。HTML 只提供初始输入，脚本、框架和浏览器随后都围绕真实 DOM 对象读写状态。
* ``Node`` 是通用树节点抽象；``Document``、``Element``、``Text``、``Comment``、``DocumentFragment`` 承担不同树角色。``childNodes`` 与 ``children`` 的结果因此不同。
* Element 承载标签语义、attribute、选择器匹配和事件目标；Text 承载字符内容；Document 是当前文档入口；DocumentFragment 适合在提交到真实 document 前组织临时子树。
* HTML content attribute 与 DOM property 是两个层次。二者可能反射，也可能分别表示初始声明和当前运行时状态；表单 ``value``、``checked``、``disabled`` 等最容易暴露这种差异。
* DOM mutation 包括节点插入/删除、attribute 修改和文本变化。Mutation 会进一步影响 selector matching、style invalidation、layout、paint、事件路径和 accessibility tree。
* Framework 的 virtual DOM、signals、模板编译或响应式系统都只是上游调度模型；用户最终看到的变化必须通过真实 DOM commit 进入浏览器渲染与事件系统。

关键路径
--------

初始构建：

``HTML → Parser → Document / Element / Text nodes → DOM tree``

用户交互后的更新：

``User event → event target → JavaScript/framework state → DOM mutation → style/layout/paint/accessibility update → visible result``

Attribute/property 判断：

``initial HTML attribute → current DOM attribute → current DOM property → submitted/rendered behavior``

批量结构构建：

``create nodes → DocumentFragment → single document insertion → browser invalidation work``

调试时应区分 source、当前 DOM、DOM property 和浏览器下游计算结果，而不是把它们视为同一个状态。

概念辨析
--------

* **Node vs Element**：Element 是 Node 的一种；Text、Comment、Document 也是 Node，但不能按元素选择器处理。
* **``childNodes`` vs ``children``**：前者包含文本和注释等所有子节点；后者只包含 Element。
* **Attribute vs Property**：attribute 更接近声明和序列化状态；property 更接近当前对象运行时状态，具体反射规则由平台定义。
* **DOM mutation vs visual update**：修改 DOM 只是输入变化；浏览器还可能执行 style、layout、paint 与 composite 才形成新画面。
* **Virtual DOM vs DOM**：virtual DOM 是框架内部数据结构；真实 DOM 才是浏览器、事件、CSS、可访问性和渲染系统共享的状态边界。

本章结论
--------

DOM 是页面运行时的共享事实层。服务器输出、用户输入和框架状态只有映射到真实 DOM 后，才能影响浏览器的事件、样式、布局、可访问性和最终画面。排查页面问题时，应从真实节点、当前 attribute/property 和实际 mutation 开始，而不是停留在模板或组件抽象。