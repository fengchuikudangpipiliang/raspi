# 基于树莓派的人脸识别考勤系统设计与实现 — LaTeX 论文

## 编译方式

### Overleaf 在线编译（推荐）

1. 打开 [Overleaf](https://cn.overleaf.com/)
2. 新建项目
3. 上传以下文件（注意保持 chapters/ 目录结构）：
   - `main.tex`
   - `heuthesis.cls`
   - `chapters/chapter1.tex`
   - `chapters/chapter2.tex`
   - `chapters/chapter3.tex`
   - `chapters/chapter4.tex`
   - `chapters/conclusion.tex`
4. 编译器选择 **XeLaTeX**（Menu → Compiler → XeLaTeX）
5. 点击 Recompile

### 本地编译

```bash
cd latex
xelatex main.tex
xelatex main.tex   # 编译两次生成完整目录
```

## 文件结构

```
latex/
├── main.tex              # 主文件（封面、摘要、目录、参考文献、致谢）
├── heuthesis.cls         # 模板类
├── README.md             # 本文件
└── chapters/
    ├── chapter1.tex      # 第1章 绪论
    ├── chapter2.tex      # 第2章 核心技术概要（公式+表格）
    ├── chapter3.tex      # 第3章 系统设计与实现（算法+表格）
    ├── chapter4.tex      # 第4章 实验与分析（对照实验+参数分析）
    └── conclusion.tex    # 结论
```

## 修改个人信息

编辑 `main.tex` 顶部：

```latex
\thesisTitle{基于树莓派的人脸识别考勤系统设计与实现}
\authorName{（你的姓名）}
\studentID{（你的学号）}
\advisor{（指导教师姓名）}
\majorField{软件工程}
\collegeName{计算机科学与技术学院}
\submitDate{2026年5月}
```

## 本次重写的主要改进

1. **去掉了 dlib 相关内容**：只写 YuNet+SFace 最终方案
2. **公式化**：第2章加入16个数学公式（余弦相似度、Laplacian方差、滑动窗口融合、屏幕重放风险信号等）
3. **表格**：
   - 表2.1 质量校验器设计
   - 表3.1 严格识别引擎门禁条件
   - 表3.2 数据库表结构
   - 表4.1 识别线程各阶段处理耗时
   - 表4.2 线程解耦前后帧率对比
   - 表4.3 系统内存占用分析
   - 表4.4 活体检测准确率评估
   - 表4.5 编码匹配阈值对识别效果的影响
   - 表4.6 滑动窗口长度对活体检测的影响
4. **算法伪代码**：第3章加入动作挑战流程算法
5. **第4章重写**：从"功能测试"改为"实验与分析"，加入参数敏感性分析（阈值消融、窗口长度对比）
6. **参考文献更新**：补充了CVPR 2025 FAS论文、最新活体检测综述等
