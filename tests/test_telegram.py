from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

from app.telegram.bot import (
    AUDIT_URL,
    COMPETITORS,
    PRIMARY_KEYWORD,
    SECONDARY_KEYWORDS,
    SELECT_WEBSITE,
    TOPIC,
    _content_progress,
    _format_audit_report,
    _register_process,
    audit_command,
    build_application,
    cancel_content,
    collect_competitors,
    collect_primary,
    collect_secondary,
    collect_website,
    content_command,
    help_command,
    report_command,
    start_command,
)


@pytest.mark.asyncio
async def test_cancel_stops_active_work_and_discards_its_record(monkeypatch) -> None:
    started = asyncio.Event()

    async def work() -> None:
        started.set()
        await asyncio.Event().wait()

    application = SimpleNamespace(bot_data={})
    task = asyncio.create_task(work())
    _register_process(application, "42", task, "content generation", 17)
    await started.wait()
    discard = AsyncMock()
    monkeypatch.setattr("app.telegram.bot._discard_content_job", discard)
    update = make_update()
    context = SimpleNamespace(application=application, user_data={})

    assert await cancel_content(update, context) == ConversationHandler.END

    assert task.cancelled()
    discard.assert_awaited_once_with(17)
    assert "No cancelled run or partial report was saved" in (
        update.message.reply_text.await_args.args[0]
    )


def make_update(text: str = "") -> MagicMock:
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.message.chat_id = 100
    update.message.reply_text = AsyncMock()
    update.message.reply_document = AsyncMock()
    update.effective_user.id = 42
    update.effective_chat.id = 100
    return update


@pytest.mark.asyncio
async def test_start_command_replies_with_online_message() -> None:
    update = make_update()
    await start_command(update, MagicMock())
    update.message.reply_text.assert_awaited_once_with(
        "SEO Automation Bot is online.\n\nUse /help to see available commands."
    )


@pytest.mark.asyncio
async def test_help_lists_required_commands() -> None:
    update = make_update()
    await help_command(update, MagicMock())
    text = update.message.reply_text.await_args.args[0]
    for command in ("/audit", "/audits", "/report", "/content", "/status"):
        assert command in text


@pytest.mark.asyncio
async def test_audit_requires_and_validates_url() -> None:
    update = make_update()
    context = MagicMock()
    context.args = []
    assert await audit_command(update, context) == AUDIT_URL
    assert "Enter the website URL" in update.message.reply_text.await_args.args[0]

    update = make_update()
    context.args = ["example.com"]
    progress = MagicMock(message_id=9)
    update.message.reply_text.return_value = progress
    context.application.create_task = MagicMock()
    with patch("app.telegram.bot.RetentionManager.ensure_capacity", new=AsyncMock()):
        assert await audit_command(update, context) == ConversationHandler.END
    created = context.application.create_task.call_args.args[0]
    created.close()
    assert context.application.create_task.call_args.kwargs["name"] == "seo-audit:https://example.com"

    update = make_update()
    context.args = ["ftp://example.com"]
    assert await audit_command(update, context) == AUDIT_URL
    assert "valid URL" in update.message.reply_text.await_args.args[0]

    update = make_update()
    context.args = ["https://example.com", "extra"]
    assert await audit_command(update, context) == AUDIT_URL
    assert "Enter one complete website URL" in update.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_report_retrieves_only_matching_audit_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "data" / "reports" / "audit_5.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps({"website": "https://traderai.ai/"}), encoding="utf-8"
    )
    audit = SimpleNamespace(
        id=5,
        status="completed",
        output_data={"report_path": str(report_path)},
    )
    project = SimpleNamespace(website_url="https://traderai.ai")

    class FakeSession:
        async def execute(self, statement):
            del statement
            return SimpleNamespace(first=lambda: (audit, project))

    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    monkeypatch.setattr("app.telegram.bot.get_session", fake_session)
    monkeypatch.setattr("app.telegram.bot.PROJECT_ROOT", tmp_path)
    update = make_update()
    context = MagicMock(args=["5"])
    await report_command(update, context)

    update.message.reply_document.assert_awaited_once()
    document = update.message.reply_document.await_args.kwargs["document"]
    assert document.getvalue().startswith(b"%PDF")
    assert update.message.reply_document.await_args.kwargs["filename"] == "seo_audit_5.pdf"
    assert "traderai.ai" in update.message.reply_document.await_args.kwargs["caption"]


@pytest.mark.asyncio
async def test_report_rejects_legacy_shared_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "data" / "reports" / "zeetech_seo_audit.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps({"website": "https://traderai.ai/"}), encoding="utf-8"
    )
    audit = SimpleNamespace(
        id=5,
        status="completed",
        output_data={"report_path": str(report_path)},
    )
    project = SimpleNamespace(website_url="https://traderai.ai")

    class FakeSession:
        async def execute(self, statement):
            del statement
            return SimpleNamespace(first=lambda: (audit, project))

    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    monkeypatch.setattr("app.telegram.bot.get_session", fake_session)
    monkeypatch.setattr("app.telegram.bot.PROJECT_ROOT", tmp_path)
    update = make_update()
    await report_command(update, MagicMock(args=["5"]))

    assert "legacy shared report" in update.message.reply_text.await_args.args[0]
    update.message.reply_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_audit_starts_background_task() -> None:
    update = make_update()
    progress = MagicMock(message_id=9)
    update.message.reply_text.return_value = progress
    context = MagicMock()
    context.args = ["https://example.com"]
    context.application.create_task = MagicMock()
    with patch("app.telegram.bot.RetentionManager.ensure_capacity", new=AsyncMock()):
        await audit_command(update, context)
    context.application.create_task.assert_called_once()
    context.application.create_task.call_args.args[0].close()


@pytest.mark.asyncio
async def test_content_requires_explicit_website_selection(monkeypatch) -> None:
    project = SimpleNamespace(id=3, website_url="https://selected.example")
    audit = SimpleNamespace(
        id=17,
        output_data={"pages_crawled": 8, "issues_created": 4},
    )

    class FakeRepository:
        async def list_completed_audits(self, session, requester_id, limit):
            del session, requester_id, limit
            return [(project, audit)]

    @asynccontextmanager
    async def fake_session():
        yield object()

    monkeypatch.setattr("app.telegram.bot.ContentRepository", FakeRepository)
    monkeypatch.setattr("app.telegram.bot.get_session", fake_session)
    monkeypatch.setattr("app.telegram.bot.init_db", AsyncMock())
    monkeypatch.setattr(
        "app.telegram.bot.RetentionManager.ensure_capacity", AsyncMock()
    )
    update = make_update()
    context = MagicMock()
    context.user_data = {}

    assert await content_command(update, context) == SELECT_WEBSITE
    response = update.message.reply_text.await_args.args[0]
    assert "Select a website" in response
    assert "Audit #17" in response
    assert context.user_data["content_input"] == {}


@pytest.mark.asyncio
async def test_collect_website_uses_only_selected_owned_audit(monkeypatch) -> None:
    project = SimpleNamespace(id=3, website_url="https://selected.example")
    audit = SimpleNamespace(id=17)

    class FakeRepository:
        async def get_owned_completed_audit(self, session, audit_id, requester_id):
            del session, requester_id
            return (project, audit) if audit_id == 17 else None

    @asynccontextmanager
    async def fake_session():
        yield object()

    monkeypatch.setattr("app.telegram.bot.ContentRepository", FakeRepository)
    monkeypatch.setattr("app.telegram.bot.get_session", fake_session)
    context = MagicMock()
    context.user_data = {"content_input": {}}

    assert await collect_website(make_update("99"), context) == SELECT_WEBSITE
    update = make_update("17")
    assert await collect_website(update, context) == PRIMARY_KEYWORD
    assert context.user_data["content_input"] == {
        "project_id": 3,
        "audit_run_id": 17,
        "website_url": "https://selected.example",
    }


def test_human_audit_report_explains_nature_location_and_action() -> None:
    report = {
        "website": "https://example.com/",
        "pages_crawled": 1,
        "pages": [
            {
                "url": "https://example.com/pricing",
                "issues": ["Missing meta description"],
            }
        ],
        "errors": [],
    }

    text = "\n".join(_format_audit_report(report, 7))
    assert "Nature: On-page SEO" in text
    assert "Page: https://example.com/pricing" in text
    assert 'Location: HTML <meta name="description"> element' in text
    assert "Recommended action:" in text


@pytest.mark.asyncio
async def test_content_input_steps_validate_and_store_values() -> None:
    context = MagicMock()
    context.user_data = {"content_input": {"website_url": "https://traderai.ai"}}

    update = make_update("AI trading bot")
    assert await collect_primary(update, context) == SECONDARY_KEYWORDS
    assert context.user_data["content_input"]["primary_keyword"] == "AI trading bot"

    update = make_update("automated trading, crypto bot, automated trading")
    assert await collect_secondary(update, context) == COMPETITORS
    assert context.user_data["content_input"]["secondary_keywords"] == [
        "automated trading",
        "crypto bot",
    ]

    update = make_update("https://one.example/a\nhttps://two.example/b")
    assert await collect_competitors(update, context) == TOPIC
    assert len(context.user_data["content_input"]["competitor_urls"]) == 2
    assert "contact_url" not in context.user_data["content_input"]
    assert "login_url" not in context.user_data["content_input"]
    assert "automatically" in update.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_invalid_content_inputs_remain_on_current_step() -> None:
    context = MagicMock()
    context.user_data = {"content_input": {"website_url": "https://traderai.ai"}}
    assert await collect_primary(make_update("x"), context) == PRIMARY_KEYWORD
    assert await collect_secondary(make_update(""), context) == SECONDARY_KEYWORDS
    assert await collect_competitors(make_update("invalid"), context) == COMPETITORS
    homepage_update = make_update("one.example\nhttps://two.example/article")
    assert await collect_competitors(homepage_update, context) == TOPIC
    assert context.user_data["content_input"]["competitor_urls"][0] == "https://one.example"
    assert (
        await collect_competitors(make_update("https://one.example/article"), context)
        == TOPIC
    )


def test_progress_message_tracks_stages_and_revisions() -> None:
    text = _content_progress("example.com", "keyword", "revision", 2)
    assert "Revision: 2" in text
    assert "Content Strategist" in text
    assert "Content Writer" in text
    assert "Reviewer" in text


def test_build_application_registers_required_handlers() -> None:
    with (
        patch("app.telegram.bot.TELEGRAM_BOT_TOKEN", "test-token"),
        patch("app.telegram.bot.TELEGRAM_PROXY_URL", None),
    ):
        application = build_application()
    handlers = [handler for group in application.handlers.values() for handler in group]
    assert any(isinstance(handler, ConversationHandler) for handler in handlers)
    commands = {
        command
        for handler in handlers
        if hasattr(handler, "commands")
        for command in handler.commands
    }
    commands.update(
        command
        for handler in handlers
        if isinstance(handler, ConversationHandler)
        for entry in handler.entry_points
        if hasattr(entry, "commands")
        for command in entry.commands
    )
    assert {"start", "help", "status", "audit", "audits", "report"} <= commands
