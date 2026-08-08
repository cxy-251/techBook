Internationalization, Locale, Direction, Unicode, and Semantic Presentation
============================================================================

核心知识点
----------

* Internationalization（i18n）不是字符串翻译，而是让同一系统能在不同语言、地区、书写方向、数字/日期格式和文化规则下保持正确语义与交互。
* Unicode 解决字符标识与编码基础，UTF-8 是现代 Web 的主流传输编码；字符正确解码只是第一层，字体覆盖、分词、排序、输入法和 grapheme cluster 仍属于更高层文本处理问题。
* ``lang`` 表达文档或局部内容的语言，影响辅助技术发音、拼写、翻译和某些 CSS/浏览器行为；locale 则是应用选择日期、数字、货币、排序等格式规则的上下文，两者相关但不等价。
* ``dir`` 与 CSS logical properties 决定 LTR/RTL 书写方向下的布局语义。使用 ``margin-inline-start``、``padding-inline-end`` 等逻辑属性比硬编码 left/right 更适合双向界面。
* Bidi 文本存在嵌套方向和隔离问题。用户生成内容、数字、URL、用户名和混合语言文本应依赖 ``dir="auto"``、``bdi`` 等平台语义，而不是手工插入不可见控制字符。
* 日期、数字、货币、复数和排序应通过 ``Intl`` 等 locale-aware API 处理；把格式化结果硬编码到模板会让显示规则和业务值混在一起。
* 本地化内容可能改变文本长度、换行、字体、布局尺寸和资源，因此 i18n 会进入 CSS、layout、font loading、accessibility 和测试边界。

关键路径
--------

文档语言路径：

``Server/Route locale → html[lang]/local metadata → browser text semantics → accessibility/spellcheck/translation → user``

格式化路径：

``canonical business value → locale selection → Intl formatter → localized text → DOM → layout``

双向布局：

``language/direction → dir + logical CSS → box/layout ordering → focus/reading order → visible UI``

混合文本：

``user content → bidi isolation/dir=auto → Unicode bidi algorithm → safe semantic presentation``

工程上应把业务事实与展示格式分开：数据库保存稳定值，应用根据请求或用户 locale 在显示边界格式化。

概念辨析
--------

* **Language vs Locale**：language 说明内容语言；locale 还包含地区化格式和文化规则，如 ``en-US`` 与 ``en-GB``。
* **Unicode vs UTF-8**：Unicode 定义字符与码点体系；UTF-8 是其字节编码方式之一。
* **Code point vs User-perceived character**：一个用户看到的字符可能由多个 code point 组成，字符串长度不能直接等同于字符数。
* **LTR/RTL vs left/right**：书写方向是语义维度；物理左右是屏幕坐标。逻辑 CSS 能随方向自动映射。
* **Translation vs Internationalization**：翻译是内容本地化；i18n 还包括编码、格式化、布局、输入、可访问性和资源策略。
* **Business value vs localized string**：金额、时间、数量等事实应保持规范化；localized string 只是用户展示层。

本章结论
--------

国际化是文档、文本、布局和数据展示共同参与的系统边界。稳定设计应以 Unicode 和语义 HTML 为基础，把语言、locale、方向和格式化明确建模，并让 CSS 与组件适应文本长度和书写方向变化，而不是把“翻译文案”当作最后一步补丁。