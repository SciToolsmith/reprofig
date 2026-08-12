<p align="center">
  <picture>
    <source media="(max-width: 640px)" srcset="docs/assets/scirepro-hero-mobile.zh-CN.svg">
    <img src="docs/assets/scirepro-hero.zh-CN.svg" alt="SciRepro：从论文图件回到研究过程" width="100%">
  </picture>
</p>

<p align="center">
  <strong>简体中文</strong> · <a href="README.en.md">English</a> · <a href="#30-秒开始">快速开始</a> · <a href="scirepro/SKILL.md">完整规范</a>
</p>

SciRepro 是面向 Codex 的科研图件复现 Skill。给它一篇论文和目标图件，它会解释图件支持什么主张，重建从输入到绘图的生成链，提出有证据支持的复现路线，并在你批准后执行与验收。

> **复现的不是图片像素，而是产生这张图的研究过程与关键科学现象。**

## 30 秒开始

**安装**

```text
使用 $skill-installer 安装 https://github.com/SciToolsmith/scirepro/tree/main/scirepro
```

**调用**

```text
使用 $scirepro 分析这篇论文的图 6、图 7 和图 11。
先给我证据作用、生成链、候选复现路线和验收标准，
生成本地报告；等我选择路线后再执行。
```

## 你会得到什么

- **证据地图** — 图中可观察到什么，它支持论文的哪项主张，又不能说明什么。
- **复现路线** — 数据、方法、协议、假设、缺口、本机条件与科学验收标准清晰可查。
- **可追溯成果** — 可重新运行的代码、生成图件、配置、验证结果、日志与来源记录。

## 先报告，再执行

**批准前：**只读图、调查证据、制定路线并生成本地报告。报告会区分已核验、可推导、可合理假设和真正缺失的条件。

**批准后：**只执行你选定的图件与路线；如果数据、算法、环境、预算或支持的主张发生实质变化，SciRepro 会停下并重新确认。

## 科学复现，不是视觉还原

- 不从发表图片描线或拟合曲线来冒充数值结果；
- 不把替代数据、第三方实现或透明假设写成作者原案例；
- 不把“程序能运行”直接写成“论文结论已复现”。

SciRepro 依据预先定义的趋势、峰值、频率、模态、统计量或机制关系验收结果，并明确说明结论**支持什么、不能支持什么、还缺什么**。

<p align="center">
  <a href="scirepro/SKILL.md#evidence-model">复现判定</a> ·
  <a href="scirepro/SKILL.md#approval-gate">批准边界</a> ·
  <a href="scirepro/SKILL.md#deliverables">完整交付</a>
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
