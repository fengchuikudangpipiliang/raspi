# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "树莓派.docx"
OUT_TEX = ROOT / "树莓派论文_降AI工作稿.tex"
FIG_DIR = ROOT / "figures" / "raspberry"

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def qn(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


REWRITE_PREFIXES: list[tuple[str, str]] = [
    (
        "随着高校、实验室和企事业单位对人员管理效率与数据可信度要求的提升",
        "在实验室入口、课程签到和小型办公场所中，考勤记录通常既用于统计到岗情况，也承担事后追溯的作用。人工签到、纸质登记和刷卡考勤虽然部署门槛低，但集中签到时容易排队，记录整理依赖人工，卡片或纸面凭证也存在代签、遗失和补录困难等问题。结合毕业设计的设备条件，本文将识别与签到环节放在树莓派端完成，围绕低成本、轻量化和本地运行三个目标，设计并实现人脸识别考勤系统。",
    ),
    (
        "系统采用FastAPI作为后端框架，使用Jinja2模板和Bootstrap构建终端页面与用户门户",
        "系统后端使用FastAPI组织终端页、用户门户、动作挑战和管理员接口，页面部分由Jinja2模板渲染，并通过Bootstrap完成基本布局。数据侧采用SQLite保存成员名单、用户账号、人脸档案、审核记录和考勤流水。识别链路最终选用OpenCV YuNet做人脸检测，SFace提取人脸特征并计算余弦相似度，活体判断由OpenVINO加载anti-spoof-mn3模型完成。围绕注册和签到两个核心流程，系统实现了名单导入、首次注册改密、动作挑战抓拍、人脸质量校验、管理员审核、终端识别、自动写库和远程管理接口。注册端使用正脸、侧转、再正脸的三步挑战，并结合姿态、同人一致性、模糊度、亮度和翻拍风险检查；终端端将摄像头采集和识别推理分为两个线程，识别线程只处理最新帧，再依次经过单人入镜、人脸面积、活体、身份匹配、考勤时间窗和重复签到冷却等判断。",
    ),
    (
        "测试结果表明，本系统能够完成从用户注册到终端签到的端到端流程",
        "测试阶段验证了从用户注册到终端签到的完整流程。测试库中能够保存成员名单、审核通过的人脸档案和考勤记录；终端按1280×720分辨率采集，摄像头采集目标为15FPS，识别线程目标为5FPS。在实验室门口这类单人依次签到的场景下，系统可以给出实时识别反馈并写入签到记录。当前实现仍以小规模人脸库和单台树莓派为主要对象，后续可继续扩展多终端同步、考勤规则配置和统计报表。",
    ),
    (
        "With the increasing demand for efficient personnel management",
        "In small-scale scenarios such as laboratory entrances and classroom check-in, attendance records are used not only for counting arrivals but also for later tracing abnormal cases. Manual sign-in, paper registration, and card-based attendance are easy to deploy, yet they still suffer from queues, proxy attendance, manual statistics, and dependence on physical media. Under the hardware constraints of the graduation project, this thesis places camera capture, face recognition, liveness checking, and attendance writing on a Raspberry Pi terminal, and implements a lightweight face recognition attendance system for local deployment.",
    ),
    (
        "The system uses FastAPI as the backend framework",
        "The backend is organized with FastAPI, while Jinja2 templates and Bootstrap are used for the terminal page and user portal. SQLite stores roster members, users, face profiles, review history, and attendance records. The recognition pipeline uses OpenCV YuNet for face detection, SFace for feature extraction and cosine-similarity matching, and OpenVINO with the anti-spoof-mn3 model for passive liveness detection. The system connects roster import, first-time registration, password reset, action-challenge capture, face quality validation, administrator review, terminal recognition, attendance recording, and remote management APIs. During registration, the user completes a front-face, side-turn, and front-face-again challenge; during terminal recognition, frame capture and recognition are separated into two threads so that only the latest frame is processed by the recognition pipeline.",
    ),
    (
        "Test results show that the system can complete the end-to-end process",
        "Tests show that the implemented system can run through the whole process from account activation to terminal check-in. The test database records roster members, approved face profiles, and attendance entries persistently. With 1280×720 camera input, 15 FPS capture, and a 5 FPS recognition target, the terminal provides usable feedback for small laboratory-door attendance scenarios. The current version is still designed around a single Raspberry Pi and a small face database, leaving multi-device synchronization, configurable rules, and statistical reports for future work.",
    ),
    (
        "考勤管理是学校、实验室、企业和机关单位日常管理中的基础工作",
        "在学校实验室或小型办公空间中，考勤记录通常和人员到场、安全责任、异常追溯联系在一起。传统方式主要包括手工签到、纸质登记、IC卡和指纹识别。手工和纸质方式实现简单，但高峰时段容易排队，后续统计也依赖人工整理；IC卡依赖实体介质，忘带、遗失和代刷都会影响记录可信度；指纹识别虽然能降低代签问题，但接触式采集会带来设备磨损和公共卫生方面的顾虑。",
    ),
    (
        "树莓派体积小、功耗低、生态成熟",
        "本课题选用树莓派作为终端，主要考虑到它体积小、功耗低，能够连接USB摄像头并运行Linux服务。对于实验室门口这类固定部署点，树莓派可以同时承担摄像头采集、模型推理、页面服务和SQLite本地存储。视频帧留在端侧处理，可以减少持续上传带来的带宽压力；成员照片和考勤记录保存在本地数据库中，也符合小规模场景独立运行的需求。管理员需要远程查看设备时，再通过局域网或Tailscale访问管理接口。",
    ),
    (
        "活体检测是人脸识别考勤系统安全性的重要补充。邓雄和王洪春",
        "在考勤场景中，活体检测主要用于处理照片、手机屏幕和预录视频等冒用风险。邓雄和王洪春从深度学习与特征融合角度研究了人脸活体检测[12]，赵洋等讨论了多模态特征融合方法[13]，杨瑞杰和王洪春则将InceptionV3与特征融合用于防伪判断[14]。这些研究说明，单纯依靠人脸相似度并不足以支撑考勤写库。结合本课题的树莓派部署条件，系统在注册端加入动作挑战和质量校验，在终端端加入被动活体检测与翻拍风险分析，用多层规则降低冒用概率。",
    ),
    (
        "国外人脸识别研究经历了从人工特征到深度学习特征的演进",
        "国外人脸识别方法大致经历了人工特征到深度嵌入特征的变化。早期方法更多依赖主成分分析、局部二值模式等手工描述符，面对光照、姿态和遮挡变化时稳定性有限。深度学习方法出现后，识别系统逐渐转向学习人脸嵌入向量。FaceNet使用三元组损失拉近同类样本、拉远异类样本[15]；ArcFace和CosFace则通过角度间隔或余弦间隔提高特征区分度[16-17]。本文没有重新训练识别模型，而是使用可部署的SFace特征向量进行小规模人脸库匹配。",
    ),
    (
        "在系统工程方面，轻量Web框架、嵌入式数据库和虚拟组网技术为端侧考勤系统提供了成熟基础",
        "从工程实现看，本课题需要的不是单一算法演示，而是一套能在树莓派上长期运行的Web系统。FastAPI用于组织页面路由、JSON接口和流式响应[23]；SQLite把账号、人脸档案和考勤记录落在本地文件中，适合毕业设计规模下的轻量部署[24]；Tailscale基于WireGuard构建私有网络，使Windows管理端能够在不同网络环境下访问树莓派服务[25]。这些技术本身已经成熟，难点在于把注册、审核、识别、签到和远程管理放进同一条可追溯的业务链路。",
    ),
    (
        "人脸识别的关键是将人脸图像转化为可比较的特征表示",
        "在人脸考勤中，识别模块实际需要解决的是“当前帧中的人脸和库中哪一张人脸最接近”。早期人工特征对光照、表情和角度变化比较敏感，因此工程系统更常采用深度模型输出的嵌入向量。SFace输出固定维度的人脸特征后，系统可以把审核通过的向量保存在数据库中；识别时只需把当前特征与库中特征逐一计算相似度，再根据阈值判断是否匹配。这种方式适合成员数量会增减的小型考勤系统，因为新增成员只需要增加一条人脸档案，而不需要重新训练分类器。",
    ),
    (
        "活体检测方法可以分为主动式和被动式两类",
        "活体检测通常分为主动式和被动式。主动式会要求用户眨眼、转头或张嘴，交互明确，适合注册采集这类低频动作；被动式不额外打断用户，而是从图像纹理、反光、频域信息或模型输出中判断风险。相关综述指出，深度学习活体检测在跨设备、跨光照和跨攻击介质时仍要关注泛化能力[22]。本系统把主动挑战放在注册端，把被动活体放在终端签到端，是为了在入库阶段加强控制，同时尽量减少日常签到时的操作负担。",
    ),
    (
        "本文系统的需求来源主要来自三类使用场景",
        "需求分析围绕三类使用场景展开。第一类是普通用户首次使用系统时的账号激活和人脸资料提交，用户必须在管理员预置名单范围内完成身份校验，再通过浏览器摄像头完成动作挑战。第二类是树莓派终端的现场签到，终端需要持续读取摄像头画面，并在本地完成检测、识别、活体判断和考勤规则判断。第三类是管理员的远程管理，管理员需要维护名单、审核人脸档案、查看考勤记录和掌握设备状态。三类场景都指向同一套本地数据，但入口、权限和操作频率并不相同。",
    ),
    (
        "在安全边界上，系统根据访问来源控制页面入口",
        "系统的访问边界按照角色和来源划分。本地环回地址用于终端页、视频流和终端接口；普通远程访问进入用户门户；管理员API作为独立入口，只接受携带Authorization Bearer Token或X-Admin-Token的请求。人脸图片和签到快照不直接放成公开静态资源，普通用户只能通过会话查看本人资料，管理员也需要经过鉴权接口读取图片或快照。这样处理后，用户自助注册、现场签到和远程审核可以共用同一台树莓派服务，同时减少不同角色之间的越权访问机会。",
    ),
    (
        "系统功能实现围绕运行环境、配置管理、数据持久化、用户门户",
        "第五章按照实际落地顺序说明系统实现。首先给出树莓派端和Windows管理端的运行环境，然后说明配置加载、SQLite初始化和本地文件持久化方式，接着分别展开用户门户、注册采集、终端识别、管理员接口和测试结果。树莓派端承担现场采集、推理和写库，Windows端通过Tailscale访问管理员接口，二者之间只通过HTTP接口协作。",
    ),
    (
        "接着，用户门户由/portaa/*页面路由和/api/portal/*业务接口组成",
        "用户门户由/portal/*页面路由和/api/portal/*业务接口组成。首次注册页需要用户填写姓名、学号或工号、初始密码、新密码和确认密码。后端处理时先同步成员名单，再依次校验编号、姓名、成员状态、初始密码和新密码规则。全部通过后，系统在users表中创建账号，并把用户ID写入浏览器Session，随后引导用户进入人脸采集流程。",
    ),
    (
        "终端摄像头服务采用采集线程和识别线程分离的设计",
        "终端摄像头服务分为采集线程和识别线程。采集线程负责打开摄像头、设置分辨率与帧率、读取原始帧，并按配置完成缩放、镜像、旋转和JPEG编码，随后供MJPEG视频流使用。识别线程按目标频率取共享缓冲区中的最新帧，完成YuNet检测、活体判断、SFace特征提取、身份匹配和考勤规则判断。两个线程之间只传递最新帧，旧帧被覆盖后不再追赶处理，这样可以避免识别耗时波动造成画面积压。",
    ),
    (
        "当识别线程得到可签到结果后，摄像头服务在写库前再次执行考勤策略判断",
        "识别线程给出可签到结果后，摄像头服务不会立即写库，而是再次检查重复签到冷却和当前考勤规则。确认通过后，Repository向attendance_records表写入签到记录，并把当前帧保存为现场快照。快照按日期分目录保存，文件名中包含时间和用户编号。终端页面随后显示短暂的成功提示，状态接口也会返回“已签到”等进度信息，方便页面侧刷新。",
    ),
    (
        "终端识别实现还考虑了长期运行中的异常状态",
        "为了让终端能够连续运行，摄像头服务对几个异常状态做了处理。摄像头打开失败时，页面显示中文占位画面并提示检查摄像头编号或权限；连续读帧失败时，服务释放摄像头句柄并在下一轮尝试重新连接；管理员审核通过的新档案通过识别库定时重载进入内存，不要求重启服务；签到快照按保留天数清理，避免树莓派磁盘空间长期被图片占用。这些逻辑不直接改变用户流程，但会影响现场终端的稳定性。",
    ),
    (
        "管理员接口统一挂载在/api/admin路径下",
        "管理员接口挂载在/api/admin路径下，供Windows管理端通过Tailscale访问。普通用户Session不参与管理员鉴权，管理端请求需要携带管理员Token，可放在Authorization: Bearer <token>请求头中，也兼容X-Admin-Token。接口返回结构统一使用ok、data、items和total等字段，便于Windows端页面处理。设备状态类接口会返回基础信息、健康状态、性能指标和配置重载结果，其中健康状态包括数据库、摄像头、最近帧时间、名单文件、人脸目录和快照目录等检查项，性能指标包括系统负载、内存、磁盘、CPU温度和进程ID。",
    ),
    (
        "由上图4.5可知，系统并不是在检测到人脸后立即写入考勤",
        "图4.5展示了终端写入考勤前的多道判断。检测到人脸只是第一步，后续还需要判断人脸数量、人脸面积、活体概率、翻拍风险、身份相似度、考勤时间窗和重复签到冷却。画面中没有人脸时，终端提示用户进入画面；出现多人时暂停签到，避免身份归属不清；人脸区域过小时提示用户靠近摄像头，减少小脸裁剪导致的特征不稳定。只有这些条件同时满足，识别结果才会变为attendance_ready。",
    ),
    (
        "第一，完成了完整的用户注册与人脸资料提交流程。系统通过本地CSV名单限制允许注册的用户范围",
        "第一，完成了用户注册与人脸资料提交链路。管理员先维护本地CSV名单，用户首次注册时需要通过姓名、编号和初始密码校验，再设置正式密码。人脸采集阶段由浏览器摄像头现场抓拍，后端维护动作挑战会话，并只接收通过挑战后冻结的可信注册照。",
    ),
    (
        "系统目前仍存在一些不足。首先，系统主要面向小规模人脸库",
        "当前系统还有几处限制。人脸匹配仍采用小规模库下的线性遍历，成员数量继续增加后，识别耗时会随库规模上升；活体检测主要依赖RGB图像、anti-spoof-mn3输出和轻量重放风险信号，对高质量屏幕重放仍有改进空间；部署形态以单台树莓派为核心，还没有实现多终端统一管理和跨设备数据同步；用户门户和管理员页面目前完成了核心操作，统计分析和交互细节仍可继续完善。",
    ),
    (
        "未来工作可以从以下方向展开",
        "后续改进可以围绕五个方向推进：增加可配置的考勤规则，支持迟到、早退、请假和补签等业务；扩展多设备协同，使多个树莓派终端能够统一管理；补充考勤导出、统计报表和可视化分析；继续优化活体检测和重放风险判断，提升复杂攻击场景下的鲁棒性；在人脸库规模扩大后，引入向量索引或近似检索方法，降低身份匹配耗时。",
    ),
    (
        "感谢我的毕业设计指导教师在选题、系统设计、代码实现和论文撰写过程中的耐心指导",
        "感谢指导教师在选题、系统设计、实现调试和论文修改过程中给予的指导。课题推进中，我多次根据老师的意见调整功能边界和论文结构，也在代码实现与测试记录之间重新梳理了系统逻辑。",
    ),
    (
        "感谢实验室的学长和同学们在项目推进过程中给予的帮助",
        "感谢实验室同学在树莓派部署、摄像头调试、注册流程试用和页面反馈方面提供的帮助。部分问题是在实际试用中暴露出来的，这些反馈帮助我及时修正了采集、审核和终端提示中的细节。",
    ),
]


def rewrite_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", text)
    for prefix, replacement in REWRITE_PREFIXES:
        if normalized.startswith(re.sub(r"\s+", "", prefix)):
            return replacement
    return text


def latex_escape(text: str) -> str:
    text = text.replace("\u00a0", " ")
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "_": r"\_",
        "%": r"\%",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "<": r"\textless{}",
        ">": r"\textgreater{}",
        "⋅": r"\(\cdot\)",
        "∇": r"\(\nabla\)",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\t", " ")
    text = re.sub(r"\[\[(\d+)\],\[(\d+)\]\]", r"[\1,\2]", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


def strip_heading_number(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"^第[0-9一二三四五六七八九十]+章\s*", "", text)
    text = re.sub(r"^\d+(?:\.\d+){1,2}\s*", "", text)
    return text.strip()


def node_text(node: ET.Element) -> str:
    parts: list[str] = []
    for elem in node.iter():
        if elem.tag in {qn("w", "t"), qn("m", "t")}:
            parts.append(elem.text or "")
        elif elem.tag == qn("w", "tab"):
            parts.append(" ")
        elif elem.tag == qn("w", "br"):
            parts.append("\n")
    return clean_text("".join(parts))


def paragraph_style(p: ET.Element) -> str:
    ppr = p.find("w:pPr", NS)
    if ppr is None:
        return ""
    style = ppr.find("w:pStyle", NS)
    if style is None:
        return ""
    return style.attrib.get(qn("w", "val"), "")


def paragraph_images(p: ET.Element) -> list[str]:
    ids: list[str] = []
    for blip in p.findall(".//a:blip", NS):
        rid = blip.attrib.get(qn("r", "embed"))
        if rid:
            ids.append(rid)
    return ids


def table_rows(tbl: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in tbl.findall("w:tr", NS):
        row: list[str] = []
        for tc in tr.findall("w:tc", NS):
            row.append(node_text(tc))
        if any(cell for cell in row):
            rows.append(row)
    return rows


def rel_map(zipf: zipfile.ZipFile) -> dict[str, str]:
    data = zipf.read("word/_rels/document.xml.rels")
    root = ET.fromstring(data)
    result: dict[str, str] = {}
    for rel in root:
        rid = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        rel_type = rel.attrib.get("Type", "")
        if rid and target and rel_type.endswith("/image"):
            result[rid] = target
    return result


def copy_media(zipf: zipfile.ZipFile, rels: dict[str, str]) -> dict[str, str]:
    if FIG_DIR.exists():
        shutil.rmtree(FIG_DIR)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    for rid, target in rels.items():
        src = "word/" + target
        name = Path(target).name
        dst = FIG_DIR / name
        dst.write_bytes(zipf.read(src))
        out[rid] = f"figures/raspberry/{name}"
    return out


def formula_to_latex(text: str) -> str:
    text = clean_text(text)
    mapping = {
        "Di=xi,yi,wi,hi,li1,li2,…,li10,si": r"D_i=(x_i,y_i,w_i,h_i,l_{i1},l_{i2},\ldots,l_{i10},s_i)",
        "f=ff2": r"\hat f=\frac{f}{\lVert f\rVert_2}",
        "simf1,f2=f1⋅f2": r"\operatorname{sim}(f_1,f_2)=f_1\cdot f_2",
        "Sreal+Sspoof=1": r"S_{\mathrm{real}}+S_{\mathrm{spoof}}=1",
        "Sreal=1Mi=1MSi": r"\overline{S}_{\mathrm{real}}=\frac{1}{M}\sum_{i=1}^{M}S_i",
        "Rt=AMLEDIt": r"R_t=A(M(L(E(D(I_t)))))",
        "si=q⋅ki": r"s_i=q\cdot k_i",
        "i*=argmaxisi": r"i^*=\arg\max_i s_i",
        "R=0.35Rfreq+0.25Rglare+0.15Redge+0.25Rrect": r"R=0.35R_{\mathrm{freq}}+0.25R_{\mathrm{glare}}+0.15R_{\mathrm{edge}}+0.25R_{\mathrm{rect}}",
        "Qblur=Var∇2G": r"Q_{\mathrm{blur}}=\operatorname{Var}(\nabla^2 G)",
    }
    compact = re.sub(r"\s+", "", text)
    compact = compact.replace("（", "(").replace("）", ")")
    for raw, latex in mapping.items():
        if compact.startswith(raw):
            return latex
    return r"\text{" + latex_escape(text) + "}"


def maybe_formula(rows: list[list[str]]) -> tuple[str, str] | None:
    if len(rows) != 1:
        return None
    cells = [clean_text(c) for c in rows[0] if clean_text(c)]
    if not cells:
        return None
    number = cells[-1]
    if not re.fullmatch(r"[（(]\d+\.\d+[）)]", number):
        return None
    formula = "".join(cells[:-1])
    tag = number.strip("()（）")
    return formula_to_latex(formula), tag


def render_table(rows: list[list[str]], caption: str | None) -> list[str]:
    formula = maybe_formula(rows)
    if formula:
        body, tag = formula
        return [r"\begin{equation*}", rf"{body}\tag{{{tag}}}", r"\end{equation*}", ""]

    if not rows:
        return []
    col_count = max(len(r) for r in rows)
    width = 0.92 / max(col_count, 1)
    colspec = "|" + "|".join(
        [rf">{{\raggedright\arraybackslash}}p{{{width:.3f}\textwidth}}" for _ in range(col_count)]
    ) + "|"
    lines = [r"\begingroup", r"\small", rf"\begin{{longtable}}{{{colspec}}}"]
    if caption:
        lines.append(rf"\caption{{{latex_escape(caption)}}}\\")
    lines.append(r"\hline")
    for row in rows:
        padded = row + [""] * (col_count - len(row))
        escaped = [latex_escape(clean_text(cell)) if clean_text(cell) else "--" for cell in padded]
        lines.append(" & ".join(escaped) + r" \\")
        lines.append(r"\hline")
    lines.extend([r"\end{longtable}", r"\endgroup", ""])
    return lines


def render_figure(rids: list[str], caption: str, media: dict[str, str]) -> list[str]:
    lines = [r"\begin{figure}[H]", r"\centering"]
    for rid in rids:
        path = media.get(rid, "")
        if not path:
            lines.append(r"\fbox{\parbox{0.82\textwidth}{\centering 图片关系未找到}}")
            continue
        if path.lower().endswith(".svg"):
            lines.append(
                rf"\fbox{{\parbox[c][0.28\textheight][c]{{0.82\textwidth}}{{\centering SVG 图暂未转换：\texttt{{{latex_escape(Path(path).name)}}}}}}}"
            )
        else:
            lines.append(rf"\includegraphics[width=0.86\textwidth]{{{path}}}")
    lines.append(rf"\caption{{{latex_escape(caption)}}}")
    lines.extend([r"\end{figure}", ""])
    return lines


def render_front_matter() -> list[str]:
    return [
        r"\documentclass[UTF8]{heuthesis}",
        "",
        r"\usepackage{fontspec}",
        r"\setmainfont{Times New Roman}",
        r"\setsansfont{Arial}",
        r"\setmonofont{Consolas}",
        r"\usepackage{xurl}",
        r"\usepackage{enumitem}",
        r"\setlist{nosep}",
        r"\hypersetup{hidelinks}",
        "",
        r"\thesisTitle{基于树莓派的人脸识别考勤系统设计与实现}",
        r"\authorName{陈浩}",
        r"\studentID{2022201616}",
        r"\advisor{吕继光}",
        r"\majorField{软件工程}",
        r"\collegeName{计算机科学与技术学院}",
        r"\submitDate{2026年6月}",
        "",
        r"\begin{document}",
        r"\makeCover",
        "",
        r"\frontmatter",
        r"\chapter*{摘\quad 要}",
        r"\addcontentsline{toc}{chapter}{摘\quad 要}",
    ]


def render_end() -> list[str]:
    return ["", r"\end{document}"]


def generate() -> None:
    with zipfile.ZipFile(DOCX) as zipf:
        document = ET.fromstring(zipf.read("word/document.xml"))
        rels = rel_map(zipf)
        media = copy_media(zipf, rels)

    body = document.find("w:body", NS)
    if body is None:
        raise RuntimeError("document body not found")

    lines = render_front_matter()
    pending_images: list[str] = []
    pending_table_caption: str | None = None
    in_refs = False
    reference_no = 0
    phase = "before_abstract"

    def flush_images_without_caption() -> None:
        nonlocal pending_images
        if pending_images:
            lines.extend(render_figure(pending_images, "原文图片", media))
            pending_images = []

    for child in body:
        local = child.tag.rsplit("}", 1)[-1]
        if local == "p":
            text = node_text(child)
            style = paragraph_style(child)
            images = paragraph_images(child)

            if images:
                pending_images.extend(images)
                continue
            if not text:
                continue

            text = rewrite_text(text)
            clean = clean_text(text)
            compact_clean = re.sub(r"\s+", "", clean)

            if compact_clean == "摘要":
                phase = "cn_abstract"
                continue
            if compact_clean.upper() == "ABSTRACT":
                phase = "en_abstract"
                lines.extend(
                    [
                        r"\clearpage",
                        r"\chapter*{ABSTRACT}",
                        r"\addcontentsline{toc}{chapter}{ABSTRACT}",
                    ]
                )
                continue
            if compact_clean.startswith("关键词：") or compact_clean.startswith("关键词:"):
                if phase == "cn_abstract":
                    keyword_text = re.sub(r"^\s*关键词\s*[：:]\s*", "", clean)
                    lines.extend(["", r"\par\noindent{\heiti 关键词：}" + latex_escape(keyword_text), ""])
                continue
            if clean.startswith("Keywords:"):
                if phase == "en_abstract":
                    lines.extend(
                        [
                            "",
                            r"\par\noindent{\bfseries Keywords:} "
                            + latex_escape(clean.removeprefix("Keywords:").strip()),
                            r"\clearpage",
                            r"\tableofcontents",
                            r"\clearpage",
                            r"\mainmatter",
                        ]
                    )
                    phase = "main"
                continue
            if phase == "before_abstract":
                continue

            if style == "afa" and clean.startswith("图"):
                caption = re.sub(r"^图\s*", "图", clean)
                if pending_images:
                    lines.extend(render_figure(pending_images, caption, media))
                    pending_images = []
                else:
                    lines.append(rf"\par\centerline{{{latex_escape(caption)}}}")
                continue
            if style == "afa" and clean.startswith("表"):
                pending_table_caption = clean
                continue
            if clean.startswith("(续)表") or clean.startswith("（续）表"):
                pending_table_caption = clean
                continue

            flush_images_without_caption()

            if style == "1":
                if phase != "main":
                    lines.extend([latex_escape(clean), ""])
                    continue
                title = strip_heading_number(clean)
                if in_refs and title != "参考文献":
                    lines.append(r"\end{thebibliography}")
                    in_refs = False
                if title == "参考文献":
                    lines.extend(
                        [
                            r"\chapter*{参考文献}",
                            r"\addcontentsline{toc}{chapter}{参考文献}",
                            r"\begin{thebibliography}{99}",
                        ]
                    )
                    in_refs = True
                    reference_no = 0
                elif title in {"结论", "攻读学士学位期间发表的论文和取得的科研成果"}:
                    lines.extend(
                        [
                            rf"\chapter*{{{latex_escape(title)}}}",
                            rf"\addcontentsline{{toc}}{{chapter}}{{{latex_escape(title)}}}",
                        ]
                    )
                else:
                    lines.append(rf"\chapter{{{latex_escape(title)}}}")
                continue
            if style == "2":
                if phase != "main":
                    lines.extend([latex_escape(clean), ""])
                    continue
                lines.append(rf"\section{{{latex_escape(strip_heading_number(clean))}}}")
                continue
            if style == "3":
                if phase != "main":
                    lines.extend([latex_escape(clean), ""])
                    continue
                lines.append(rf"\subsection{{{latex_escape(strip_heading_number(clean))}}}")
                continue

            if clean == "致谢":
                if in_refs:
                    lines.append(r"\end{thebibliography}")
                    in_refs = False
                lines.extend([r"\chapter*{致\quad 谢}", r"\addcontentsline{toc}{chapter}{致\quad 谢}"])
                continue

            if in_refs and clean:
                reference_no += 1
                lines.append(rf"\bibitem{{ref{reference_no}}} {latex_escape(clean)}")
            else:
                if phase in {"cn_abstract", "en_abstract", "main"}:
                    lines.extend([latex_escape(clean), ""])

        elif local == "tbl":
            if phase != "main":
                continue
            flush_images_without_caption()
            rows = table_rows(child)
            lines.extend(render_table(rows, pending_table_caption))
            pending_table_caption = None

    if in_refs:
        lines.append(r"\end{thebibliography}")
    flush_images_without_caption()
    lines.extend(render_end())
    OUT_TEX.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    generate()
