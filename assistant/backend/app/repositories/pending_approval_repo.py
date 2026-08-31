"""pending_approvals 持久化表的 repository。"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.pending_approval import PendingApproval


class PendingApprovalRepository:
    """工具调用审批请求的 CRUD 操作。"""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        request_id: str,
        conversation_id: int,
        tool_name: str,
        args_json: str,
        expire_at: datetime,
    ) -> PendingApproval:
        """插入新的待审批请求。"""
        row = PendingApproval(
            request_id=request_id,
            conversation_id=conversation_id,
            tool_name=tool_name,
            args_json=args_json,
            status="pending",
            expire_at=expire_at,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self, request_id: str) -> PendingApproval | None:
        """按唯一 request_id 获取单条审批请求。"""
        return (
            self.db.query(PendingApproval)
            .filter(PendingApproval.request_id == request_id)
            .first()
        )

    def update_status(self, request_id: str, status: str) -> PendingApproval | None:
        """将审批请求切换到新状态。

        有效状态：pending、approved、denied、expired。
        返回更新后的行；未找到时返回 None。
        """
        row = self.get(request_id)
        if row is None:
            return None
        row.status = status
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_pending_by_conversation(self, conversation_id: int) -> list[PendingApproval]:
        """返回某个会话中所有 pending（尚未处理）的请求。"""
        return (
            self.db.query(PendingApproval)
            .filter(
                PendingApproval.conversation_id == conversation_id,
                PendingApproval.status == "pending",
            )
            .all()
        )

    def expire_stale(self) -> int:
        """将所有超过 expire_at 的 pending 请求标记为 expired。

        返回受影响的行数。
        """
        now = datetime.now(timezone.utc)
        count = (
            self.db.query(PendingApproval)
            .filter(
                PendingApproval.status == "pending",
                PendingApproval.expire_at <= now,
            )
            .update({"status": "expired"})
        )
        self.db.commit()
        return count
