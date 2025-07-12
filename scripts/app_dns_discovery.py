import dns.resolver
import time

# Set your DNS server (Infoblox DNS in your lab)
DNS_SERVER = "10.10.10.3"

# AI/GenAI SaaS domains to simulate "app usage"
domains = [
    "chat.openai.com",           # ChatGPT
    "bard.google.com",           # Google Gemini (ex-Bard)
    "claude.ai",                 # Anthropic Claude
    "copilot.microsoft.com",     # Microsoft Copilot
    "poe.com",                   # Quora Poe
    "perplexity.ai",             # Perplexity
    "notion.so",                 # Notion AI
    "grammarly.com",             # Grammarly AI
    "monday.com",                # Project management AI
    "clickup.com",               # ClickUp
    "slack.com",                 # Slack AI
    "zoom.us",                   # Zoom AI
    "otter.ai",                  # Otter voice transcription
    "supernormal.com",           # Meeting assistant
    "gptforwork.com",            # GPT for Sheets/Docs
]

resolver = dns.resolver.Resolver()
resolver.nameservers = [DNS_SERVER]

for domain in domains:
    try:
        print(f"🔍 Resolving {domain} ...")
        answers = resolver.resolve(domain, 'A')
        for rdata in answers:
            print(f"✅ {domain} resolved to {rdata}")
    except Exception as e:
        print(f"❌ Failed to resolve {domain}: {e}")
    time.sleep(1)  # Slight delay to mimic human behavior
