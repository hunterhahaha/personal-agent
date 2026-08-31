"""tool_results 持久化表的 repository。"""

from sqlalchemy.orm import Session

from app.models.tool_result import ToolResultRecord


class ToolResultRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(
        self,
        call_id: str,
        conversation_id: int,
        tool: str,
        full_output: str,
        summary: str,
    ) -> ToolResultRecord:
        row = self.db.query(ToolResultRecord).filter(
            ToolResultRecord.callID == call_id,
        ).first()
        if row:
            row.full_output = full_output
            row.summary = summary
        else:
            row = ToolResultRecord(
                callID=call_id,
                conversation_id=conversation_id,
                tool=tool,
                full_output=full_output,
                summary=summary,
            )
            self.db.add(row)
        self.db.commit()
        return row

    def get_by_call_id(self, call_id: str) -> ToolResultRecord | None:
        return self.db.query(ToolResultRecord).filter(
            ToolResultRecord.callID == call_id,
        ).first()
