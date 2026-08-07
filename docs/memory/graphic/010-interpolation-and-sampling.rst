第010章：插值与采样
===================

核心知识点
----------

插值、采样与过滤承担不同职责
   插值在已有离散样本之间构造中间值；采样选择从连续或高分辨率信号中读取哪些位置；过滤把一个像素 footprint 覆盖的多个信息合成为输出。插值无法恢复采样时已经丢失的高频内容。

三角形属性使用透视校正插值
   光栅化器按 barycentric weights 生成 fragment 的 UV、颜色、法线和位置属性。透视投影下，默认 varying 需要结合 clip ``w`` 做 perspective-correct interpolation；直接在屏幕坐标中线性插值 UV 会造成纹理滑动和透视扭曲。

Aliasing 来自信号频率超过采样能力
   细纹理、锐利几何边界、阴影、高光和时间运动都包含高频成分。当屏幕、shadow map 或时间采样不足时，高频会折叠成锯齿、摩尔纹、爬行和闪烁。修复方向是提高采样率或在采样前降低信号频率。

像素 footprint 决定过滤尺度
   一个屏幕像素映射到纹理空间后可能覆盖一个 texel，也可能覆盖细长的大区域。隐式 texture LOD 通常依据 ``dFdx`` 与 ``dFdy`` 估计 footprint；程序化 UV、分支不连续或错误显式 LOD 会破坏这一估计。

Mipmap 是纹理缩小时的预过滤结构
   低 mip level 预先汇总高分辨率 texel，使远处像素读取与其覆盖范围相匹配。bilinear 只在单层四个邻近 texel 间过滤，trilinear 再混合相邻 mip 层，减少 LOD 切换；它们不能替代正确 mip chain。

各向异性过滤处理斜视角 footprint
   远处地面等斜面在 UV 空间形成细长 footprint，普通方形 mip 可能沿一个方向过糊、另一个方向采样不足。anisotropic filtering 沿主方向增加采样，以更多带宽换取倾斜表面的稳定细节。

抗锯齿策略处理的信号范围不同
   SSAA 提高整体空间采样率但成本最高；MSAA 主要改善几何 coverage；FXAA 在最终颜色上识别并柔化边缘；TAA 使用 jitter、motion vector 与 history resolve 积累时间样本，同时引入 ghosting、模糊与历史失效问题。纹理和 shader 高频仍需从源头过滤。

UV 与资源边界决定采样是否连续
   UV 密度、重复频率、seam、atlas padding、wrap mode、normal map tangent basis 和 mip 生成共同决定纹理边界。相同 position 在 UV seam 处通常需要拆顶点；缺少 padding 会让低 mip 混入图集外颜色。

关键路径
--------

一次纹理采样进入屏幕：

::

   mesh 顶点提供 UV
   → rasterizer 做透视校正插值
   → fragment shader 得到当前 UV
   → 邻近片元导数估计纹理 footprint
   → sampler 选择 mip level 与过滤方式
   → texture unit 读取并重建纹理值
   → shader 完成材质和光照
   → coverage 或 temporal resolve 生成最终像素

纹理闪烁排查：

::

   固定场景并分别观察静止与运动画面
   → 用纯色或 UV debug 区分几何与纹理问题
   → 检查纹理是否具有正确 mip chain
   → 检查 min/mag、mipmap、anisotropy、LOD bias 与 wrap
   → 检查 UV 密度、重复频率和 seam padding
   → 检查 shader 导数、显式 LOD 与高频分支
   → 再使用 TAA 或其它 resolve 处理剩余屏幕 aliasing

几何边缘抗锯齿：

::

   三角形覆盖连续屏幕区域
   → 像素或子样本测试 coverage
   → fragment shader 计算颜色
   → MSAA、SSAA 或单样本 render target 保存样本
   → resolve 合成像素
   → FXAA 或 TAA 可继续处理最终边缘与时间稳定性

概念辨析
--------

* **插值与采样**：插值根据已知样本计算中间值；采样决定读取信号的位置和频率。连续插值结果仍可能因采样不足产生 aliasing。
* **采样与过滤**：采样产生离散读数；过滤根据覆盖范围组合邻域信息。单点采样后再模糊不能完全恢复已经折叠的高频。
* **bilinear 与 trilinear**：bilinear 在一个 mip 层内过滤四个 texel；trilinear 还在两个 mip 层结果之间混合。
* **mipmap 与 anisotropic filtering**：mipmap提供不同尺度的预过滤图像；各向异性过滤针对细长 footprint 在主方向增加读取，通常建立在 mipmap 之上。
* **几何 aliasing 与纹理 aliasing**：前者来自 primitive coverage 与像素网格不匹配；后者来自 texel 或 shader 信号频率超过屏幕采样率。两者可能同时存在但处理入口不同。
* **MSAA、FXAA 与 TAA**：MSAA增加几何 coverage 样本；FXAA处理最终颜色边缘；TAA积累跨帧抖动样本。它们对透明、纹理、高光和历史变化的覆盖能力不同。
* **LOD bias 与纹理清晰度**：负 bias 选择更高分辨率 mip，静态更锐利但更易闪烁；正 bias 更稳定但更模糊。判断必须包含运动画面。
* **UV seam 与过滤边界**：UV seam 是参数化不连续；过滤边界是 sampler 在邻域读取时遇到的 wrap 或 atlas 外数据。修复 seam 可能需要拆顶点、统一 tangent basis 和增加纹理 padding。

本章结论
--------

插值与采样问题必须围绕信号频率、采样率和像素 footprint 判断。阅读 shader 或排查闪烁时，应先分清属性插值、纹理采样、几何 coverage 与时间 resolve 的责任，再检查 mipmap、sampler、导数、UV 和抗锯齿边界；稳定画面来自采样前的正确预过滤与匹配 footprint，而不是依赖最终后处理掩盖上游错误。