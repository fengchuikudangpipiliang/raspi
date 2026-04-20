import hashlib
import hmac
import re
import secrets


PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 240_000


def normalize_name(value: str) -> str:
    """
    统一姓名输入，减少因为首尾空格和连续空白导致的误判。
    """
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_code(value: str) -> str:
    """
    统一学号/工号格式。
    当前规则是去空白后转大写，方便名单导入、注册和登录共用一套匹配逻辑。
    """
    return re.sub(r"\s+", "", (value or "").strip()).upper()


def hash_secret(secret: str) -> str:
    """
    用 PBKDF2 生成可存库的密码哈希。
    不直接保存明文，避免本地数据库泄露时把初始密码和登录密码一并暴露。
    """
    salt = secrets.token_hex(16)
    derived_key = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        secret.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${derived_key.hex()}"


def verify_secret(secret: str, stored_hash: str) -> bool:
    """
    校验用户输入和存库哈希是否一致。
    这里兼容格式损坏场景，避免异常直接把接口打崩。
    """
    try:
        algorithm, iterations, salt, digest = (stored_hash or "").split("$", 3)
        if algorithm != f"pbkdf2_{PBKDF2_ALGORITHM}":
            return False
        derived_key = hashlib.pbkdf2_hmac(
            PBKDF2_ALGORITHM,
            secret.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        return hmac.compare_digest(derived_key.hex(), digest)
    except Exception:
        return False


def validate_initial_password(initial_password: str) -> None:
    """
    校验管理员预置初始密码是否太弱。
    成员名单导入阶段就先做一次兜底，避免导入明显不可用的数据。
    """
    if len((initial_password or "").strip()) < 6:
        raise ValueError("初始密码至少需要 6 个字符。")


def validate_new_password(code: str, name: str, initial_password: str, new_password: str, confirm_password: str) -> str:
    """
    首次注册和后续改密共用的新密码校验。
    规则尽量明确可解释，不搞隐藏门槛。
    """
    password = (new_password or "").strip()
    confirm = (confirm_password or "").strip()
    if not password:
        raise ValueError("请输入新密码。")
    if password != confirm:
        raise ValueError("两次输入的新密码不一致。")
    if len(password) < 8:
        raise ValueError("新密码至少需要 8 个字符。")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("新密码至少包含 1 个字母和 1 个数字。")
    if normalize_code(code) and normalize_code(code) in normalize_code(password):
        raise ValueError("新密码不能直接包含完整学号或工号。")
    if normalize_name(name) and normalize_name(name) == normalize_name(password):
        raise ValueError("新密码不能与姓名完全相同。")
    if password == (initial_password or "").strip():
        raise ValueError("新密码不能与初始密码相同。")
    return password
