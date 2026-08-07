第051章：色彩理论与色彩空间
==========================

核心知识点
----------

RGB 数值必须绑定完整颜色语义
   一个 RGB 三元组只有同时明确 primaries、white point、transfer function 和 reference state 才有确定含义。sRGB、Display P3、Rec.2020、ACEScg 即使都使用 RGB，色域、白点、编码和工作目标也并不相同。

颜色管线要区分 scene-referred 与 display-referred
   PBR 光照、中间 HDR buffer、bloom 和多数合成处理的是场景线性信号；tone mapping、gamut mapping 与最终 transfer function 才开始面向具体显示设备。工作空间不能与显示空间混为一谈。

sRGB 是存储/显示编码，不是光照计算空间
   Base color、emissive 等颜色纹理常按 sRGB 存储，采样时应解码为 linear RGB；normal、roughness、metallic、AO、height、mask 等数据纹理必须保持线性数值语义。光照、混合、mipmap、blur 和 temporal accumulation 都应在正确线性空间中进行。

GPU 纹理格式本身就是颜色合同的一部分
   ``*_SRGB`` texture view 可以在采样边界完成 sRGB decode，最终 sRGB render target 可以在写出时完成 encode。若硬件已经转换，shader 再手动转换会形成 double decode/encode；若资源格式没有声明颜色语义，shader 又默认线性，结果同样会偏离。

宽色域主要改变可表达色域
   Display P3 比 sRGB 覆盖更多饱和颜色，Rec.2020 更宽。工作空间中的颜色若超出目标显示 gamut，需要 gamut mapping；直接逐通道 clamp 会破坏 hue、saturation 与局部层次。

ACEScg 属于高动态范围工作空间
   ACEScg 是 scene-linear、宽色域的 CGI/VFX 工作空间，适合跨素材渲染与合成。它不是最终显示编码，数值可以大于 1，也可能在颜色转换中出现负值。实时引擎即使不用 ACEScg，也应保留“工作空间”和“输出空间”的分层思想。

HDR 正确性依赖浮点中间缓冲
   Scene-linear lighting、emissive 与高亮应在 FP16/FP32 等 HDR buffer 中保留大于 1 的范围。若中途写入 8-bit UNORM、提前 sRGB encode 或 clamp，高光层次一旦丢失，后续 tone mapping 和 bloom 无法恢复。

系统颜色管理属于渲染链的最后一段
   同一 swapchain 内容在不同显示器、ICC profile、HDR 模式、浏览器、截图工具中可能表现不同。最终颜色问题必须区分 raw GPU resource、应用输出、系统合成器和显示设备四层。

关键路径
--------

SDR 颜色路径：

::

   source asset + color metadata
   → texture format / sRGB decode
   → scene-linear RGB
   → PBR lighting / blending / filtering
   → HDR floating-point buffer
   → exposure / tone mapping
   → gamut mapping to sRGB
   → sRGB encode
   → SDR swapchain / display

HDR / 宽色域路径：

::

   source asset
   → decode to working linear space
   → HDR lighting / composition
   → rendering transform
   → gamut mapping to target primaries
   → HDR transfer / reference-white mapping
   → HDR-capable surface
   → OS compositor / display

颜色异常排查：

::

   先确认素材语义
   → 检查 texture view 是否 sRGB / linear
   → probe shader 中间值
   → 检查 lighting 是否在线性 HDR 中进行
   → 检查中间 buffer 是否保留 >1 高光
   → 检查 tone/gamut/output transform
   → 最后检查系统 profile 与显示模式

概念辨析
--------

* **sRGB 与 linear RGB**：sRGB 是非线性编码；linear RGB 才适合能量运算。二者可能共享 primaries，但数值含义不同。
* **Color texture 与 data texture**：base color 是颜色信号，需要颜色空间解释；normal、roughness 等是参数数据，不应套用 sRGB transfer。
* **Display P3 与 Rec.2020**：二者主要定义更宽的色域，不等于“自动 HDR”。动态范围还取决于 transfer function、reference white 和显示链路。
* **Working space 与 output space**：前者服务渲染与合成，后者服务设备呈现。ACEScg 属于前者，sRGB/P3/HDR10 surface 属于后者。
* **Tone mapping 与 gamut mapping**：tone mapping 主要压缩亮度动态范围；gamut mapping 处理颜色超出目标色域的问题。
* **Shader 数值与屏幕观感**：shader 中数值正确不保证最终显示正确，swapchain color space、系统色彩管理和面板特性仍会改变呈现。

本章结论
--------

颜色问题应按“素材语义—GPU 解码—线性工作空间—HDR 中间缓冲—输出变换—显示设备”理解。最重要的边界是颜色纹理与数据纹理分离、所有光照和混合在线性空间进行、高光在浮点 buffer 中完整保留，以及 SDR/HDR 分别使用匹配的 gamut 与 transfer。只要每个 RGB 数值都能回答“它属于哪个空间、是否线性、面向场景还是显示”，颜色管线就具备可验证性。