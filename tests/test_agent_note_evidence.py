"""Note authorization regressions, using only temporary offline databases."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_agent import NOW, commit, complete_call, creation, tools_for
from test_agent import controller as controller_fixture
from test_agent import focus as focus_fixture

from app.agent.requests import WriteRequestContext
from app.agent.validation import ToolValidationError
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_record_changes import snapshot
from app.focus_mode import FocusMode

controller = controller_fixture
focus = focus_fixture


@pytest.fixture(params=["v1", "v1_with_context", "v2"])
def protocol(request):
    return request.param


def protocol_arguments(arguments, text, protocol):
    """Use the same genuine user quote through every supported entry path."""
    arguments = deepcopy(arguments)
    if protocol == "v1":
        return arguments, None
    context = WriteRequestContext.create(text)
    assert context is not None
    if protocol == "v2":
        arguments.pop("request_quote")
        arguments["request_id"] = context.request_id
        for operation in arguments["operations"]:
            operation["evidence"] = {
                field: [{"message_id": "u1", "quote": quote}]
                for field, quote in operation["evidence"].items()
            }
    return arguments, context


def update_arguments(record, text, fields):
    return {
        "request_quote": text,
        "operations": [
            {
                "kind": "update",
                "record_id": record.id,
                "fields": fields,
                "evidence": dict.fromkeys(fields, text),
            }
        ],
    }


def existing_record(focus):
    database, item, records = focus
    record = records.create(
        item,
        NOW - timedelta(hours=2, seconds=7),
        NOW - timedelta(seconds=3),
        3600,
        mode=FocusMode.COUNTDOWN,
        target_duration_seconds=7200,
        note="original note",
    )
    # Keep a historical non-minute duration, shorter than its wall-clock range.
    with database.connect() as connection:
        connection.execute(
            "UPDATE focus_sessions SET duration_seconds=3607 WHERE id=?",
            (record.id,),
        )
    return records.get(record.id)


def assert_no_receipts(database):
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM settings WHERE key LIKE 'agent.operation.%'"
            ).fetchone()[0]
            == 0
        )


def assert_note_rejected(tool, arguments, text, context):
    with pytest.raises(ToolValidationError) as error:
        tool.prepare(arguments, [text], True, context=context)
    assert error.value.code == "scope"
    assert error.value.field == "note"
    assert error.value.kind == "authorization"
    assert not tool.plan_prepared


def test_create_cannot_attach_note_absent_from_genuine_user_quote(focus, protocol):
    arguments, text = creation(focus[1])
    operation = arguments["operations"][0]
    operation["fields"]["note"] = "invented content"
    operation["evidence"]["note"] = text
    arguments, context = protocol_arguments(arguments, text, protocol)

    assert_note_rejected(tools_for(focus), arguments, text, context)

    assert focus[2].list_sessions() == []
    assert_no_receipts(focus[0])


@pytest.mark.parametrize("note", ["invented content", ""])
def test_update_cannot_invent_or_clear_note_without_value_evidence(
    focus, protocol, note
):
    record = existing_record(focus)
    before = snapshot(record)
    text = f"Please update record {record.id}."
    arguments = update_arguments(record, text, {"note": note})
    arguments, context = protocol_arguments(arguments, text, protocol)
    tool = tools_for(focus)
    tool.execute("get_focus_record", {"record_id": record.id})

    assert_note_rejected(tool, arguments, text, context)

    assert [snapshot(value) for value in focus[2].list_sessions()] == [before]
    assert_no_receipts(focus[0])


@pytest.mark.parametrize("include_note", [False, True])
def test_create_keeps_default_or_explicit_user_note(focus, protocol, include_note):
    arguments, text = creation(focus[1])
    expected_note = "reviewed chapter one" if include_note else ""
    if include_note:
        text += f" Note: {expected_note}."
        arguments["request_quote"] = text
        operation = arguments["operations"][0]
        operation["fields"]["note"] = expected_note
        operation["evidence"]["note"] = text
    arguments, context = protocol_arguments(arguments, text, protocol)

    plan, preview = tools_for(focus).prepare(arguments, [text], True, context=context)
    assert not preview["requires_confirmation"]
    commit(focus[0], plan)

    record = focus[2].list_sessions()[0]
    assert record.note == expected_note
    assert record.duration_seconds == 7200
    assert record.start_time.isoformat() == "2026-11-04T01:00:00+00:00"
    assert record.end_time.isoformat() == "2026-11-04T03:00:00+00:00"


@pytest.mark.parametrize(
    "instruction,note",
    [
        ("Please update the note to reviewed.", "reviewed"),
        ("Please update the note: clear it.", ""),
        ("请修改备注，清空备注。", ""),
    ],
)
def test_explicit_note_edit_preserves_time_duration_and_other_metadata(
    focus, protocol, instruction, note
):
    record = existing_record(focus)
    arguments = update_arguments(record, instruction, {"note": note})
    arguments, context = protocol_arguments(arguments, instruction, protocol)
    tool = tools_for(focus)
    tool.execute("get_focus_record", {"record_id": record.id})

    plan, preview = tool.prepare(arguments, [instruction], True, context=context)
    assert preview["requires_confirmation"]
    commit(focus[0], plan, confirmed=True)

    before, after = snapshot(record), snapshot(focus[2].get(record.id))
    assert after.pop("note") == note
    before.pop("note")
    before.pop("updated_at")
    after.pop("updated_at")
    assert before == after
    assert after["duration_seconds"] == 3607


def test_unrelated_update_preserves_omitted_note_times_and_actual_duration(
    focus, protocol
):
    record = existing_record(focus)
    item = FocusItemRepository(focus[0]).create("Work", "#14B8A6")
    text = f"Please update record {record.id} to project Work."
    arguments = update_arguments(record, text, {"focus_item_id": item.id})
    arguments, context = protocol_arguments(arguments, text, protocol)
    tool = tools_for(focus)
    tool.execute("get_focus_record", {"record_id": record.id})

    plan, preview = tool.prepare(arguments, [text], True, context=context)
    assert preview["changes"][0]["after"]["note"] == record.note
    commit(focus[0], plan, confirmed=True)

    before, after = snapshot(record), snapshot(focus[2].get(record.id))
    assert after["focus_item_id"] == item.id
    assert after["focus_item_name"] == item.name
    for field in ("focus_item_id", "focus_item_name", "updated_at"):
        before.pop(field)
        after.pop(field)
    assert before == after
    assert after["note"] == "original note"
    assert after["duration_seconds"] == 3607


def test_controller_legacy_create_does_not_auto_commit_invented_note(
    controller, focus, qt_wait_until
):
    arguments, text = creation(focus[1])
    operation = arguments["operations"][0]
    operation["fields"]["note"] = "invented content"
    operation["evidence"]["note"] = text
    controller.send(text)
    assert controller._action_context is not None

    complete_call(controller, "apply_record_changes", arguments)
    qt_wait_until(lambda: controller.worker is None)

    assert focus[2].list_sessions() == []
    assert_no_receipts(focus[0])
    assert controller._pending is None
    assert not controller.busy
    error = controller.turn["validation_error"]
    assert error["code"] == "scope"
    assert error["field"] == "note"
    assert error["category"] == "authorization"
    assert not controller.turn["cards"][-1]["result"]["retry_format"]
    assert len(controller.client.requests) == 1
