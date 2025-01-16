import json
from datetime import datetime
import os

class ConversationLogger:
    def __init__(self, log_dir="conversation_logs"):
        """Initialize the conversation logger with a directory for storing logs"""
        self.log_dir = log_dir
        self._ensure_log_directory()

    def _ensure_log_directory(self):
        """Create the log directory if it doesn't exist"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def _get_conversation_file(self, user_id):
        """Get the log file path for a specific user"""
        return os.path.join(self.log_dir, f"conversation_{user_id}.jsonl")

    async def log_message(self, user_id, user_name, message_type, content):
        """Log a single message in the conversation"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "user_name": user_name,
            "type": message_type,  # 'user' or 'assistant'
            "content": content
        }
        
        try:
            with open(self._get_conversation_file(user_id), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to log conversation: {e}")

    async def log_function_call(self, user_id, user_name, function_name, arguments, response):
        """Log a function call in the conversation"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "user_name": user_name,
            "type": "function_call",
            "function_name": function_name,
            "arguments": arguments,
            "response": response
        }
        
        try:
            with open(self._get_conversation_file(user_id), 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to log function call: {e}")

    def get_conversation_history(self, user_id, limit=None):
        """Retrieve conversation history for a specific user"""
        try:
            messages = []
            file_path = self._get_conversation_file(user_id)
            
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        messages.append(json.loads(line.strip()))
                        
            if limit:
                messages = messages[-limit:]
                
            return messages
        except Exception as e:
            logger.error(f"Failed to retrieve conversation history: {e}")
            return []