# 基于树莓派的人脸识别考勤系统设计与实现 — LaTeX1

本目录是重新整理后的论文版本，按五章结构编写：

1. 绪论：背景意义、研究现状、主要工作；
2. 毕业设计相关关键技术；
3. 系统需求分析；
4. 系统设计；
5. 系统实现与测试分析。

`latex/` 目录仅作为模板和格式参考，本版正文均重新组织在 `latex1/` 中。

## 编译方式

推荐使用 XeLaTeX：

```bash
cd latex1
xelatex main.tex
xelatex main.tex
```

当前工作区未检测到本地 LaTeX 编译器，因此需要在已安装 TeX Live / MiKTeX / Overleaf 的环境中编译。

如果编译后中文不显示，请确认编译器是 **XeLaTeX**。本模板已使用 TeX Live/Overleaf 自带的 `fandol` 中文字体集，不能使用 pdfLaTeX 编译。

## 文件结构

```text
latex1/
├── main.tex
├── heuthesis.cls
├── README.md
├── figures/
│   └── README.md
└── chapters/
    ├── chapter1.tex
    ├── chapter2.tex
    ├── chapter3.tex
    ├── chapter4.tex
    ├── chapter5.tex
    └── conclusion.tex
```

## 本版写作边界

- 只写最终系统采用的技术和效果：YuNet、SFace、OpenVINO、FastAPI、SQLite、Jinja2、Bootstrap、Tailscale。
- 正文只围绕最终系统展开，不做无关实现对照。
- 参考文献均在正文对应技术或论述处标注，不只堆在文末。
- 第五章已预留运行截图位置，图片放入 `figures/` 后会自动替换占位框。
