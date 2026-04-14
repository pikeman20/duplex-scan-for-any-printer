"""
Telegram Bot for Scanner Confirmation System

Provides command interface for confirming/rejecting scan sessions via Telegram.
"""
from __future__ import annotations

import os
import logging
import threading
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from agent.config import Config, TelegramConfig

logger = logging.getLogger(__name__)


@dataclass
class TelegramBot:
    """Telegram bot for handling scan session confirmations."""

    config: TelegramConfig
    _application: Optional[Application] = field(default=None, repr=False)
    _running: bool = field(default=False, repr=False)
    _authorized_chats: Dict[int, int] = field(default_factory=dict)  # user_id -> chat_id
    _session_callback: Optional[Any] = field(default=None, repr=False)
    _latest_session_info: Optional[Dict] = field(default=None, repr=False)

    @classmethod
    def from_config(cls, config: Config) -> Optional["TelegramBot"]:
        """Create TelegramBot from Config, returns None if not enabled."""
        if not config.telegram.enabled:
            logger.info("Telegram bot is disabled in configuration")
            return None

        if not config.telegram.bot_token:
            logger.warning("Telegram bot enabled but no bot token configured")
            return None

        return cls(config=config.telegram)

    def set_session_callback(self, callback: Any) -> None:
        """Set callback for session state changes."""
        self._session_callback = callback

    def update_session_info(self, session_info: Dict[str, Any]) -> None:
        """Update the latest session info for display in bot."""
        self._latest_session_info = session_info

    def is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized to use bot commands."""
        if not self.config.authorized_users:
            # No authorized users configured - allow anyone
            return True
        return str(user_id) in self.config.authorized_users

    def register_chat(self, user_id: int, chat_id: int) -> None:
        """Register a user's chat ID for notifications."""
        self._authorized_chats[user_id] = chat_id

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        self.register_chat(user_id, chat_id)

        if not self.is_authorized(user_id):
            await update.message.reply_text(
                "❌ You are not authorized to use this bot.\n"
                "Please contact the administrator to get access."
            )
            return

        welcome_text = (
            "✅ <b>Welcome to Scanner Bot!</b>\n\n"
            "This bot allows you to confirm or reject scanning sessions.\n\n"
            "📋 <b>Available Commands:</b>\n"
            "/start - Register and show this message\n"
            "/help - Show help and commands\n"
            "/status - Show current session status\n"
            "/confirm - Confirm current session\n"
            "/reject - Reject current session\n\n"
            "⏱️ Sessions will auto-timeout after "
            f"{self.config.confirm_timeout_seconds // 60} minutes of inactivity."
        )

        await update.message.reply_text(welcome_text, parse_mode="HTML")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return

        help_text = (
            "📖 <b>Help</b>\n\n"
            "<b>/start</b> - Register with the bot\n"
            "<b>/help</b> - Show this help message\n"
            "<b>/status</b> - Show current session status and pending actions\n"
            "<b>/confirm</b> - Confirm the current scanning session and process it\n"
            "<b>/reject</b> - Reject and discard the current session\n\n"
            "<b>Note:</b> Only one session can be active at a time.\n"
            f"Auto-timeout: {self.config.confirm_timeout_seconds // 60} minutes"
        )

        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data="cmd_status")],
            [InlineKeyboardButton("✅ Confirm", callback_data="cmd_confirm")],
            [InlineKeyboardButton("❌ Reject", callback_data="cmd_reject")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=reply_markup)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return

        if not self._latest_session_info:
            await update.message.reply_text(
                "📭 No active session.\n"
                "Scans will automatically appear here when images are uploaded."
            )
            return

        session = self._latest_session_info
        status_text = (
            f"📊 <b>Session Status</b>\n\n"
            f"<b>Session ID:</b> {session.get('id', 'N/A')}\n"
            f"<b>Mode:</b> {session.get('mode', 'N/A')}\n"
            f"<b>State:</b> {session.get('state', 'N/A')}\n"
            f"<b>Images:</b> {session.get('image_count', 0)}\n"
            f"<b>Timeout:</b> {self.config.confirm_timeout_seconds // 60} minutes"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Confirm", callback_data="cmd_confirm")],
            [InlineKeyboardButton("❌ Reject", callback_data="cmd_reject")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(status_text, parse_mode="HTML", reply_markup=reply_markup)

    async def confirm_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /confirm command."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return

        if not self._latest_session_info:
            await update.message.reply_text("❌ No active session to confirm.")
            return

        if self._session_callback:
            try:
                # Call the confirm callback with print_requested=False (default)
                self._session_callback(confirm=True, print_requested=False)
                await update.message.reply_text(
                    "✅ Session confirmed! Processing will begin shortly."
                )
            except Exception as e:
                logger.error(f"Error confirming session: {e}")
                await update.message.reply_text(
                    f"❌ Error confirming session: {str(e)}"
                )
        else:
            await update.message.reply_text("⚠️ Bot not connected to session manager.")

    async def reject_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reject command."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return

        if not self._latest_session_info:
            await update.message.reply_text("❌ No active session to reject.")
            return

        if self._session_callback:
            try:
                self._session_callback(confirm=False, print_requested=False)
                await update.message.reply_text(
                    "❌ Session rejected. Images will be cleaned up."
                )
            except Exception as e:
                logger.error(f"Error rejecting session: {e}")
                await update.message.reply_text(
                    f"❌ Error rejecting session: {str(e)}"
                )
        else:
            await update.message.reply_text("⚠️ Bot not connected to session manager.")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline button callbacks."""
        query = update.callback_query
        await query.answer()

        if not self.is_authorized(query.from_user.id):
            await query.edit_message_text("❌ You are not authorized.")
            return

        data = query.data

        if data == "cmd_status":
            await self.status_command(update, context)
        elif data == "cmd_confirm":
            await self.confirm_command(update, context)
        elif data == "cmd_reject":
            await self.reject_command(update, context)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors."""
        logger.error(f"Error handling update: {context.error}")
        if update and update.message:
            await update.message.reply_text(
                "⚠️ An error occurred. Please try again later."
            )

    def start_polling(self) -> None:
        """Start the bot polling in a background thread."""
        if self._running:
            logger.warning("Bot is already running")
            return

        if not self.config.bot_token:
            logger.error("Cannot start bot: no bot token configured")
            return

        try:
            # Build application
            self._application = (
                Application.builder()
                .token(self.config.bot_token)
                .build()
            )

            # Add handlers
            self._application.add_handler(CommandHandler("start", self.start_command))
            self._application.add_handler(CommandHandler("help", self.help_command))
            self._application.add_handler(CommandHandler("status", self.status_command))
            self._application.add_handler(CommandHandler("confirm", self.confirm_command))
            self._application.add_handler(CommandHandler("reject", self.reject_command))
            self._application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.help_command)
            )
            self._application.add_handler(
                CallbackQueryHandler(self.button_callback)
            )

            # Add error handler
            self._application.add_error_handler(self.error_handler)

            # Start polling in background with restart logic
            def run_polling():
                import asyncio
                import time
                max_retries = 5
                retry_delay = 10  # seconds between retries

                for attempt in range(max_retries):
                    try:
                        logger.info(f"Bot polling started (attempt {attempt + 1}/{max_retries})")
                        asyncio.run(self._application.run_polling(drop_pending_updates=True))
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.warning(f"Bot polling crashed, restarting in {retry_delay}s: {e}")
                            time.sleep(retry_delay)
                        else:
                            logger.error(f"Bot polling failed after {max_retries} attempts: {e}")
                            self._running = False

            self._running = True
            threading.Thread(target=run_polling, daemon=True).start()
            logger.info("Telegram bot started successfully")

        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            self._running = False

    def stop(self) -> None:
        """Stop the bot."""
        if self._application:
            try:
                import asyncio
                asyncio.run(self._application.stop())
            except Exception as e:
                logger.error(f"Error stopping bot: {e}")
        self._running = False
        logger.info("Telegram bot stopped")

    def send_notification(self, message: str, parse_mode: str = "HTML") -> None:
        """Send notification to all authorized users."""
        if not self._running or not self._application:
            logger.warning("Cannot send notification: bot not running")
            return

        # Schedule async send in the application's event loop
        try:
            import asyncio

            async def _send_to_all():
                for user_id, chat_id in self._authorized_chats.items():
                    try:
                        await self._application.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode=parse_mode
                        )
                    except Exception as e:
                        logger.error(f"Failed to send notification to user {user_id}: {e}")

            # Try to get the running loop from the application
            try:
                loop = self._application.loop
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(_send_to_all(), loop)
                else:
                    logger.warning("Bot event loop not running, cannot send notification")
            except AttributeError:
                # Fallback: create new event loop for this notification
                asyncio.run(_send_to_all())
        except Exception as e:
            logger.error(f"Error scheduling notification: {e}")


# Import CallbackQueryHandler at module level for the handler
from telegram.ext import CallbackQueryHandler