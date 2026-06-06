%% heuthesis.cls -- 哈尔滨工程大学本科毕业论文模板
%% 基于学校《本科生论文编写规范》编写
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{heuthesis}[2026/05/05 v1.1 HEU undergraduate thesis template]

\DeclareOption*{\PassOptionsToClass{\CurrentOption}{ctexbook}}
\ProcessOptions\relax

\LoadClass[a4paper,zihao=-4,fontset=windows,scheme=chinese]{ctexbook}

% ========== 页面设置 ==========
\RequirePackage[top=28mm,bottom=28mm,left=25mm,right=25mm,
  headheight=12mm,headsep=8mm,footskip=12mm]{geometry}

% ========== 行距 ==========
\linespread{1.5}

% ========== 段落 ==========
\setlength{\parindent}{2em}
\setlength{\parskip}{0pt}

% ========== 标题格式 ==========
\ctexset{
  chapter = {
    format     = \centering\zihao{3}\bfseries,
    name       = {第,章},
    number     = \arabic{chapter},
    beforeskip = 24pt, afterskip = 18pt,
  },
  section = {
    format     = \centering\zihao{4}\bfseries,
    name       = {\arabic{chapter}.,},
    number     = \arabic{section},
    beforeskip = 18pt, afterskip = 12pt,
  },
  subsection = {
    format     = \zihao{-4}\bfseries,
    name       = {\arabic{chapter}.\arabic{section}.\arabic{subsection}},
    number     = \arabic{subsection},
    beforeskip = 12pt, afterskip = 6pt,
  },
  contentsname = 目\quad 录,
  figurename   = 图,
  tablename    = 表,
}

% ========== 宏包 ==========
\RequirePackage{graphicx}
\RequirePackage{caption}
\captionsetup[figure]{font=small,labelsep=quad}
\captionsetup[table]{font=small,labelsep=quad}
\RequirePackage{float}
\RequirePackage[section]{placeins}
\RequirePackage{booktabs}
\RequirePackage{longtable}
\RequirePackage{tabularx}
\RequirePackage{multirow}
\RequirePackage{amsmath,amssymb}
\RequirePackage{listings}
\lstset{
  basicstyle=\ttfamily\small, breaklines=true,
  frame=none, numbers=none,
  keywordstyle=\bfseries, showstringspaces=false,
}
\RequirePackage{algorithm}
\RequirePackage{algorithmicx}
\RequirePackage{algpseudocode}
\algrenewcommand\algorithmicrequire{\textbf{输入:}}
\algrenewcommand\algorithmicensure{\textbf{输出:}}
\algrenewcommand\algorithmicforall{\textbf{对于}}
\algrenewcommand\algorithmicfor{\textbf{对于}}
\algrenewcommand\algorithmicdo{\textbf{执行}}
\algrenewcommand\algorithmicend{\textbf{结束}}
\algrenewcommand\algorithmicif{\textbf{如果}}
\algrenewcommand\algorithmicthen{\textbf{则}}
\algrenewcommand\algorithmicelse{\textbf{否则}}
\algrenewcommand\algorithmicwhile{\textbf{当}}
\algrenewcommand\algorithmicreturn{\textbf{返回}}
\RequirePackage{tikz}
\usetikzlibrary{shapes.geometric,arrows,positioning,fit,calc}

% ========== 超链接 ==========
\RequirePackage{hyperref}
\hypersetup{colorlinks=true,linkcolor=black,citecolor=black,urlcolor=blue}

% ========== 封面定义 ==========
\newcommand{\@thesistitle}{}
\newcommand{\thesisTitle}[1]{\renewcommand{\@thesistitle}{#1}}
\newcommand{\@authorName}{}
\newcommand{\authorName}[1]{\renewcommand{\@authorName}{#1}}
\newcommand{\@studentID}{}
\newcommand{\studentID}[1]{\renewcommand{\@studentID}{#1}}
\newcommand{\@advisor}{}
\newcommand{\advisor}[1]{\renewcommand{\@advisor}{#1}}
\newcommand{\@major}{}
\newcommand{\majorField}[1]{\renewcommand{\@major}{#1}}
\newcommand{\@college}{}
\newcommand{\collegeName}[1]{\renewcommand{\@college}{#1}}
\newcommand{\@submitDate}{}
\newcommand{\submitDate}[1]{\renewcommand{\@submitDate}{#1}}

% ========== 封面生成 ==========
\newcommand{\makeCover}{%
\thispagestyle{empty}
\begin{center}
  \vspace*{1cm}
  {\zihao{1}\bfseries 哈尔滨工程大学}\\[1.5cm]
  {\zihao{-1}\bfseries 本科生毕业论文（设计）}\\[2cm]
  {\zihao{2}\bfseries\@thesistitle}\\[2cm]
\end{center}
\vfill
\begin{center}
\renewcommand{\arraystretch}{2.2}
{\zihao{4}
\begin{tabular}{r@{\hspace{2em}}l}
  学生姓名 & \underline{\makebox[8em]{\@authorName}}\\
  学\quad\quad 号 & \underline{\makebox[8em]{\@studentID}}\\
  专\quad\quad 业 & \underline{\makebox[8em]{\@major}}\\
  指导教师 & \underline{\makebox[8em]{\@advisor}}\\
  提交日期 & \underline{\makebox[8em]{\@submitDate}}\\
\end{tabular}}
\end{center}
\vspace{2cm}
\begin{center}
  {\zihao{3}\@college}\\
  {\zihao{-3}哈尔滨工程大学}
\end{center}
\vspace*{1cm}
\clearpage
}
