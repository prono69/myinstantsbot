#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Telegram bot that searches sounds on www.myinstants.com
    Author: Luiz Francisco Rodrigues da Silva <luizfrdasilva@gmail.com>
"""

import logging
import os
import sys
from uuid import uuid4

from telegram import InlineQueryResultVoice, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
)

from myinstants import HTTPErrorException, search_instants

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start."""
    await update.message.reply_text(
        "Hi!\nYou can use this bot in any chat, just type "
        "@myinstantsbot query message\nEnjoy!"
    )


async def help_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help."""
    await update.message.reply_text(
        "This bot searches sounds on myinstants.com\n"
        "You can use it in any chat, just type "
        "@myinstantsbot query message"
    )


async def info_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /info."""
    await update.message.reply_text(
        "Source code: https://www.github.com/heylouiz/myinstantsbot\n"
        "Developer: @heylouiz"
    )


# ---------------------------------------------------------------------------
# Inline query handler
# ---------------------------------------------------------------------------

async def inline_query(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries."""
    query = update.inline_query.query
    if not query:
        return

    try:
        results = await search_instants(query)
    except HTTPErrorException as exc:
        logger.warning("search_instants failed for query %r: %s", query, exc)
        await update.inline_query.answer([], cache_time=0)
        return

    inline_results = [
        InlineQueryResultVoice(
            id=str(uuid4()),
            title=instant["text"],
            voice_url=instant["url"],
        )
        for instant in results[:10]
    ]

    await update.inline_query.answer(inline_results, cache_time=300)


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors with full traceback."""
    logger.error("Update %r caused error: %s", update, context.error, exc_info=context.error)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("Missing environment variable TELEGRAM_TOKEN. See README.md.")
        sys.exit(1)

    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler("start", start, block=False))
    application.add_handler(CommandHandler("help", help_command, block=False))
    application.add_handler(CommandHandler("info", info_command, block=False))
    application.add_handler(InlineQueryHandler(inline_query, block=False))
    application.add_error_handler(error_handler, block=False)

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
