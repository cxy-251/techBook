第074章：色彩管理
================

核心知识点
----------

色彩管理的目标是让颜色在输入、计算、显示和交付之间保持可解释关系
   RGB 数值只有绑定 primaries、white point、transfer function 和 reference state 才有明确语义。工程中最常见错误不是“颜色公式错”，而是某一段把同一组数值当成了不同色彩空间或不同显示条件。

Scene-Linear 是渲染计算的核心工作域
   光照、BRDF、透明混合、Bloom、滤波和大部分后处理中的能量相关运算应在 scene-linear 工作空间完成。Display-referred 编码适合观看、传输和调色交互，直接参与光照会破坏能量比例。

颜色贴图与数据贴图必须从导入阶段区分
   Albedo、base color、emissive 等颜色资源需要声明原始色彩空间并在 shading 前正确解码；normal、roughness、metallic、height、AO、depth、motion vector 属于 data，应保持数值语义。Normal map 被错误 sRGB decode 会直接扭曲方向。

sRGB 不是简单的 2.2 Gamma
   sRGB transfer 是分段函数。GPU 的 sRGB texture/view format 可以自动把存储码值解到 linear；输出端也可能通过 sRGB framebuffer/swapchain 进行编码。工程文档应写清 decode/compute/encode，而不是用“开 gamma”这种模糊描述。

Primaries 与 White Point 的转换通常在线性域完成
   P3、Rec.709、Rec.2020、ACEScg 等空间之间需要先处理 transfer，再通过矩阵与必要的 chromatic adaptation 转换 primaries/white point。若在非线性码值上直接套线性矩阵，会产生错误色相和亮度。

LUT 必须绑定输入域与输出域
   1D LUT 适合单通道曲线与 shaper，3D LUT 适合 RGB 耦合的 look、gamut mapping 与 film emulation。HDR scene-linear 直接进入只覆盖 ``0..1`` 的 3D LUT 会压缩高光，因此常需 shaper curve 把宽动态范围映射到有效采样域。

HDR Render Target 必须保留超出显示白的线性值
   ``RGBA16F``、``R11G11B10F`` 等浮点格式让灯光、高光、Bloom 和 exposure 保持可计算空间。过早 clamp 到 ``0..1`` 会永久损失金属反射、太阳、灯牌和体积高光层次。

Tone Mapping 与 View Transform 是输出链的一部分
   Tone mapping 负责动态范围压缩，view/output transform 还可能处理 gamut、white point 和 display encoding。内部 HDR buffer 不等于 HDR 显示输出；最终是否正确还取决于 swapchain format、color space、HDR metadata、OS compositor 和显示设备状态。

Display-Referred UI 通常应在输出映射附近合成
   普通字体、图标和品牌色是面向显示的资源，若直接进入 HDR scene-linear 并被 exposure/tone mapper 处理，亮度和颜色会漂移。只有真正属于世界光照的发光面板或全息元素才应作为 scene-linear emissive 进入主渲染路径。

设备校准与 Viewing Condition 是色彩合同的一部分
   同一文件在不同 profile、峰值亮度、环境光和 HDR 模式下会呈现不同。SDR、Display P3、HDR10 PQ 等目标必须记录 reference white、peak luminance、white point 与 display profile，审片设备和制作软件应共享同一输出假设。

截图路径必须单独验证
   GPU backbuffer、OS compositor、截图 API、文件编码和查看器是不同阶段。HDR buffer 正常而 PNG 截图丢高光时，问题可能只在 HDR→SDR 映射；wide-gamut 屏幕更红时，优先查文件 profile 与 viewer，而不是立即修改 shader。

生产环境需要单一色彩配置源
   DCC、renderer、engine、compositor、review player 与交付工具应共享 OCIO/show config 或等价 color manifest。输入标签、working space、view transform、LUT、SDR/HDR 目标和 screenshot/recording 规则都应来自同一配置，避免手工复制和口头 gamma 假设。

色彩问题应沿五段链路定位
   先检查输入资源标签，再检查 scene-linear 计算，再检查 tone/view transform，再检查平台 compositor/display profile，最后检查交付文件 metadata。只要找到第一处语义不匹配，就不需要在后续阶段用 LUT 或曝光继续补偿。

关键路径
--------

颜色资产到显示：

::

   source texture + color tag
   → GPU texture / view format
   → decode to scene-linear
   → shading / blending / HDR post
   → exposure / tone mapping
   → gamut / view transform
   → output transfer
   → swapchain / file encoding
   → compositor / display profile

数据贴图：

::

   normal / roughness / metallic / depth / motion
   → mark as data
   → no color transfer decode
   → shader numeric interpretation
   → derived lighting / geometry result

截图问题排查：

::

   inspect HDR render target
   → inspect post-tonemap target
   → inspect swapchain color space
   → inspect OS compositor
   → inspect screenshot file profile / bit depth
   → inspect viewer color management

概念辨析
--------

* **Scene-Referred 与 Display-Referred**：前者描述场景光能关系，后者描述目标显示条件下的图像码值。
* **Gamma 与 Transfer Function**：Gamma 是泛称，sRGB/PQ/HLG 都有具体传递函数，不能用单一指数替代所有情况。
* **Color Texture 与 Data Texture**：前者需要颜色空间解释，后者只承载数值参数。
* **HDR Buffer 与 HDR Display**：浮点 HDR 中间纹理只是内部数据，HDR 显示还需要正确输出变换、swapchain 和设备模式。
* **Tone Mapping 与 Gamut Mapping**：前者主要压缩亮度动态范围，后者处理目标色域无法表示的颜色。
* **LUT 与 Color Space Transform**：LUT 可以承载 look 或部分变换，但必须明确输入/输出空间，不能脱离色彩合同单独使用。
* **Display Profile 与 View Transform**：view transform 生成目标显示信号，display profile/系统管理负责设备侧呈现，两层职责不同。
* **截图差异与渲染错误**：截图链本身可能重新编码或映射颜色，不能只凭截图差异判断 scene render 错误。

本章结论
--------

色彩管理应按“输入标签—scene-linear 工作空间—HDR 中间结果—tone/view transform—输出编码—设备呈现”理解。颜色资源和 data 资源从导入就要分流，所有能量计算保持在线性域，HDR 高光在输出阶段之前不得被无意截断。遇到偏灰、过饱和、截图丢高光或跨设备不一致时，沿输入、计算、输出、平台和设备五段链定位第一处语义错误，才能得到可复现的修正。