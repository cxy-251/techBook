第053章：Tone Mapping、HDR 与曝光控制
==================================

核心知识点
----------

Tone Mapping 是从场景信号走向显示信号的动态范围压缩
   它不是单纯“调好看”的滤镜，而是 scene-referred HDR 到 display-referred 输出之间的关键变换。输入仍是线性 HDR，高光可以远大于 1；输出开始服从 SDR/HDR 显示范围、transfer function 和目标设备。

曝光决定 tone curve 看到的信号尺度
   最简单的关系是 ``exposed = sceneColor * exposureScale``，一档曝光对应乘 2 或除 2。曝光应先把主体中灰放到合理区域，再让 tone mapper 分配暗部和高光；用 tone curve 去补偿错误曝光会让整条曲线失衡。

Middle gray 是曝光调试锚点
   ``0.18`` 常作为 scene-linear 中灰参考。主体若被推到 shoulder，画面容易发灰、过曝；若落入过重 toe，主体和暗部会一起压死。自动曝光也应围绕主体、直方图与时间平滑组织，而不是让少量极亮像素主导结果。

White point 与 shoulder 决定高光层次
   White point 过低，高光过快挤成白块；过高则高光压缩不足。Shoulder 应让车灯、霓虹、太阳等超亮区域逐渐接近显示白，同时保留颜色与亮度层次。

Toe、中间调、Shoulder 分别控制不同亮度区间
   Toe 决定暗部如何离开黑位；中间调斜率决定主体对比；shoulder 决定高光滚降。Washed-out、crushed、white clipping 等症状应分别映射到这三个区域，而不是统一归为“tone mapping 不对”。

Reinhard、Filmic、ACES-style 是不同取舍
   Reinhard 单调稳定、适合作基线；Filmic 提供更强 toe/shoulder 风格控制；ACES-style 实时曲线常追求自然高光和色彩响应。实时 ACES fitted curve 只是 shader 近似，不等同于完整 ACES Output Transform。

Bloom 应从仍保留高光层次的 HDR 信号提取
   通常先 exposure，再从 HDR 中做 threshold/soft-knee，然后 downsample、blur、upsample 和 composite。若 tone mapping 或 clamp 之后再提取 bloom，高光能量已经被压平；若 bright-pass 用低精度格式，也会形成白雾和色彩丢失。

SDR 与 HDR 输出必须走不同显示合同
   SDR 通常需要 tone mapping 到有限范围，再做 sRGB/gamut 输出；HDR10/scRGB 等路径还涉及 reference white、目标色域、transfer function、surface color space 和系统 HDR 状态。同一 RGB 数字在不同输出合同中对应不同可见亮度。

自动曝光是一条带历史状态的控制链
   Histogram 或 log-average luminance 给出目标 exposure，随后要排除极端亮暗值并进行时间平滑。Camera cut、室内外切换和大面积闪光都需要明确 adaptation 规则，否则曝光泵动会比单帧曲线问题更明显。

关键路径
--------

HDR 到显示：

::

   scene-linear lighting
   → floating-point HDR render target
   → auto/manual exposure
   → exposed HDR
   → bloom extraction / pyramid
   → tone mapping
   → bloom / grading composite
   → gamut + display transform
   → SDR sRGB 或 HDR surface

自动曝光：

::

   HDR luminance
   → histogram / log-average
   → reject extreme ranges
   → target middle-gray exposure
   → temporal adaptation
   → exposure scale
   → tone mapper input

发灰 / 压死排查：

::

   先看 tone-map 前 HDR 数值
   → 检查中灰与高光是否完整
   → 检查 exposure / metering
   → 对比 linear clamp / Reinhard / project curve
   → 检查 bloom source 与 composite
   → 检查 grading
   → 最后检查 SDR/HDR encoding 与系统显示状态

概念辨析
--------

* **Scene-referred 与 display-referred**：前者描述场景光照关系；后者已经绑定显示目标和观看条件。
* **Exposure 与 tone mapping**：exposure 改变进入曲线的输入尺度；tone mapping 决定这个尺度如何压入显示范围。
* **White point 与 reference white**：tone-curve white point 控制高光压缩位置；显示 reference white 是输出设备语义，两者相关但不是同一参数。
* **HDR buffer 与 HDR display**：内部 FP16 高动态范围渲染不等于最终使用 HDR 显示输出。
* **Bloom 与 clipping**：bloom 需要上游高光能量；已经被 clamp 的白块无法通过 bloom 恢复原始层次。
* **Filmic curve 与完整 ACES**：前者是一段实时映射曲线；完整 ACES 还包含工作色域、输出变换和显示编码。
* **发灰与过曝**：发灰可能来自曝光、中间调斜率、bloom 或双重编码；不能仅凭最终画面直接归因。

本章结论
--------

HDR 呈现应按“scene-linear HDR—曝光—高光提取—tone curve—显示变换”理解。排查时先证明 FP16 buffer 中暗部梯度、中灰和 >1 高光都存在，再检查 exposure 把主体放在哪个亮度区间，随后才调 toe、middle、shoulder、white point 与 bloom。最终 SDR/HDR 输出还必须匹配各自的 gamut、transfer 和系统 surface；只有这条链完整，亮度问题才能从主观调参变成可定位的数据问题。