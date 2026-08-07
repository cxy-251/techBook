第054章：感知指标、Gamma 与显示校准
================================

核心知识点
----------

视觉质量判断必须同时覆盖信号路径与显示路径
   一帧图像从 linear HDR、tone mapping、transfer function、文件编码、系统颜色管理到具体面板会经历多个变换。最终“偏暗、偏饱和、banding、指标很好但观感差”不能只从 shader 或单个截图解释。

人眼对误差的敏感度并不均匀
   同等数值误差在暗部、平滑渐变、品牌色、肤色和运动边缘中更容易被看见，在复杂纹理和噪声区域中可能被掩盖。感知判断必须同时考虑亮度、局部对比、颜色、空间频率和时间变化。

线性空间负责物理计算，transfer function 负责编码与呈现
   Lighting、alpha blend、filter 和能量累积应使用 linear 数据；sRGB、BT.1886、PQ、HLG 等 transfer function 处理数值到显示响应的映射。缺失或重复 encode/decode 会系统性改变中间调、渐变与 blur 权重。

sRGB 不是简单 ``gamma 2.2``
   它使用分段 transfer function。工程实现应优先让 sRGB texture/render-target format 完成标准转换；手写转换只适合明确控制的路径。若硬件已 decode，shader 再做一次 ``srgbToLinear`` 会让颜色过暗。

PSNR、SSIM、Delta E 回答不同问题
   PSNR 看像素误差能量，适合批量回归；SSIM 更关注亮度、对比与结构；Delta E 用于颜色差异。任何指标都不能单独覆盖时间稳定、HDR 显示、局部语义和系统色彩管理。

指标输入空间必须固定
   在 linear HDR 上计算 PSNR 与在 tone-mapped sRGB 截图上计算，回答的是不同问题。SSIM 使用 luma 还是 RGB、Delta E 使用哪个 white point 与感知空间，都必须写进 QA 合同，否则数值无法横向比较。

局部问题需要区域化指标
   全图平均很容易稀释暗部 banding、UI 品牌色、霓虹偏色和局部 ghosting。应结合 mask、histogram、difference view、局部 PSNR/SSIM、Delta E 和时间差分，把异常区域单独评估。

显示校准决定同一信号如何被设备呈现
   White point、gamut、peak brightness、black level、EOTF、ICC/display profile 和系统 HDR 状态都会影响观感。广色域显示器若把 sRGB 内容错误当作 P3 解释，会产生明显过饱和。

截图、浏览器和视频不是同一输出链
   GPU raw resource、应用截图、带 profile PNG、浏览器 canvas、录屏视频和播放器可能使用不同 bit depth、range、metadata 与 color management。若引擎截图正常而视频异常，应优先把问题移到编码/播放器链路，而不是继续改 shader。

测试图案是颜色排查的最小证据集
   灰阶 ramp 检查 transfer 与中间调，暗部阶梯检查 bit depth/banding，饱和色块检查 gamut/profile，棋盘混合检查 linear blend。固定测试图案比直接在复杂游戏画面里猜颜色更可靠。

关键路径
--------

显示差异排查：

::

   固定显示器 / OS profile / HDR mode / app path
   → 保存 linear HDR buffer
   → 保存 tone-mapped linear
   → 保存 final encoded output
   → 比较 app screenshot / browser / video frame
   → 检查 transfer / bit depth / range / profile
   → 检查 display gamut / white / EOTF
   → 用同一测试图案复测

指标选择：

::

   先确定视觉问题类型
   → 像素误差: PSNR / MSE
   → 结构损失: SSIM
   → 颜色偏移: Delta E
   → 局部异常: mask + histogram + region metric
   → temporal artifact: 连续帧差分 / motion-area metric
   → 明确输入空间与参考图

Gamma / transfer 排查：

::

   检查 texture 是否已 sRGB decode
   → 检查 shader 是否重复转换
   → 检查中间 pass 是否在线性空间 filter/blend
   → 检查 final encode 是否恰好一次
   → 检查 swapchain / screenshot / browser profile

概念辨析
--------

* **Gamma 与 transfer function**：gamma 是常用近似说法；sRGB、PQ、HLG 等实际有各自明确 transfer 规则。
* **Linear value 与 displayed brightness**：shader 中的线性值并不直接等于用户看到的亮度，输出 EOTF/显示设备还会继续解释。
* **PSNR 与感知质量**：高 PSNR 只能说明平均像素误差小，不代表局部颜色、banding 或 temporal artifact 不明显。
* **SSIM 与 Delta E**：SSIM 偏结构，Delta E 偏颜色；两者解决的问题不同。
* **Color management 与 shader bug**：同一 raw output 在不同设备上差异明显时，应优先检查 profile/gamut/display path，再判断 shader。
* **Wide gamut 与 HDR**：广色域描述颜色范围，HDR描述亮度/动态范围与传递语义，二者可以组合但不是同一能力。
* **截图正确与显示正确**：截图文件正常只证明导出内容可能正确，不证明 OS 合成器和面板呈现一定正确。

本章结论
--------

感知调试应按“线性信号—transfer—指标—输出文件/平台—显示设备”拆分。不要用单一 PSNR 或最终肉眼观感直接归因；先固定观察条件和输入空间，再用灰阶、暗部、饱和色与棋盘图建立基线，然后结合区域化 PSNR/SSIM、Delta E 与显示 profile 逐层验证。只有指标、颜色空间和设备状态都被记录，跨平台画质差异才具备可复现性。