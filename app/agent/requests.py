"""Client-owned write scope. Conversation prose never grants tool authority."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

WRITE_INTENT = re.compile(
    r"帮我.{0,20}(?:记|删|改)|补记|记一下|记上|记到|记录下来|新增|添加|删除|删掉|移除|修改|只改|仅改|改成|改为|更正|更新"
    r"|(?:^|[.!?]\s*|\b(?:please|can you|could you|would you|help me|I want you to)\s+)(?:only\s+)?(?:log|record|add|create|delete|remove|edit|update|change|correct)\b",
    re.IGNORECASE,
)
WRITE_REFUSAL = re.compile(
    r"取消(?:操作|记录|新增|修改|删除)?|算了|(?:不要|别|不用|不必|不需要).{0,12}(?:记|增|加|删|改|保存)"
    r"|\b(?:cancel|never mind)\b|\b(?:don't|do not|never)\s+(?:log|record|add|create|delete|remove|edit|update|change|save)\b",
    re.IGNORECASE,
)
BATCH_INTENT = re.compile(
    r"批量|整批|多条|(?:所有|全部)(?:的)?(?:记录|条目)|全部(?:删除|删掉|修改|更新)"
    r"|(?:两|二|三|四|五|六|七|八|九|十|\d+)条|\b(?:batch|multiple|all\s+(?:records|sessions)|\d+\s+(?:records|sessions))\b",
    re.IGNORECASE,
)
FIELD_WORDS = {
    "note": r"备注|\bnotes?\b",
    "focus_item_id": r"项目|\b(?:project|focus item)\b",
    "start_time": r"开始|起始|\bstart\b",
    "end_time": r"结束|\bend\b",
    "duration_seconds": r"时长|\bduration\b",
}


def instruction_text(text: str) -> str:
    # Quoted note contents must not act as a new instruction or a cancellation.
    return re.sub(r'“[^”]*”|「[^」]*」|"[^"\n]*"', "", text)


def limited_fields(text: str) -> frozenset[str] | None:
    text = instruction_text(text)
    match = re.search(
        r"(?:只(?:把|将|修改|改|更新)?|仅(?:修改|改|更新)?|\bonly\s+(?:change|edit|update)\s+(?:the\s+)?)"
        r"\s*(备注|项目|开始时间|结束时间|时长|note|project|focus item|start time|end time|duration)",
        text,
        re.IGNORECASE,
    )
    if match:
        return frozenset(
            k
            for k, pattern in FIELD_WORDS.items()
            if re.search(pattern, match[1], re.IGNORECASE)
        )
    return None


def refused(text: str) -> bool:
    text = instruction_text(text)
    # These constraints reduce permissions; they do not revoke the requested action.
    if limited_fields(text):
        text = re.sub(
            r"(?:其他|其它|其余).{0,8}(?:不要|别|不用).{0,4}(?:改|修改|更新)", "", text
        )
        text = re.sub(
            r"(?:don't|do not)\s+(?:change|edit|update)\s+(?:any\s+)?(?:other|anything else|the other)[^.!?]*",
            "",
            text,
            flags=re.IGNORECASE,
        )
    if BATCH_INTENT.search(text):
        text = re.sub(
            r"(?:不要|别).{0,3}(?:逐条|单独).{0,4}(?:保存|新增|添加|执行)", "", text
        )
        text = re.sub(
            r"(?:don't|do not)\s+(?:save|add|create|execute)[^.!?]*(?:one by one|individually)",
            "",
            text,
            flags=re.IGNORECASE,
        )
    return bool(WRITE_REFUSAL.search(text))


def is_analysis(text: str) -> bool:
    return bool(
        re.search(
            r"^(?:请|帮我)?\s*(?:查询|统计|分析|总结|解释|为什么|如何|怎么|哪些|多少)"
            r"|^(?:please\s+)?(?:show|query|analy[sz]e|summari[sz]e|explain|what|why|how)\b",
            text.strip(),
            re.IGNORECASE,
        )
    )


def is_supplement(text: str, item_names: list[str]) -> bool:
    if is_analysis(text) or refused(text):
        return False
    return bool(
        text.strip(" 。.!！").casefold() in {n.casefold() for n in item_names}
        or re.match(
            r"^(?:确认|是的|对的|没错|继续|重试|yes\b|confirm\b|retry\b)",
            text,
            re.IGNORECASE,
        )
        or re.match(
            r"^(?:日期|时间|具体|开始|结束|实际|连续|项目|所属|现有项目|备注|记录\s*(?:ID|编号|#|\d)|今天|昨天|\d{4}[-/年]|\d{1,2}[:：]|(?:the )?(?:date|time|project|record\s+(?:ID|#|\d))|use\b)",
            text,
            re.IGNORECASE,
        )
    )


@dataclass
class WriteRequestContext:
    request_id: str
    authorization: str
    kinds: frozenset[str]
    fields: frozenset[str] | None
    batch: bool
    target_ids: frozenset[int]
    operation_count: int | None
    sources: dict[str, str] = field(default_factory=dict)
    state: str = "awaiting_details"
    missing_fields: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, text: str) -> WriteRequestContext | None:
        clean = instruction_text(text)
        if re.fullmatch(r"\s*record\s+(?:ID\s*)?#?\d+[.!]?\s*", clean, re.IGNORECASE):
            return (
                None  # A record identity by itself is data, not a new create command.
            )
        if refused(text) or is_analysis(text) or not WRITE_INTENT.search(clean):
            return None
        kinds = set()
        if re.search(r"删除|删掉|移除|\b(?:delete|remove)\b", clean, re.IGNORECASE):
            kinds.add("delete")
        if re.search(
            r"修改|只改|仅改|改成|改为|更正|更新|\b(?:edit|update|change|correct)\b",
            clean,
            re.IGNORECASE,
        ):
            kinds.add("update")
        if re.search(
            r"新增|添加|补记|记一下|记上|记到|记录下来|帮我.{0,12}记|\b(?:log|add|create)\b",
            clean,
            re.IGNORECASE,
        ) or (not kinds and re.search(r"\brecord\b", clean, re.IGNORECASE)):
            kinds.add("create")
        if not kinds:
            return None
        target_groups = re.findall(
            r"(?:记录\s*(?:ID|编号|#)?|records?\s*(?:IDs?|#)?)\s*[:：]?\s*"
            r"(\d+(?:(?:\s*[,、和及&]\s*|\s+and\s+)\d+)*)",
            clean,
            re.IGNORECASE,
        )
        ids = frozenset(
            int(value) for group in target_groups for value in re.findall(r"\d+", group)
        )
        batch = bool(BATCH_INTENT.search(clean)) or len(ids) > 1
        count_match = re.search(
            r"(?<![第\d一二三四五六七八九十])(\d+|一|两|二|三|四|五|六|七|八|九|十)\s*条|\b(\d+|one|two|three|four|five)\s+(?:records|sessions)\b",
            clean,
            re.IGNORECASE,
        )
        count = None
        if count_match:
            value = (count_match[1] or count_match[2]).lower()
            numbers = {
                "一": 1,
                "两": 2,
                "二": 2,
                "三": 3,
                "四": 4,
                "五": 5,
                "六": 6,
                "七": 7,
                "八": 8,
                "九": 9,
                "十": 10,
                "one": 1,
                "two": 2,
                "three": 3,
                "four": 4,
                "five": 5,
            }
            count = int(value) if value.isdigit() else numbers[value]
            batch = batch or count > 1
        elif ids and kinds <= {"update", "delete"}:
            count = len(ids)
        elif not batch:
            count = 1
        instance = cls(
            str(uuid4()),
            text,
            frozenset(kinds),
            limited_fields(text),
            batch,
            ids,
            count,
        )
        instance.add_source(text)
        return instance

    def add_source(self, text: str) -> None:
        self.sources[f"u{len(self.sources) + 1}"] = text

    def payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "allowed_operations": sorted(self.kinds),
            "allowed_update_fields": sorted(self.fields)
            if self.fields is not None
            else None,
            "requires_batch": self.batch,
            "target_ids": sorted(self.target_ids),
            "operation_count": self.operation_count,
            "user_messages": self.sources,
            "state": self.state,
            "missing_fields": self.missing_fields,
        }
