import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import inspect, update
from sqlalchemy.orm import Session

from app.models.compression_log import CompressionLog
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.tool_result import ToolResultRecord
from app.repositories.base import BaseRepository
from app.utils.workspace import validate_user_workspace_root


class ConversationRepository(BaseRepository):
    model = Conversation

    def __init__(self, db: Session):
        super().__init__(db)

    def create(self, schema: BaseModel) -> Conversation:
        data = schema.model_dump()
        data["workspace_root"] = validate_user_workspace_root(data.get("workspace_root"))
        obj = Conversation(**data)
        obj.session_id = f"ses_{uuid.uuid4().hex[:20]}"
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def find_all(self, skip: int = 0, limit: int = 100) -> list:
        return (
            self.db.query(self.model)
            .order_by(self.model.updated_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_all(self) -> int:
        """返回会话总数。"""
        return self.db.query(self.model).count()

    def count_messages(self, conversation_id: int) -> int:
        """返回指定会话中的消息总数。"""
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .count()
        )

    def find_messages(
        self,
        conversation_id: int,
        skip: int = 0,
        limit: int = 100,
        order: str = "asc",
        exclude_id: Optional[int] = None,
    ) -> list[Message]:
        query = self.db.query(Message).filter(
            Message.conversation_id == conversation_id
        )

        if exclude_id is not None:
            query = query.filter(Message.id != exclude_id)

        if order == "desc":
            query = query.order_by(Message.created_at.desc())
        else:
            query = query.order_by(Message.created_at)

        query = query.offset(skip).limit(limit)
        return query.all()

    def add_message(
        self,
        conversation_id: int,
        msg_type: str,
        msg_json: dict,
        turn_index: int | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            msg_type=msg_type,
            msg_json=msg_json,
            turn_index=turn_index,
        )
        self.db.add(msg)
        conv = self.find_by_id(conversation_id)
        if conv:
            conv.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def increment_successful_turn_count(self, conversation_id: int) -> int | None:
        """成功完成一轮用户对话后递增计数，并返回新计数。"""
        result = self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(
                successful_turn_count=Conversation.successful_turn_count + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount == 0:
            self.db.rollback()
            return None

        self.db.commit()
        conv = self.find_by_id(conversation_id)
        if conv is None:
            return None
        self.db.refresh(conv)
        return conv.successful_turn_count

    def reserve_turn_index(self, conversation_id: int) -> int | None:
        """为一次用户发送原子预留轮次编号，并返回新编号。"""
        result = self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(
                turn_count=Conversation.turn_count + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount == 0:
            self.db.rollback()
            return None

        self.db.commit()
        conv = self.find_by_id(conversation_id)
        if conv is None:
            return None
        self.db.refresh(conv)
        return conv.turn_count

    def delete(self, id: int) -> bool:
        """删除会话，并级联删除相关记录。

        删除会话本身之前，先删除关联的 tool_results、compression_logs 和
        messages；所有操作都在同一个事务中完成。
        """
        obj = self.find_by_id(id)
        if obj is None:
            return False

        # 按 conversation_id 级联删除相关记录。tool_results / compression_logs
        # 可能由轻量测试库跳过 raw SQL migration，因此清理前先确认表存在。
        existing_tables = set(inspect(self.db.bind).get_table_names())
        if ToolResultRecord.__tablename__ in existing_tables:
            self.db.query(ToolResultRecord).filter(
                ToolResultRecord.conversation_id == id
            ).delete(synchronize_session=False)
        if CompressionLog.__tablename__ in existing_tables:
            self.db.query(CompressionLog).filter(
                CompressionLog.conversation_id == id
            ).delete(synchronize_session=False)
        self.db.query(Message).filter(
            Message.conversation_id == id
        ).delete(synchronize_session=False)

        self.db.delete(obj)
        self.db.commit()
        return True

