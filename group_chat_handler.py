from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class GroupChatHandler:
    def __init__(self, bot_context_file: str, relevance_threshold: float = 0.7):
        self.context = self._load_context(bot_context_file)
        self.relevance_threshold = relevance_threshold
        self.active_conversations = {}  # Track active conversations by group
        self.recent_messages = {}  # Store recent messages for context
        self.last_response_time = {}  # Track when bot last responded in each group
    
    def _load_context(self, context_file: str) -> str:
        """Load and parse the context file"""
        try:
            with open(context_file, 'r') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading context file: {e}")
            return ""
        
    async def should_respond(self, message: str, group_id: int, is_reply_to_bot: bool = False) -> bool:
        """Determine if the bot should respond to a message"""
        # Always respond if it's a direct reply to the bot
        if is_reply_to_bot:
            return True
            
        # Check if message contains a question
        if self._is_question(message):
            relevance = await self._calculate_relevance(message)
            return relevance >= self.relevance_threshold
            
        # Check if message is part of an active conversation
        if self._is_part_of_active_conversation(group_id, message):
            return True
            
        # Check if message is highly relevant to bot's purpose
        relevance = await self._calculate_relevance(message)
        return relevance >= self.relevance_threshold * 1.2  # Higher threshold for non-questions
        
    def _is_question(self, message: str) -> bool:
        """Detect if a message contains a question"""
        question_indicators = [
            "?",
            "what", "how", "why", "when", "where", "who", "which",
            "can you", "could you", "would you",
            "is there", "are there",
            "tell me"
        ]
        
        message_lower = message.lower()
        return any(indicator in message_lower for indicator in question_indicators)
        
    async def _calculate_relevance(self, message: str) -> float:
        """Calculate relevance score of message to bot's context"""
        # This would use embeddings comparison or keyword matching
        # For now, using a simple keyword-based approach
        relevant_keywords = self._extract_keywords_from_context()
        message_keywords = set(message.lower().split())
        
        keyword_matches = len(set(relevant_keywords) & message_keywords)
        return min(1.0, keyword_matches / max(1, len(relevant_keywords)))
    
    def _extract_keywords_from_context(self) -> set:
        """Extract relevant keywords from the bot's context"""
        # This is a simple implementation - you might want to make this more sophisticated
        # by using NLP techniques or maintaining a curated list of keywords
        words = self.context.lower().split()
        # Remove common words and keep only meaningful keywords
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "is", "are", "was", "were"}
        return {word for word in words if word not in stopwords and len(word) > 2}
        
    def update_conversation_context(self, group_id: int, message: str, 
                                  message_id: int, user_id: int):
        """Update the conversation context for a group"""
        if group_id not in self.recent_messages:
            self.recent_messages[group_id] = []
            
        self.recent_messages[group_id].append({
            'message_id': message_id,
            'user_id': user_id,
            'content': message,
            'timestamp': datetime.now()
        })
        
        # Keep only last 10 messages or messages from last 5 minutes
        self._prune_old_messages(group_id)
        
    def _is_part_of_active_conversation(self, group_id: int, message: str) -> bool:
        """Check if message is part of an ongoing conversation"""
        if group_id not in self.recent_messages:
            return False
            
        # Check if there's been recent bot activity
        last_response = self.last_response_time.get(group_id, 0)
        if isinstance(last_response, (int, float)) and last_response == 0:
            return False
            
        time_diff = (datetime.now() - last_response).seconds if isinstance(last_response, datetime) else float('inf')
        if time_diff > 300:  # 5 minute timeout
            return False
            
        # Check contextual relevance to recent messages
        recent_context = ' '.join([m['content'] for m in self.recent_messages[group_id][-3:]])
        relevance = self._calculate_context_similarity(recent_context, message)
        
        return relevance > 0.6  # Threshold for conversation continuity
    
    def _calculate_context_similarity(self, context: str, message: str) -> float:
        """Calculate similarity between context and message"""
        # Simple word overlap similarity for now
        context_words = set(context.lower().split())
        message_words = set(message.lower().split())
        
        overlap = len(context_words & message_words)
        return overlap / max(1, len(context_words | message_words))
        
    def _prune_old_messages(self, group_id: int):
        """Remove old messages from context"""
        current_time = datetime.now()
        self.recent_messages[group_id] = [
            msg for msg in self.recent_messages[group_id]
            if (current_time - msg['timestamp']).seconds < 300  # 5 minute window
        ][-10:]  # Keep only last 10 messages
        
    def get_conversation_context(self, group_id: int) -> list:
        """Get recent conversation context for a group"""
        if group_id not in self.recent_messages:
            return []
            
        return self.recent_messages[group_id]
        
    def update_last_response_time(self, group_id: int):
        """Update the timestamp of the bot's last response in a group"""
        self.last_response_time[group_id] = datetime.now()