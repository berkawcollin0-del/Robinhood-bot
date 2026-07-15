import feedparser
import random
import datetime
import os
import asyncio
from telegram import Bot

# Configuration
TOKEN = os.environ.get('8558552493:AAHDCklNVlS-ElKy9KgEs-1y3okRHkWG9Ms')
CHAT_ID = os.environ.get('8513717392')

FEEDS = {
    "🇺🇸 US Housing": "https://news.google.com/rss/search?q=US+housing+real+estate+market+news&hl=en-US&gl=US&ceid=US:en",
    "🐻 St. Louis Updates": "https://news.google.com/rss/search?q=St.+Louis+business+real+estate+development&hl=en-US&gl=US&ceid=US:en",
    "⚖️ Law & Policy": "https://news.google.com/rss/search?q=real+estate+law+policy+changes+NAR&hl=en-US&gl=US&ceid=US:en",
    "🤖 AI in Real Estate": "https://news.google.com/rss/search?q=AI+in+real+estate+tools+trends&hl=en-US&gl=US&ceid=US:en"
}

DAILY_TIPS = [
    "Call 5 past clients today just to ask how they are doing—no sales pitch.",
    "Draft one social media post highlighting a local St. Louis business you love.",
    "Spend 15 minutes researching a new AI tool to automate your listing descriptions.",
    "Review your local MLS for 'Coming Soon' listings.",
    "Update your CRM with notes from your last 3 client interactions.",
    "Write a handwritten note to someone in your professional network.",
    "Identify one local event in Wentzville/St. Louis and plan to attend for networking."
]

def get_daily_tip():
    return DAILY_TIPS[datetime.datetime.now().timetuple().tm_yday % len(DAILY_TIPS)]

def fetch_feed(url, limit=3):
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries[:limit]:
        # Using simple formatting to avoid length errors
        items.append(f"• {entry.title}\n  {entry.link}")
    return "\n\n".join(items) if items else "No updates found today."

async def main():
    bot = Bot(token=TOKEN)
    
    # 1. Send Tip
    intro = f"📅 **Agent Briefing - {datetime.date.today().strftime('%B %d, %Y')}**\n\n💡 **TIP:** {get_daily_tip()}"
    await bot.send_message(chat_id=CHAT_ID, text=intro, parse_mode='Markdown')
    
    # 2. Send Categories one by one to avoid message length limits
    for category, url in FEEDS.items():
        content = fetch_feed(url)
        message = f"**{category}**\n\n{content}"
        await bot.send_message(
            chat_id=CHAT_ID, 
            text=message, 
            parse_mode='Markdown', 
            disable_web_page_preview=True
        )

if __name__ == '__main__':
    asyncio.run(main())
