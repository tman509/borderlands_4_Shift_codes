#!/usr/bin/env python3
"""
Simple Discord webhook test script.
"""

import os
import sys
import json
import requests
from datetime import datetime

def test_discord_webhook():
    """Test Discord webhook with a simple message."""
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
    
    if not webhook_url:
        print("❌ DISCORD_WEBHOOK_URL environment variable not set")
        print("Set it with: export DISCORD_WEBHOOK_URL='your_webhook_url'")
        return False
    
    # Create test message
    test_message = {
        "content": "🧪 **Discord Webhook Test**",
        "embeds": [
            {
                "title": "Shift Code Bot Test",
                "description": "This is a test message to verify Discord integration is working.",
                "color": 0x00ff00,  # Green color
                "fields": [
                    {
                        "name": "Status",
                        "value": "✅ Webhook Connected",
                        "inline": True
                    },
                    {
                        "name": "Test Time",
                        "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "inline": True
                    }
                ],
                "footer": {
                    "text": "Borderlands Shift Code Bot"
                }
            }
        ]
    }
    
    try:
        print("🚀 Sending test message to Discord...")
        
        response = requests.post(
            webhook_url,
            json=test_message,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 204:
            print("✅ Discord test message sent successfully!")
            print("Check your Discord channel for the test message.")
            return True
        else:
            print(f"❌ Discord webhook failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending Discord message: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("Discord Webhook Test")
    print("=" * 30)
    
    success = test_discord_webhook()
    
    if success:
        print("\n🎉 Discord integration is working!")
    else:
        print("\n💥 Discord integration needs attention")
        print("\nTroubleshooting:")
        print("1. Check your DISCORD_WEBHOOK_URL is correct")
        print("2. Verify the webhook hasn't been deleted in Discord")
        print("3. Make sure the bot has permission to post in the channel")
    
    sys.exit(0 if success else 1)