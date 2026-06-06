# 树莓派论文 LaTeX 降 AI 工作稿

本目录是可独立编译的 LaTeX 工作稿。

## 文件说明

- `main.tex`：主 LaTeX 文件，建议从这个文件继续修改。
- `main.pdf`：已编译出的 PDF。
- `heuthesis.cls`：哈尔滨工程大学本科论文模板，已设置为 Windows 字体集。
- `figures/raspberry/`：从 Word 文档中提取出的论文图片资源。
- `source/`：保留中文文件名版本的 tex 和 pdf。
- `tools/convert_raspberry_thesis.py`：从 `树莓派.docx` 生成当前工作稿的转换脚本。

## 编译命令

在本文件夹内运行：

```powershell
xelatex -interaction=nonstopmode -halt-on-error main.tex
```

如需刷新目录，可连续运行两次。
