import feedparser
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Define the RSS feeds using Google News for reliable aggregation
US_FEED_URL = "https://news.google.com/rss/search?q=US+housing+real+estate+market+news&hl=en-US&gl=US&ceid=US:en"
MO_FEED_URL = "https://news.google.com/rss/search?q=Missouri+housing+real+estate+market+news&hl=en-US&gl=US&ceid=US:en"

def clean_html(raw_html):
    """Removes HTML tags from the summary text to keep the output clean."""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    # Remove "Read full article" type text often appended by Google News
    cleantext = cleantext.split('nbsp;')[0] 
    return cleantext.strip()

def fetch_news(feed_url, limit=5):
    """Fetches and formats news from the given RSS feed into bullet points."""
    feed = feedparser.parse(feed_url)
    bullet_points = []
    
    for entry in feed.entries[:limit]:
        title = entry.title
        link = entry.link
        
        # Clean the summary to get a brief description for the bullet point
        summary = ""
        if 'summary' in entry:
            summary = clean_html(entry.summary)
            # Truncate summary if it's too long
            if len(summary) > 150:
                summary = summary[:147] + "..."
        
        # Format as a Markdown bullet point
        bullet_points.append(f"• *[{title}]({link})*\n  {summary}")
        
    return "\n\n".join(bullet_points)

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /news command by fetching and sending the separated news."""
    await update.message.reply_text("Fetching the latest housing news for you. Please wait a moment...")
    
    # Fetch the top 5 news articles for each region
    us_news = fetch_news(US_FEED_URL, limit=5)
    mo_news = fetch_news(MO_FEED_URL, limit=5)
    
    # Construct the final message with clear information hierarchy 
    message = (
        "🇺🇸 **US HOUSING NEWS**\n"
        "---\n"
        f"{us_news}\n\n"
        "🐻 **MISSOURI HOUSING NEWS**\n"
        "---\n"
        f"{mo_news}"
    )
    
    # Send the message, parsing Markdown formatting and disabling giant link previews
    await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)

if __name__ == '__main__':
    # Insert your specific BotFather token here
    TOKEN = 'AAHDCklNVlS-ElKy9KgEs-1y3okRHkWG9Ms'
    
    # Build the application
    app = Application.builder().token(TOKEN).build()
    
    # Add the /news command handler to listen for user input
    app.add_handler(CommandHandler('news', news_command))
    
    print("Bot is running! Send /news to your bot in Telegram to get the latest updates.")
    
    # Run the bot until you press Ctrl-C
    app.run_polling()
