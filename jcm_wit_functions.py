import logging
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes,
    ConversationHandler,
    InlineQueryHandler
)
from datetime import datetime
import json
import asyncio
from openai import AsyncOpenAI
from typing import Optional, Dict, Any
import signal
import sys
from dotenv import load_dotenv
import os
from uuid import uuid4
from conversation_logger import ConversationLogger
from group_chat_handler import GroupChatHandler

# Load environment variables from .env file
load_dotenv()

# Get environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CONTEXT_FILE = "user_context.txt"

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise ValueError("TELEGRAM_TOKEN and OPENAI_API_KEY must be set in .env file")

# Import custom functions
from custom_functions import AVAILABLE_FUNCTIONS

# Set up logging
logging.basicConfig(
    filename=f'jcn_bot_{datetime.now().strftime("%Y%m%d")}.log',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class JCNBot:
    def __init__(self, telegram_token: str, openai_api_key: Optional[str] = None, context_file: str = "user_context.txt"):
        """Initialize the bot with tokens"""
        self.telegram_token = telegram_token
        self.application = Application.builder().token(telegram_token).build()
        
        # Initialize conversation logger
        self.conversation_logger = ConversationLogger()
        
        # Add group chat handler
        self.group_handler = GroupChatHandler(context_file)
        
        # Initialize OpenAI client if API key provided
        if openai_api_key:
            try:
                self.openai_client = AsyncOpenAI(api_key=openai_api_key)
                logger.info("OpenAI client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.openai_client = None
        else:
            logger.warning("No OpenAI API key provided")
            self.openai_client = None
        
        # Store active conversations
        self.active_conversations = {}
        
        # Context file paths
        self.context_file = context_file
        self.system_prompt_file = "system_prompt.txt"
        self.jason_context_file = "jason_context.txt"
        
        # Setup handlers
        self.setup_handlers()

    def setup_handlers(self):
        """Set up command and message handlers"""
        # Basic command handlers - allow in private and group chats
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # Add separate conversation handlers for private and group chats
        private_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("chat", self.start_chat, filters.ChatType.PRIVATE)],
            states={
                'CHATTING': [
                    MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, self.handle_chat_message),
                    CommandHandler("end", self.end_chat)
                ]
            },
            fallbacks=[CommandHandler("end", self.end_chat)]
        )
        self.application.add_handler(private_conv_handler)
        
        # Add handler for inline queries in groups
        self.application.add_handler(InlineQueryHandler(self.handle_inline_query))
        
        # Add general message handler for group chats - should handle both commands and messages
        self.application.add_handler(
            MessageHandler(
                filters.ChatType.GROUPS & filters.TEXT,
                self.handle_group_message
            )
        )
        
        # Error handler
        self.application.add_error_handler(self.error_handler)

    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages in group chats"""
        if not update.message or not update.message.text:
            return
                
        message = update.message.text
        group_id = update.effective_chat.id
        user_id = update.effective_user.id
        message_id = update.message.message_id
            
        # Log incoming message
        logger.info(f"Group message received - Group: {group_id}, User: {user_id}, Message: {message}")
            
        # Check if message is a command
        is_command = message.startswith('/')
            
        # Check if message is a reply to the bot
        is_reply_to_bot = (
            update.message.reply_to_message and 
            update.message.reply_to_message.from_user and
            update.message.reply_to_message.from_user.id == context.bot.id
        )
            
        # Check if bot is mentioned
        bot_username = context.bot.username.lower() if context.bot.username else ""
        is_mentioned = any(name.lower() in message.lower() for name in [
            f"@{bot_username}",
            "@jdawg_bot"
        ])
            
        # Only respond if:
        # 1. It's a command, or
        # 2. It's a reply to the bot, or
        # 3. The bot is explicitly mentioned
        should_respond = is_command or is_reply_to_bot or is_mentioned
            
        if should_respond:
            try:
                # Send typing indicator
                await context.bot.send_chat_action(
                    chat_id=group_id,
                    action="typing"
                )
                    
                # Clean the message (remove bot mentions)
                clean_message = message.lower()
                if context.bot.username:
                    clean_message = clean_message.replace(f"@{context.bot.username.lower()}", "")
                clean_message = clean_message.replace("@jdawg_bot", "").strip()
                    
                # Handle /chat command
                if '/chat' in message:
                    await update.message.reply_text(
                        "I'm ready to chat! Just mention me (@jdawg_bot) in your messages or reply to my messages.",
                        reply_to_message_id=message_id
                    )
                    return
                    
                # Generate response
                response = await self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": self.read_context_file()},
                        {"role": "system", "content": "You are in a group chat. Keep responses concise and natural."},
                        {"role": "user", "content": clean_message}
                    ],
                    functions=self.get_function_definitions(),
                    function_call="auto",
                    max_tokens=1024
                )
                    
                # Process the response
                await self.process_ai_response(update, context, response, None)
                    
            except Exception as e:
                logger.error(f"Error in group chat response: {str(e)}", exc_info=True)
                await update.message.reply_text(
                    "Sorry, I encountered an error while processing your message.",
                    reply_to_message_id=message_id
                )


    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command"""
        user = update.effective_user
        welcome_message = (
            f"Hi {user.first_name}! I'm JCN, Jason's Convoluted Notions.\n\n"
            "I can help you with various tasks and have conversations.\n"
            "Try /help to see what I can do!"
        )
        await update.message.reply_text(welcome_message)
        logger.info(f"New user started bot: {user.id} ({user.first_name})")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command"""
        help_text = (
            "Here are the commands you can use:\n\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/chat - Start an AI chat session\n"
            "In group chats, you can also use me inline by typing @bot_name followed by your message."
        )
        await update.message.reply_text(help_text)

    async def start_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start an AI chat session"""
        user_id = update.effective_user.id
        self.active_conversations[user_id] = []
        await update.message.reply_text(
            "Starting AI chat session. You can talk directly with me now!\n"
            "Use /end to finish the conversation."
        )
        return 'CHATTING'

    async def end_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """End an AI chat session"""
        user_id = update.effective_user.id
        if user_id in self.active_conversations:
            del self.active_conversations[user_id]
        await update.message.reply_text("Chat session ended. Thanks for talking with me!")
        return ConversationHandler.END

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Log errors caused by Updates"""
        logger.error(f"Update {update} caused error {context.error}")
        if update and isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, something went wrong! Please try again later."
            )

    def read_context_file(self) -> str:
        """Read and parse the context file"""
        try:
            # Read system prompt
            system_prompt = "You are a Telegram bot. "
            try:
                with open(self.system_prompt_file, 'r') as f:
                    system_prompt = f.read().strip()
            except FileNotFoundError:
                logger.warning(f"System prompt file not found: {self.system_prompt_file}")
            except Exception as e:
                logger.error(f"Error reading system prompt file: {e}")

            # Read Jason's context
            jason_context = ""
            try:
                with open(self.jason_context_file, 'r') as f:
                    jason_context = f.read().strip()
            except FileNotFoundError:
                logger.warning(f"Jason's context file not found: {self.jason_context_file}")
            except Exception as e:
                logger.error(f"Error reading Jason's context file: {e}")

            # Read general context
            general_context = ""
            try:
                with open(self.context_file, 'r') as f:
                    general_context = f.read().strip()
            except FileNotFoundError:
                logger.warning(f"Context file not found: {self.context_file}")
            except Exception as e:
                logger.error(f"Error reading context file: {e}")

            # Combine all contexts
            full_context = f"{system_prompt}\n\n"
            
            if jason_context:
                full_context += f"JASON'S CONTEXT:\n{jason_context}\n\n"
            
            if general_context:
                full_context += f"ADDITIONAL CONTEXT:\n{general_context}"

            logger.info("Successfully compiled context")
            return full_context.strip()
            
        except Exception as e:
            logger.error(f"Error compiling context: {e}")
            return "Error reading context."

    async def handle_chat_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages in an AI chat session"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        message = update.message.text
        
        # Log user message
        await self.conversation_logger.log_message(
            user_id=user_id,
            user_name=user_name,
            message_type="user",
            content=message
        )
        
        # Get conversation history
        conversation = self.active_conversations.get(user_id, [])
        
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            
            # Prepare messages with context and history
            messages = [
                {"role": "system", "content": self.read_context_file()}
            ] + conversation + [
                {"role": "user", "content": message}
            ]
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                functions=self.get_function_definitions(),
                function_call="auto",
                max_tokens=1024
            )
            
            # Handle response
            await self.process_ai_response(update, context, response, conversation)
            
            return 'CHATTING'
            
        except Exception as e:
            logger.error(f"Error in chat: {str(e)}", exc_info=True)
            await update.message.reply_text(f"Sorry, I encountered an error: {str(e)}")
            return 'CHATTING'

    async def handle_inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline queries in group chats"""
        query = update.inline_query.query
        
        if not query:
            return
            
        try:
            # Generate response using AI
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.read_context_file()},
                    {"role": "user", "content": query}
                ],
                functions=self.get_function_definitions(),
                function_call="auto",
                max_tokens=1024
            )
            
            # Create inline results
            results = [
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="AI Response",
                    description=response.choices[0].message.content[:100] + "...",
                    input_message_content=InputTextMessageContent(
                        response.choices[0].message.content
                    )
                )
            ]
            
            await update.inline_query.answer(results)
            
        except Exception as e:
            logger.error(f"Error in inline query: {str(e)}", exc_info=True)

    def get_function_definitions(self):
        """Get the list of available functions for the API"""
        return [
            {
                "name": name,
                "description": func["function"].__doc__,
                "parameters": func["parameters"]
            }
            for name, func in AVAILABLE_FUNCTIONS.items()
        ]


    async def process_ai_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                response, conversation):
        """Process and handle AI response including function calls"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        response_message = response.choices[0].message
        is_group_chat = update.effective_chat.type in ["group", "supergroup"]
        
        try:
            # Handle function calls
            if hasattr(response_message, 'function_call') and response_message.function_call:
                function_name = response_message.function_call.name
                function_args = json.loads(response_message.function_call.arguments)
                
                if function_name in AVAILABLE_FUNCTIONS:
                    function_to_call = AVAILABLE_FUNCTIONS[function_name]["function"]
                    function_response = await function_to_call(**function_args)
                    
                    # Log function call
                    await self.conversation_logger.log_function_call(
                        user_id=user_id,
                        user_name=user_name,
                        function_name=function_name,
                        arguments=function_args,
                        response=function_response.__dict__
                    )
                    
                    # Send function result
                    await update.message.reply_text(
                        f"Function call result:\n{function_response.message}\n\n"
                        f"{'Success' if function_response.success else 'Failed'}",
                        reply_to_message_id=update.message.message_id if is_group_chat else None
                    )
                    
                    # Only update conversation history for private chats
                    if not is_group_chat:
                        conversation.extend([
                            {
                                "role": "assistant",
                                "content": None,
                                "function_call": {
                                    "name": function_name,
                                    "arguments": json.dumps(function_args)
                                }
                            },
                            {
                                "role": "function",
                                "name": function_name,
                                "content": json.dumps(function_response.__dict__)
                            }
                        ])
            
            # Send and log the text response
            if response_message.content:
                await update.message.reply_text(
                    response_message.content,
                    reply_to_message_id=update.message.message_id if is_group_chat else None
                )
                
                # Log assistant's response
                await self.conversation_logger.log_message(
                    user_id=user_id,
                    user_name=user_name,
                    message_type="assistant",
                    content=response_message.content
                )
                
                # Only update conversation history for private chats
                if not is_group_chat:
                    conversation.append({
                        "role": "assistant",
                        "content": response_message.content
                    })
        
        except Exception as e:
            logger.error(f"Error in process_ai_response: {str(e)}", exc_info=True)
            await update.message.reply_text(
                "Sorry, I encountered an error while processing the response.",
                reply_to_message_id=update.message.message_id if is_group_chat else None
            )

    def run(self):
        """Run the bot until the user presses Ctrl-C"""
        logger.info("Starting bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Create and run the bot
    bot = JCNBot(TELEGRAM_TOKEN, OPENAI_API_KEY, CONTEXT_FILE)
    
    try:
        logger.info("Starting bot...")
        # Create an event loop
        loop = asyncio.get_event_loop()
        
        # Set up graceful shutdown
        def signal_handler():
            logger.info("Received shutdown signal, cleaning up...")
            # Save any pending messages or state if needed
            loop.stop()
            logger.info("Bot shutdown complete")
        
        # Register signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
        
        # Run the bot
        bot.run()
        
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
    finally:
        # Close the event loop
        loop.close()
        logger.info("Event loop closed")