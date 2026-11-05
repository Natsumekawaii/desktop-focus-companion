"""Live-discovered regressions, replayed offline without any credential or API."""

from copy import deepcopy
from datetime import timedelta

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit
from test_agent import (
    NOW,
    commit,
    complete_call,
    creation,
    tools_for,
)
from test_agent import (
    controller as controller_fixture,
)
from test_agent import (
    focus as focus_fixture,
)

from app.agent.prompts import system_prompt
from app.agent.requests import WriteRequestContext, refused
from app.agent.validation import ToolValidationError
from app.core.theme import COLOR_THEMES, get_theme_manager
from app.data.focus_record_changes import snapshot
from app.i18n import get_localization, tr
from app.ui.agent_page import ToolCard
from app.ui.agent_preview import ChangePreview

controller = controller_fixture
focus = focus_fixture


@pytest.mark.parametrize(
    "message,count,ids",
    [
        ("请删除记录ID 1、2，整批确认。", 2, {1, 2}),
        ("Please delete record IDs 1 and 2 together.", 2, {1, 2}),
        ("Please add two records.", 2, set()),
        ("请新增两条记录。", 2, set()),
        ("请新增一条记录。", 1, set()),
    ],
)
def test_client_owns_explicit_count_and_target_scope(message, count, ids):
    context = WriteRequestContext.create(message)
    assert context is not None
    assert context.operation_count == count
    assert context.target_ids == ids
    assert context.batch == (count > 1)


def test_single_write_cannot_expand_into_batch(focus):
    args, text, context = v2_creation(focus[1])
    args["operations"].append(deepcopy(args["operations"][0]))
    with pytest.raises(ToolValidationError, match="scope"):
        tools_for(focus).prepare(args, [text], True, context=context)


def test_batch_ordinals_are_not_the_requested_count():
    context = WriteRequestContext.create("请批量新增：第一条工作，第二条学习。")
    assert context is not None and context.batch
    assert context.operation_count is None


@pytest.mark.parametrize(
    "message",
    [
        "只改备注为复习完成，其余字段全部不要改。",
        "Please only change the note to reviewed. Keep all other fields unchanged.",
    ],
)
def test_all_other_fields_does_not_turn_single_edit_into_batch(message):
    context = WriteRequestContext.create(message)
    assert context is not None and not context.batch
    assert context.operation_count == 1
    assert context.fields == {"note"}


def test_prompt_requires_real_confirmation_card_not_prose():
    text = system_prompt(NOW, "Asia/Shanghai", "zh-CN", True)
    assert "CALL apply_record_changes" in text
    assert "prose table" in text
    assert "before creating it" in text


@pytest.mark.parametrize("reply", ["记录ID 1", "record ID 1", "record 1"])
def test_record_identity_reply_continues_edit_not_create(controller, reply):
    controller.send("只改备注为复习完成，其他字段不要改。")
    request = controller._action_context
    assert request is not None
    controller.client.completed.emit(
        {"role": "assistant", "content": "请提供记录编号"}, {}
    )
    controller.send(reply)
    assert controller._action_context is request
    assert request.kinds == {"update"}
    assert request.fields == {"note"}


def v2_creation(item, context=None):
    legacy, text = creation(item)
    ctx = context or WriteRequestContext.create(text)
    assert ctx is not None
    op = legacy["operations"][0]
    refs = {key: [{"message_id": "u1", "quote": text}] for key in op["fields"]}
    return (
        {"request_id": ctx.request_id, "operations": [{**op, "evidence": refs}]},
        text,
        ctx,
    )


@pytest.mark.parametrize(
    "message",
    [
        "请修改记录ID 1，只把备注改成复习完成，其他字段都不要改。",
        "只改备注，其他字段不要改。",
        "请批量新增两条记录，整批展示预览让我确认，不要逐条自动保存。",
        "Please only change the note to reviewed. Do not change other fields.",
    ],
)
def test_scoped_constraints_keep_requested_authority(controller, message):
    controller.send(message)
    assert controller._write_allowed
    assert controller._action_context is not None


@pytest.mark.parametrize(
    "message",
    [
        "不要记录",
        "取消操作",
        "Don't record this",
        "Never delete my records",
        "新增记录，但不要保存",
    ],
)
def test_global_cancellation_still_denies_writing(message):
    assert refused(message)
    assert WriteRequestContext.create(message) is None


def test_clarification_without_question_mark_survives_with_source_ids(
    controller, focus, qt_wait_until
):
    controller.send("我早上上了2小时C语言课，帮我记一下。")
    identity = controller._action_context.request_id
    controller.client.completed.emit(
        {
            "role": "assistant",
            "content": "请补充日期、起止时间和所属项目。",
            "reasoning_content": "",
        },
        {},
    )
    assert controller.turn["clarification_open"]
    answer = "日期是2026-11-04，具体09:00到11:00，连续2小时，项目Learning。"
    controller.send(answer)
    assert controller._action_context.request_id == identity
    args, _, _ = v2_creation(focus[1], controller._action_context)
    args["operations"][0]["evidence"] = {
        k: [{"message_id": "u2", "quote": answer}]
        for k in args["operations"][0]["fields"]
    }
    complete_call(controller, "apply_record_changes", args)
    qt_wait_until(
        lambda: controller.worker is None and len(focus[2].list_sessions()) == 1
    )
    assert focus[2].list_sessions()[0].duration_seconds == 7200


@pytest.mark.parametrize(
    "next_message", ["查询本周统计", "你好", "What is my total?", "取消操作"]
)
def test_new_topic_revokes_pending_request(controller, next_message):
    controller.send("帮我记一下2小时课程")
    controller.client.completed.emit(
        {"role": "assistant", "content": "请补充时间和项目。"}, {}
    )
    controller.send(next_message)
    assert controller._action_context is None
    assert not controller._write_allowed


def test_stop_and_switch_do_not_restore_saved_authority(controller):
    controller.send("帮我记一下2小时课程")
    controller.client.completed.emit(
        {"role": "assistant", "content": "请补充时间和项目。"}, {}
    )
    chat = controller.conversation
    controller.new_conversation()
    controller.select_conversation(chat)
    controller.send("今天09:00到11:00，项目Learning")
    assert not controller._write_allowed


def test_v2_sources_span_messages_and_times_without_repeated_date(focus):
    ctx = WriteRequestContext.create(
        "请新增记录：2026-11-04 09:00到11:00，连续2小时，项目Learning。"
    )
    assert ctx
    args, _, _ = v2_creation(focus[1], ctx)
    args["operations"][0]["evidence"] = {
        "focus_item_id": [{"message_id": "u1", "quote": "Learning"}],
        "start_time": [
            {"message_id": "u1", "quote": "2026-11-04"},
            {"message_id": "u1", "quote": "09:00"},
        ],
        "end_time": [{"message_id": "u1", "quote": "11:00"}],
        "duration_seconds": [{"message_id": "u1", "quote": "2小时"}],
    }
    plan, _ = tools_for(focus).prepare(
        args, list(ctx.sources.values()), True, context=ctx
    )
    commit(focus[0], plan)
    assert len(focus[2].list_sessions()) == 1


@pytest.mark.parametrize(
    "defect",
    ["explanation", "joined_quote", "unknown_source", "old_request", "invented_note"],
)
def test_observed_bad_parameters_cannot_bypass_sources(focus, defect):
    args, text, ctx = v2_creation(focus[1])
    op = args["operations"][0]
    if defect == "old_request":
        args["request_id"] = "old-request"
    elif defect == "invented_note":
        op["fields"]["note"] = "invented content"
        op["evidence"]["note"] = [{"message_id": "u1", "quote": "Learning"}]
    else:
        ref = op["evidence"]["focus_item_id"][0]
        if defect == "explanation":
            ref["quote"] = 'User said "Learning"; ID read from context.'
        elif defect == "joined_quote":
            ref["quote"] = text + " / another message"
        else:
            ref["message_id"] = "database-note"
    with pytest.raises(ToolValidationError):
        tools_for(focus).prepare(args, [text], True, context=ctx)
    assert not focus[2].list_sessions()


def test_local_scope_locks_fields_and_target_ids(focus):
    first = focus[2].create(focus[1], NOW - timedelta(hours=2), NOW, 3600)
    second = focus[2].create(focus[1], NOW - timedelta(hours=2), NOW, 3600)
    ctx = WriteRequestContext.create(
        f"请修改记录ID {first.id}，只把备注改成reviewed，其他字段都不要改。"
    )
    assert ctx and ctx.fields == frozenset({"note"})
    tools = tools_for(focus)
    tools.execute("get_focus_record", {"record_id": second.id})
    args = {
        "request_id": ctx.request_id,
        "operations": [
            {
                "kind": "update",
                "record_id": second.id,
                "fields": {"note": "reviewed"},
                "evidence": {"note": [{"message_id": "u1", "quote": "reviewed"}]},
            }
        ],
    }
    with pytest.raises(ToolValidationError, match="scope"):
        tools.prepare(args, [], True, context=ctx)
    args["operations"][0]["record_id"] = first.id
    args["operations"][0]["fields"]["duration_seconds"] = 60
    args["operations"][0]["evidence"]["duration_seconds"] = [
        {"message_id": "u1", "quote": "reviewed"}
    ]
    with pytest.raises(ToolValidationError, match="scope"):
        tools.prepare(args, [], True, context=ctx)


def test_delete_contract_and_single_format_repair(controller, focus, qt_wait_until):
    record = focus[2].create(focus[1], NOW - timedelta(hours=2), NOW, 3600)
    controller.send(f"请删除记录ID {record.id}，先给我确认预览。")
    complete_call(controller, "get_focus_record", {"record_id": record.id}, "read")
    qt_wait_until(lambda: controller.worker is None)
    args = {
        "request_id": controller._action_context.request_id,
        "operations": [
            {
                "kind": "delete",
                "record_id": record.id,
                "fields": {},
                "evidence": {"note": "Existing record note is not user evidence"},
            }
        ],
    }
    complete_call(controller, "apply_record_changes", args, "bad")
    qt_wait_until(lambda: controller.worker is None)
    assert controller.turn["cards"][-1]["result"]["retry_format"]
    assert focus[2].list_sessions()
    args["operations"][0].pop("fields")
    args["operations"][0].pop("evidence")
    complete_call(controller, "apply_record_changes", args, "fixed")
    qt_wait_until(lambda: controller.worker is None)
    assert controller._pending is not None
    controller.confirm("fixed")
    qt_wait_until(lambda: controller.worker is None)
    assert not focus[2].list_sessions()


@pytest.mark.parametrize("repair", ["same_bad_format", "changed_value", "valid"])
def test_format_repair_is_bounded_and_value_locked(
    controller, focus, qt_wait_until, repair
):
    _, text, _ = v2_creation(focus[1])
    controller.send(text)
    args, _, _ = v2_creation(focus[1], controller._action_context)
    bad = deepcopy(args)
    bad["operations"][0]["evidence"]["focus_item_id"][0]["quote"] = (
        "User said Learning, from context."
    )
    complete_call(controller, "apply_record_changes", bad, "bad")
    qt_wait_until(lambda: controller.worker is None)
    assert controller.turn["cards"][-1]["result"]["retry_format"]
    if repair == "same_bad_format":
        args = bad
    elif repair == "changed_value":
        args["operations"][0]["fields"]["duration_seconds"] = 3600
    complete_call(controller, "apply_record_changes", args, "repair")
    qt_wait_until(lambda: controller.worker is None)
    if repair == "valid":
        assert len(focus[2].list_sessions()) == 1
        assert controller.turn["cards"][-1]["result"]["status"] == "committed"
    else:
        assert not controller.busy and not focus[2].list_sessions()
        assert not controller.turn["cards"][-1]["result"]["retry_format"]
        assert len(controller.client.requests) == 2


def test_duration_conflict_is_local_and_not_retried(controller, focus, qt_wait_until):
    text = "请新增记录：2026-11-04 09:00到10:00，实际2小时，项目Learning。"
    controller.send(text)
    args, _, _ = v2_creation(focus[1], controller._action_context)
    args["operations"][0]["fields"]["end_time"] = "2026-11-04T10:00:00+08:00"
    args["operations"][0]["evidence"] = {
        k: [{"message_id": "u1", "quote": text}]
        for k in args["operations"][0]["fields"]
    }
    complete_call(controller, "apply_record_changes", args)
    qt_wait_until(lambda: controller.worker is None)
    assert controller.turn["validation_error"]["code"] == "duration_conflict"
    assert controller.turn["answer"] == tr("agent.validation.duration_conflict")
    assert len(controller.client.requests) == 1 and not focus[2].list_sessions()


def test_preview_is_readable_responsive_without_json(focus):
    record = focus[2].create(
        focus[1], NOW - timedelta(hours=2), NOW, 3600, note="before note"
    )
    before = snapshot(record)
    after = {**before, "note": "after note <b>not HTML</b>"}
    change = {
        "kind": "update",
        "before": before,
        "after": after,
        "overlapping_record_ids": [88],
    }
    data = {
        "id": "test",
        "name": "apply_record_changes",
        "status": "awaiting_confirmation",
        "result": {"changes": [change], "requires_confirmation": True},
    }
    card = ToolCard(data)
    card.show()
    for width in (400, 700):
        card.resize(width, card.sizeHint().height())
        QTest.qWait(10)
        assert len(card.findChildren(ChangePreview)[0].rows) == 1
        assert not card.findChildren(QTextEdit)
        labels = [w.text() for w in card.findChildren(QLabel)]
        assert any("before note" in text for text in labels)
        assert any("after note <b>not HTML</b>" in text for text in labels)
        assert any("#88" in text for text in labels)
    assert (
        len(
            [
                w
                for w in card.findChildren(QPushButton)
                if w.text() == tr("agent.confirm")
            ]
        )
        == 1
    )
    stale = ToolCard(
        {
            **data,
            "status": "failed",
            "result": {"code": "stale_confirmation", "preview": data["result"]},
        }
    )
    assert not stale.findChildren(QPushButton)
    assert tr("agent.state.expired") in stale.header.text()
    assert stale.header.toolTip() == tr("agent.validation.stale_confirmation")


def test_preview_localization_theme_and_full_batch():
    for language in ("zh-CN", "en-US"):
        get_localization().set_language(language)
        for theme in COLOR_THEMES:
            get_theme_manager().set_theme(theme)
            changes = [
                {
                    "kind": "delete",
                    "before": {
                        "id": n,
                        "focus_item_name": "test",
                        "duration_seconds": 3600,
                        "note": f"note {n}",
                    },
                    "after": None,
                }
                for n in range(1, 51)
            ]
            card = ToolCard(
                {
                    "id": "test",
                    "name": "apply_record_changes",
                    "status": "awaiting_confirmation",
                    "result": {"changes": changes},
                }
            )
            assert len(card.findChildren(ChangePreview)) == 50
            assert (
                sum(
                    w.text() == tr("agent.confirm")
                    for w in card.findChildren(QPushButton)
                )
                == 1
            )
            card.deleteLater()
