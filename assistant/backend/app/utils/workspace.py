"""工作区路径规范化与边界判断。"""

import os
import re
import shlex
from pathlib import Path


DEFAULT_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent / "workspace"

_WINDOWS_ABSOLUTE_RE = re.compile(r"^[a-zA-Z]:[\\/]")
_CD_RE = re.compile(r"(?:^|[;&|]\s*)cd\s+(?:/d\s+)?(?P<path>\"[^\"]+\"|'[^']+'|[^\s;&|]+)", re.IGNORECASE)
_ENV_VAR_RE = re.compile(r"(%[A-Za-z_][A-Za-z0-9_]*%|\$env:|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?)")
_INLINE_INTERPRETER_RE = re.compile(r"\b(python|py|node|powershell|pwsh|cmd)\b.*\s(-c|-command|/c)\b", re.IGNORECASE)
_REDIRECT_RE = re.compile(r"(?<![<>&])([<>]{1,2})(?![<>&])")


def normalize_workspace_root(path: str | None) -> str:
    """返回规范化后的工作区绝对路径；空值回退到默认工作区。"""
    raw = (path or "").strip()
    target = Path(raw).expanduser() if raw else _ensure_default_workspace_root()
    return str(target.resolve(strict=False))


def validate_user_workspace_root(path: str | None) -> str:
    """校验用户选择的工作区路径，避免把过宽目录当作安全边界。"""
    normalized = normalize_workspace_root(path)
    target = Path(normalized)
    if not target.exists():
        raise ValueError(f"工作区路径不存在: {normalized}")
    if not target.is_dir():
        raise ValueError(f"工作区必须是文件夹: {normalized}")
    if _is_forbidden_workspace_root(target):
        raise ValueError(f"不允许将过宽或系统目录作为工作区: {normalized}")
    return normalized


def resolve_workspace_path(path: str | None, workspace_root: str) -> str:
    """在工作区内解析一个 cwd/path；空值表示工作区根。"""
    root = Path(normalize_workspace_root(workspace_root))
    raw = (path or "").strip()
    target = Path(raw).expanduser() if raw else root
    if not target.is_absolute():
        target = root / target
    return str(target.resolve(strict=False))


def is_path_within(path: str | Path, workspace_root: str) -> bool:
    """判断路径是否位于工作区内，兼容 Windows 大小写。"""
    root = Path(normalize_workspace_root(workspace_root)).resolve(strict=False)
    target = Path(path).expanduser().resolve(strict=False)
    try:
        if os.name == "nt":
            root_cmp = os.path.normcase(str(root))
            target_cmp = os.path.normcase(str(target))
            return target_cmp == root_cmp or target_cmp.startswith(root_cmp.rstrip("\\/") + os.sep)
        target.relative_to(root)
        return True
    except ValueError:
        return False


def command_workspace_violation(
    command: str,
    workspace_root: str | None,
    cwd: str | None = None,
) -> str | None:
    """检查命令是否明确引用工作区外路径。

    v1 对高确定性越界直接命中；对相对逃逸、环境变量、重定向和解释器
    内联代码等难以可靠静态解析的表达保守触发审批。
    """
    root = normalize_workspace_root(workspace_root)
    resolved_cwd = resolve_workspace_path(cwd, root)
    if not is_path_within(resolved_cwd, root):
        return f"cwd outside workspace: {resolved_cwd}"

    suspicious = _suspicious_shell_construct(command or "")
    if suspicious:
        return suspicious

    for match in _CD_RE.finditer(command or ""):
        raw_path = _strip_quotes(match.group("path"))
        resolved = resolve_workspace_path(raw_path, root)
        if not is_path_within(resolved, root):
            return f"cd outside workspace: {resolved}"

    for token in _split_command_tokens(command):
        candidate = _strip_quotes(token)
        if _looks_absolute_path(candidate):
            resolved = Path(candidate).expanduser().resolve(strict=False)
            if not is_path_within(resolved, root):
                return f"path outside workspace: {resolved}"

    return None


def _is_forbidden_workspace_root(path: Path) -> bool:
    text = os.path.normcase(str(path.resolve(strict=False))).rstrip("\\/")
    anchor = os.path.normcase(path.anchor).rstrip("\\/")
    if text == anchor:
        return True
    home = os.path.normcase(str(Path.home().resolve(strict=False)))
    if text == home:
        return True
    if os.name == "nt":
        forbidden = [
            os.environ.get("SystemRoot", r"C:\Windows"),
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("APPDATA", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        if str(path).startswith("\\\\"):
            return True
        return any(item and text == os.path.normcase(item) for item in forbidden)
    return text in {"/", "/etc", "/usr", "/var", "/home"}


def _ensure_default_workspace_root() -> Path:
    if not DEFAULT_WORKSPACE_ROOT.exists():
        DEFAULT_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    return DEFAULT_WORKSPACE_ROOT


def _suspicious_shell_construct(command: str) -> str | None:
    if ".." in command:
        return "command contains relative parent traversal '..'"
    if "~" in command:
        return "command contains home-directory expansion '~'"
    if _ENV_VAR_RE.search(command):
        return "command contains environment variable expansion"
    if _REDIRECT_RE.search(command):
        return "command contains shell redirection"
    if _INLINE_INTERPRETER_RE.search(command):
        return "command contains inline interpreter execution"
    if "*" in command or "?" in command:
        return "command contains wildcard expansion"
    return None


def _strip_quotes(value: str) -> str:
    return value.strip().strip("\"'")


def _looks_absolute_path(value: str) -> bool:
    if not value:
        return False
    if os.name == "nt":
        return value.startswith("\\\\") or bool(_WINDOWS_ABSOLUTE_RE.match(value))
    return value.startswith("/")


def _split_command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return re.split(r"\s+", command or "")
