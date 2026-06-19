# JoinBridge Bot

Original multi-channel Telegram join-request automation bot built with Python.

## Features
- Handles join requests from multiple private channels/groups.
- Sends the latest admin-selected post to the requesting user instantly.
- Supports copy or forward delivery mode per chat.
- Deep-link button to open the bot from the private message.
- Admin commands for binding chats, setting latest post, stats, and broadcast.
- SQLite storage for users, joins, broadcasts, and per-chat configuration.

## Flow
1. Add the bot as admin in a private channel/group with join requests enabled.
2. Start the bot in private and make sure admin users are listed in `ADMIN_USER_IDS`.
3. In the target chat, send `/bind`.
4. Reply to the desired admin post with `/setlatest`.
5. When a user sends a join request, the bot DMs them the saved latest post.

## Commands
- `/start` - User/admin entry point.
- `/help` - Usage guide.
- `/bind` - Bind current group/channel in admin context.
- `/setmode copy|forward` - Choose delivery mode for current chat.
- `/setlatest` - Reply to a post in the source chat to mark it as latest deliverable content.
- `/stats` - Show overall stats.
- `/chatstats <chat_id>` - Show stats for one source chat.
- `/broadcast <text>` - Broadcast text to all known active users.

## Important Notes
- The join-request DM relies on Telegram's join request user chat identifier window, so delivery should happen immediately when the request arrives.
- Store large Telegram IDs as 64-bit integers.
- For channels, admin commands may be limited depending on how Telegram delivers posts and permissions. Groups/supergroups are easiest for command-driven setup. If commands in a source channel are inconvenient, update the chat row directly in SQLite or adapt the bot to use callback-based admin setup in private chat.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
mkdir -p data
python run.py
```

## Privacy
This project stores join and broadcast metadata locally in SQLite. Review and harden before production.
