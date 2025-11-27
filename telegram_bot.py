"""
Telegram notification module for SolSpotBot
"""
import logging
import requests
from typing import Optional
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def send_telegram_message(text: str) -> bool:
    """
    Send a message to Telegram using the Bot API
    
    Args:
        text: Message text to send
        
    Returns:
        True if message was sent successfully, False otherwise
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured, skipping notification")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        response = requests.post(
            url,
            params={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text
            },
            timeout=5
        )
        response.raise_for_status()
        logger.debug(f"Telegram message sent successfully")
        return True
    except requests.exceptions.Timeout:
        logger.warning("Telegram API timeout - message not sent")
        return False
    except requests.exceptions.RequestException as e:
        logger.warning(f"Telegram API error - message not sent: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error sending Telegram message: {e}")
        return False

