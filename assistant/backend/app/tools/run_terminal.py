"""通用 shell 命令执行工具：只有高危命令需要审批。

此工具用于执行 shell 命令，例如读取文件、修改文件、网络请求、脚本运行、进程检查等。

安全命令会立即执行。匹配高危模式的命令必须先获得用户审批。
"""

import asyncio
import logging
import subprocess
import time

from app.schemas.message import ToolResult
from app.utils.workspace import (
    command_workspace_violation,
    normalize_workspace_root,
    resolve_workspace_path,
)

logger = logging.getLogger(__name__)

REQUIRES_APPROVAL = True

# ---------------------------------------------------------------------------
# 高危命令模式（全部小写，用于大小写不敏感匹配）
# ---------------------------------------------------------------------------

DANGEROUS_PATTERNS: list[str] = [
    # ---- 破坏性文件/磁盘操作 ----
    "rm -rf /", "rm -rf /*", "rm -r /", "rm -rf ~",
    "rd /s /q", "rmdir /s /q", "del /f /s /q",
    "remove-item -recurse -force", "ri -recurse -force",
    # 磁盘、分区和格式化
    "dd if=", "dd of=", "mkfs.", "format ", "fdisk", "parted", "mkswap",
    "diskpart", "clean all",
    # ---- 系统状态变更 ----
    "shutdown", "reboot", "poweroff", "halt", "init 0", "init 6",
    # ---- 权限和用户管理 ----
    "sudo ", "chmod -r",
    "chown", "passwd", "chpasswd",
    "useradd", "userdel", "usermod", "groupadd", "groupdel",
    # ---- 进程管理 ----
    "kill -9", "killall -9", "pkill -f", "taskkill /f", "stop-process -force",
    # ---- 防火墙和网络 ----
    "iptables", "ufw ", "nft ",
    # ---- 启动和固件 ----
    "bcdedit", "bootrec", "bootsect", "grub",
    # ---- 注册表（Windows）----
    "reg delete", "reg add", "reg import",
    # ---- 加密和擦除 ----
    "cipher /w:", "cipher /d", "sdelete", "shred ", "wipe ",
    # ---- 包管理（破坏性）----
    "apt remove", "apt purge", "apt autoremove", "dpkg -r", "dpkg --purge",
    "rpm -e", "pacman -r", "pip uninstall -y", "pip uninstall --yes",
    "npm uninstall",
    # ---- shell 派生炸弹 ----
    ":(){",
]


def is_dangerous_command(command: str) -> bool:
    cmd_lower = command.strip().lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            logger.warning("Dangerous command detected — pattern '%s' matched in: %s",
                           pattern, command[:150])
            return True
    return False


TOOL_DEFINITION = {
    "name": "run_terminal",
    "description": "在用户终端执行 shell 命令，包括读取/修改文件、网络请求（curl/wget）、"
    "运行脚本（python/node）、进程管理、系统信息查看等。"
    "注意：高危命令（如 rm -rf /、dd、format、shutdown、sudo 等）会自动拦截并需要用户审批。"
    "安全命令无需审批，直接执行。",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令",
            },
            "cwd": {
                "type": "string",
                "description": "可选工作目录；必须位于当前会话工作区内",
            },
        },
        "required": ["command"],
    },
}

_MAX_STDOUT = 4000
_MAX_STDERR = 1000
_TIMEOUT = 30


async def execute(
    command: str,
    cwd: str | None = None,
    approved: bool = False,
    _workspace_root: str | None = None,
) -> ToolResult:
    command = command.strip()
    t0 = time.monotonic()
    dangerous = is_dangerous_command(command)
    matched = _matched_pattern(command) if dangerous else None
    workspace_root = normalize_workspace_root(_workspace_root) if _workspace_root else None
    workspace_violation = (
        command_workspace_violation(command, workspace_root, cwd)
        if workspace_root else None
    )
    approval_needed = dangerous or workspace_violation is not None

    if not command:
        return ToolResult(
            state={"status": "error", "input": {"command": command}, "output": None,
                   "error": "命令为空", "summary": "命令为空，未执行",
                   "dangerous": False, "dangerous_pattern": None},
            metadata={"duration_ms": 0, "truncated": False,
                      "approval_required": False, "approval_granted": None,
                      "provider": "subprocess", "extra": {}},
            content="[命令为空，未执行]",
        )

    # ---- 高危命令门禁 ----
    if approval_needed:
        if not approved:
            error = (
                "命令访问了工作区外路径，需要用户审批"
                if workspace_violation else "高危命令，需要用户审批"
            )
            summary = (
                f"工作区路径越界: {workspace_violation}"
                if workspace_violation else f"高危命令被拦截: {matched}"
            )
            return ToolResult(
                state={"status": "blocked", "input": {"command": command, "cwd": cwd},
                       "output": None,
                       "error": error,
                       "summary": summary,
                       "dangerous": True,
                       "dangerous_pattern": matched,
                       "workspace_violation": workspace_violation,
                       "approved": False},
                metadata={"duration_ms": (time.monotonic() - t0) * 1000,
                          "truncated": False,
                          "approval_required": True,
                          "approval_granted": False,
                          "provider": "subprocess", "extra": {}},
                content="[此命令被识别为高危操作，需要用户审批后才能执行。请等待用户批准。]",
            )
        logger.warning("Executing APPROVED gated command: %s", command[:200])
    else:
        logger.info("Executing safe terminal command: %s", command[:200])

    # ---- 执行 ----
    try:
        resolved_cwd = (
            resolve_workspace_path(cwd, workspace_root)
            if workspace_root else cwd
        )
        process = await asyncio.to_thread(
            subprocess.run, command, shell=True,
            capture_output=True, timeout=_TIMEOUT, cwd=resolved_cwd)
        stdout = process.stdout.decode("utf-8", errors="replace")
        stderr = process.stderr.decode("utf-8", errors="replace")
        exit_code = process.returncode
        dur_ms = (time.monotonic() - t0) * 1000

        status = "success" if exit_code == 0 else "error"
        return ToolResult(
            state={
                "status": status,
                "input": {"command": command, "cwd": resolved_cwd},
                "output": {
                    "stdout": stdout[:_MAX_STDOUT],
                    "stderr": stderr[:_MAX_STDERR],
                    "exit_code": exit_code,
                    "stdout_truncated": len(stdout) > _MAX_STDOUT,
                    "stderr_truncated": len(stderr) > _MAX_STDERR,
                },
                "summary": f"exit_code={exit_code}"
                + (f", stdout={len(stdout)} chars" if stdout else ""),
                "dangerous": dangerous,
                "dangerous_pattern": matched,
                "workspace_violation": workspace_violation,
                "approved": not approval_needed or approved,
            },
            metadata={
                "duration_ms": round(dur_ms, 1),
                "truncated": len(stdout) > _MAX_STDOUT or len(stderr) > _MAX_STDERR,
                "approval_required": approval_needed,
                "approval_granted": not approval_needed or approved,
                "provider": "subprocess",
                "extra": {"timeout_seconds": _TIMEOUT,
                          "command_length": len(command),
                          "workspace_root": workspace_root,
                          "cwd": resolved_cwd},
            },
            content=_build_content(stdout, stderr, exit_code),
        )

    except subprocess.TimeoutExpired:
        dur_ms = (time.monotonic() - t0) * 1000
        return ToolResult(
            state={"status": "timeout", "input": {"command": command},
                   "output": None, "error": "命令执行超时（30秒）",
                   "summary": "timeout after 30s",
                   "dangerous": dangerous, "dangerous_pattern": matched,
                   "workspace_violation": workspace_violation},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": approval_needed,
                      "approval_granted": not approval_needed or approved,
                      "provider": "subprocess",
                      "extra": {"timeout_seconds": _TIMEOUT}},
            content="[命令执行超时（30秒）]",
        )
    except Exception as e:
        dur_ms = (time.monotonic() - t0) * 1000
        logger.error("Terminal command failed: %s (type=%s)", e, type(e).__name__, exc_info=True)
        return ToolResult(
            state={"status": "error", "input": {"command": command},
                   "output": None, "error": f"{type(e).__name__}: {e}",
                   "summary": f"执行失败: {type(e).__name__}",
                   "dangerous": dangerous, "dangerous_pattern": matched,
                   "workspace_violation": workspace_violation},
            metadata={"duration_ms": round(dur_ms, 1), "truncated": False,
                      "approval_required": approval_needed,
                      "approval_granted": not approval_needed or approved,
                      "provider": "subprocess",
                      "extra": {"timeout_seconds": _TIMEOUT}},
            content=f"[命令执行失败: {type(e).__name__}: {e}]",
        )


def _matched_pattern(command: str) -> str | None:
    cmd_lower = command.strip().lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return pattern
    return None


def _build_content(stdout: str, stderr: str, exit_code: int) -> str:
    parts: list[str] = []
    if stdout:
        parts.append(stdout[:_MAX_STDOUT])
    if stderr:
        parts.append(f"[stderr]\n{stderr[:_MAX_STDERR]}")
    parts.append(f"[exit_code: {exit_code}]")
    return "\n".join(parts)
