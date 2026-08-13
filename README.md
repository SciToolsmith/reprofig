# SciRepro

<p align="center">
  <picture>
    <source media="(max-width: 640px)" srcset="docs/assets/scirepro-hero-mobile.zh-CN.svg">
    <img src="docs/assets/scirepro-hero.zh-CN.svg" alt="SciRepro：从论文图件回到研究过程" width="100%">
  </picture>
</p>

<p align="center">
  <strong>简体中文</strong> · <a href="README.en.md">English</a> · <a href="#30-秒开始">快速开始</a> · <a href="scirepro/SKILL.md">完整规范</a>
</p>

SciRepro 是面向 Codex 的科研图件复现 Skill。它先把每一张目标图物化为可核验对象，再解释图件、追溯生成链、调查复现条件、生成带原图的本地报告；你批准具体路线后，它才执行与验收。

> **目标图先核验，复现路线再研判，科学结论最后验收。**

## 30 秒开始

**安装**

```text
使用 $skill-installer 安装 https://github.com/SciToolsmith/scirepro/tree/main/scirepro
```

**调用：三种入口都支持一张或多张图**

```text
# 论文 + 图号（Skill 自动提取完整图件）
使用 $scirepro 分析这篇论文的图 6、图 7 和图 11。

# 论文 + 上传的目标图片集
使用 $scirepro 分析这篇论文与我上传的这些目标图。

# 仅图片集
使用 $scirepro 重构这些图片中可见的曲线、数据和版式。
```

三种入口都会先建立 `targets/` 工作区，保存原始文件、规范化 PNG、裁切 QA 与哈希清单。与论文可靠匹配并通过 QA 的目标进入 `scientific-reproduction`；仅图片模式进入边界明确的 `image-derived-reconstruction`。

## 一条主线，最小充分研判

SciRepro 只有一条复现主线。单纯询问图意、生成逻辑或大致可行性时可以直接回答；只要要实际复现或生成结果，就始终遵循下面的过程：

```text
核验目标图 → 理解证据作用 → 追溯生成链 → 形成最小可用路线
→ 调查会改变决策的未知项 → 本地网页版报告 → 用户批准 → 执行与科学验收
```

调查只围绕四类会改变决策的问题展开：**路线能否执行、能够支持什么科学结论、需要多少实质资源、是否需要额外权限**。一旦可以给出能够检验既定目标、并具有明确假设与验收标准的可执行路线，或能够说明所有合理路线为何受阻，就停止扩展调查；不会为了背景完整而继续搜索、扫描无关环境或堆砌候选路线。

论文中的公式和参数是优先证据，但不是默认正确的真值。SciRepro 只独立推导或核验目标图生成链与验收标准直接依赖的部分，并与符号定义、单位量纲、代码、引用来源及图中现象交叉检查；不审查与目标图无关的整篇公式。任何歧义、疑似错误或代码—论文差异都会显式记录。

登录、付费、大型下载、GPU、覆盖、上传和公开发布仍需明确批准。真正的复现任务始终先生成**带全部已核验目标图的本地网页版研判报告**。

## 一个任务，一个结果文件夹

批准后的运行只交付一个 `scirepro-run-<run-id>/`。单图和多图使用同一种结构；没有内容的可选目录不会创建。

```text
scirepro-run-<run-id>/
├── README.md              # 人类入口：结论、复跑方法与边界
├── manifest.json          # 文件哈希、状态、来源与完整性清单
├── report/                # 完整/部分复现必有的本地结果网页
├── shared/                # 共用计划、环境、来源、代码、配置与日志
└── targets/
    └── <target-id>/
        ├── result.json
        ├── outputs/       # 复现图及派生成果
        ├── validation/    # 指标、对比图与验收摘要
        └── derived/       # 数字化或图像派生数据（如使用）
```

运行结果分开记录三件事：**是否执行完成**、**是否通过验收**、**论文主张是否得到支持**。因此“代码跑完”不会被误写成“结论复现成功”。完整或部分复现会把执行前研判页与实际结果合成最终本地网页；失败、受阻或取消则不强制生成没有结果的空网页，但仍会终结为可检查的诊断文件夹。

执行时始终保留未迎合原图调参的 **V0 基线**。默认最多再做一次有科学依据的差异修正和一次表达/可读性修复，达到验收标准就停止；第三轮及以后必须提出新的可检验科学假设并逐轮获得批准。正确实现仍不支持论文结论时，SciRepro 会保留负面结果，而不是继续追逐像素相似度，也不会仅凭复现失败指控造假。

<details>
<summary><strong>两种模式与版权边界</strong></summary>

### 两种模式，不混淆结论

- **有论文：科学复现。**重建数据—方法—协议—绘图链，以预先定义的趋势、峰值、频率、模态、统计量或机制关系验收。
- **只有图片：图像派生重构。**可以描线、数字化、拟合外形或重建版式，但只说明可见几何与外观；不声称恢复了原始数据、方法、实验或论文结论。

本地报告必须直接显示全部目标图。公开分享版只有在确认再分发权后才嵌入图片；否则只显示版权边界，不泄露本地路径或图像字节。

</details>

<p align="center">
  <a href="scirepro/SKILL.md#evidence-and-route-model">复现判定</a> ·
  <a href="scirepro/SKILL.md#permissions-and-approval">批准边界</a> ·
  <a href="scirepro/references/run-bundle-contract.md">结果包规范</a>
</p>

<details>
<summary><strong>手动安装与旧版迁移</strong></summary>

```bash
git clone https://github.com/SciToolsmith/scirepro.git
mkdir -p ~/.codex/skills
cp -R ./scirepro/scirepro ~/.codex/skills/scirepro
```

从 ReproFig 升级时，先确认 `$scirepro` 可用，再删除或停用旧目录 `~/.codex/skills/reprofig`。

</details>

## 开源与许可

SciRepro 采用 [MIT License](LICENSE)。论文、数据集、第三方代码和生成成果仍遵循各自的版权与许可证。
