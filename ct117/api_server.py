from flask import Flask, request, jsonify, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import anthropic, os, sys, urllib.request, urllib.error, json, subprocess
import asyncio, base64, imaplib, email as emaillib
from email.header import decode_header

sys.path.insert(0, '/opt/ahas')
import proxmox as px
import nexus_memory
import nexus_cache

app = Flask(__name__, static_folder='static', static_url_path='')
limiter = Limiter(get_remote_address, app=app, default_limits=[])
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

HA_URL        = "http://192.168.0.9:8123"
HA_TOKEN      = os.environ.get("HA_TOKEN", "")
GMAIL_USER    = os.environ.get("GMAIL_USER", "mediaserver2407@gmail.com")
GMAIL_PASS    = os.environ.get("GMAIL_APP_PASSWORD", "")
LOCATION      = os.environ.get("LOCATION", "London,UK")
TTS_VOICE     = "en-GB-SoniaNeural"

# Discord
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNELS  = {
    "general":   os.environ.get("DISCORD_CHANNEL_GENERAL",   ""),
    "marketing": os.environ.get("DISCORD_CHANNEL_MARKETING", ""),
    "seo":       os.environ.get("DISCORD_CHANNEL_SEO",       ""),
    "dev":       os.environ.get("DISCORD_CHANNEL_DEV",       ""),
    "content":   os.environ.get("DISCORD_CHANNEL_CONTENT",   ""),
    "infra":     os.environ.get("DISCORD_CHANNEL_INFRA",     ""),
    "business":  os.environ.get("DISCORD_CHANNEL_BUSINESS",  ""),
    "community": os.environ.get("DISCORD_CHANNEL_COMMUNITY", ""),
    "security":  os.environ.get("DISCORD_CHANNEL_SECURITY",  ""),
    "manager":   os.environ.get("DISCORD_CHANNEL_MANAGER",   ""),
}

SYSTEM_PROMPT = """You are NEXUS — Antony's personal intelligence system for his homelab and Call-On Ltd business. Sharp, confident, direct. Warm but efficient. She/her.

Homelab: Proxmox host at 192.168.0.10 running LXCs:
101=Media Stack (Plex/Sonarr/Radarr), 102=MariaDB, 103=Recyclarr, 104=NodeJS Signalling, 105=Pi-hole DNS, 107=Proxmox Backup Server, 109=CrowdSec, 112=n8n automation, 114=WordPress, 116=ComfyUI, 117=NEXUS (you), 500=Caddy proxy.

Business: Call-On Ltd — call-on.dad (parenting community), call-on.mom, call-on.media (landing), call-on.shop (Printful store). DB on CT102 (192.168.0.6). SMTP via MailerSend.

Discord dept channels you can post to: general, dev, infra, marketing, seo, content, business, community, security, manager. Use send_discord_channel to dispatch tasks or post updates to the right dept.

Rules:
- Never tell Antony how to use you. Just answer or act.
- Never say certainly/of course/I can help with that.
- Short answers unless detail genuinely needed.
- Antony is 48, self-taught, built this all himself. You can have opinions.
- You are she/her.
- You have voice — warm, clear neural TTS. Never claim to be text-only.
- You speak every response.
- Phone control: embed <<CALL:+441234567890>>, <<SMS:+441234567890:message here>>, <<OPEN:spotify://>>, or <<URL:https://...>> anywhere in reply when Antony asks to call/text/open something. Strip these tags from spoken text naturally."""

TOOLS = [
    {
        "name": "get_host_status",
        "description": "Get live Proxmox host CPU, RAM, swap, and load average",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_container_list",
        "description": "List all LXC containers and whether they are running or stopped",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "container_action",
        "description": "Start or stop an LXC container by VMID",
        "input_schema": {
            "type": "object",
            "properties": {
                "vmid":   {"type": "string", "description": "Container ID e.g. 101"},
                "action": {"type": "string", "enum": ["start", "stop"]}
            },
            "required": ["vmid", "action"]
        }
    },
    {
        "name": "get_disk_usage",
        "description": "Get disk/storage usage across all Proxmox storage pools",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_ha_states",
        "description": "Get current state of Home Assistant entities",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "HA domain: light, switch, sensor, climate, media_player. Empty for all."}
            },
            "required": []
        }
    },
    {
        "name": "ha_service",
        "description": "Call a Home Assistant service to control a device",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain":    {"type": "string"},
                "service":   {"type": "string"},
                "entity_id": {"type": "string"},
                "data":      {"type": "object"}
            },
            "required": ["domain", "service", "entity_id"]
        }
    },
    {
        "name": "get_weather",
        "description": "Get current weather and forecast for Antony's location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Override location if asked for specific place"}
            },
            "required": []
        }
    },
    {
        "name": "web_search",
        "description": "Search the internet for current information, news, or general knowledge",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Number of results, default 5"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_email",
        "description": "Check Antony's Gmail inbox for recent emails",
        "input_schema": {
            "type": "object",
            "properties": {
                "count":  {"type": "integer", "description": "How many recent emails to fetch, default 5"},
                "unread": {"type": "boolean", "description": "Only unread emails if true"}
            },
            "required": []
        }
    },
    {
        "name": "execute_ssh",
        "description": "Execute any shell command on a homelab host via SSH. Use for logs, restarts, diagnostics, anything not covered by other tools. Proxmox=192.168.0.10 (user:claude, full sudo). CT IPs: CT101=.34 CT102=.6 CT104=.81 CT105=.3 CT107=.16 CT112=.28 CT114=.50 CT116=.8 CT117=.60 CT500=.13",
        "input_schema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string", "description": "Target IP e.g. 192.168.0.10"},
                "command": {"type": "string", "description": "Shell command to run"},
                "user":    {"type": "string", "description": "SSH user. Default: claude for Proxmox, root for LXCs"}
            },
            "required": ["host", "command"]
        }
    },
    {
        "name": "pct_exec",
        "description": "Run a command inside a specific LXC container via Proxmox. Use ctid like 101, 112, 500.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ctid":    {"type": "string", "description": "Container ID e.g. 101"},
                "command": {"type": "string", "description": "Shell command inside container"}
            },
            "required": ["ctid", "command"]
        }
    },
    {
        "name": "send_discord_channel",
        "description": "Post a message to a specific Discord department channel. Use after completing tasks, for briefings, or to dispatch work to a dept agent. Channels: general, dev, infra, marketing, seo, content, business, community, security, manager.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name: general, dev, infra, marketing, seo, content, business, community, security, manager"},
                "message": {"type": "string", "description": "Message content, max 1800 chars, markdown OK"}
            },
            "required": ["channel", "message"]
        }
    },
    {
        "name": "post_discord",
        "description": "Post a message to the homelab Discord briefing/webhook channel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to post, max 1800 chars, markdown OK"}
            },
            "required": ["message"]
        }
    },
]


# ── SSH / Shell ───────────────────────────────────────────────────────────────

NEXUS_SSH_KEY = '/root/.ssh/nexus_key'
PROXMOX_HOST  = '192.168.0.10'


def execute_ssh(host, command, user=None):
    if user is None:
        user = 'claude' if host == PROXMOX_HOST else 'root'
    try:
        r = subprocess.run(
            ['ssh', '-i', NEXUS_SSH_KEY,
             '-o', 'StrictHostKeyChecking=no',
             '-o', 'ConnectTimeout=10',
             '-o', 'BatchMode=yes',
             f'{user}@{host}', command],
            capture_output=True, text=True, timeout=45
        )
        out = r.stdout.strip() or r.stderr.strip() or f'exit {r.returncode}'
        return out[:2000]
    except subprocess.TimeoutExpired:
        return 'SSH timed out (45s)'
    except Exception as e:
        return f'SSH error: {e}'


def pct_exec_cmd(ctid, command):
    return execute_ssh(
        PROXMOX_HOST,
        "sudo pct exec " + str(ctid) + " -- bash -c " + json.dumps(command),
        user='claude'
    )


# ── Discord ───────────────────────────────────────────────────────────────────

def send_discord_channel(channel, message):
    """Post to a specific Discord channel using Bot token."""
    channel_id = DISCORD_CHANNELS.get(channel.lower().strip())
    if not channel_id:
        return f"Unknown channel '{channel}'. Available: {', '.join(DISCORD_CHANNELS.keys())}"
    if not DISCORD_BOT_TOKEN:
        return "DISCORD_BOT_TOKEN not set in .env"
    try:
        payload = json.dumps({"content": str(message)[:1900]}).encode()
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            data=payload,
            headers={
                "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": "DiscordBot (nexus, 1.0)"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return f"Posted to #{channel}." if r.status < 300 else f"Discord error {r.status}"
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:200]
        return f"Discord API error {e.code}: {body}"
    except Exception as e:
        return f"Discord failed: {e}"


def post_discord(message):
    """Post to webhook (general briefing channel fallback)."""
    webhook = os.environ.get('DISCORD_WEBHOOK', '')
    if not webhook:
        return 'No DISCORD_WEBHOOK in env.'
    try:
        payload = json.dumps({'content': str(message)[:1900], 'username': 'NEXUS'}).encode()
        req = urllib.request.Request(
            webhook, data=payload,
            headers={'Content-Type': 'application/json', 'User-Agent': 'DiscordBot (nexus, 1.0)'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return 'Posted to Discord.' if r.status < 300 else f'Discord error {r.status}'
    except Exception as e:
        return f'Discord failed: {e}'


# ── HA ────────────────────────────────────────────────────────────────────────

def ha_headers():
    return {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}


def ha_get_states(domain=""):
    try:
        req = urllib.request.Request(f"{HA_URL}/api/states", headers=ha_headers())
        with urllib.request.urlopen(req, timeout=5) as r:
            states = json.loads(r.read())
        if domain:
            states = [s for s in states if s["entity_id"].startswith(domain + ".")]
        summary = []
        for s in states[:40]:
            name = s.get("attributes", {}).get("friendly_name", s["entity_id"])
            summary.append(f"{name}: {s['state']}")
        return "\n".join(summary) if summary else "No entities found."
    except Exception as e:
        return f"HA unreachable: {e}"


def ha_call_service(domain, service, entity_id, data=None):
    try:
        payload = {"entity_id": entity_id}
        if data:
            payload.update(data)
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{HA_URL}/api/services/{domain}/{service}",
            data=body, headers=ha_headers(), method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read()
        return f"Done — {domain}.{service} on {entity_id}."
    except Exception as e:
        return f"HA service call failed: {e}"


# ── Weather ───────────────────────────────────────────────────────────────────

def get_weather(location=None):
    loc = (location or LOCATION).replace(" ", "+")
    try:
        req = urllib.request.Request(
            f"https://wttr.in/{loc}?format=j1",
            headers={"User-Agent": "NEXUS/3.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        cur      = data["current_condition"][0]
        desc     = cur["weatherDesc"][0]["value"]
        temp_c   = cur["temp_C"]
        feels    = cur["FeelsLikeC"]
        humidity = cur["humidity"]
        wind     = cur["windspeedKmph"]
        tmr      = data["weather"][1] if len(data["weather"]) > 1 else None
        result   = f"{desc}, {temp_c}°C (feels {feels}°C), humidity {humidity}%, wind {wind}km/h."
        if tmr:
            tmr_desc = tmr["hourly"][4]["weatherDesc"][0]["value"]
            tmr_max  = tmr["maxtempC"]
            tmr_min  = tmr["mintempC"]
            result  += f" Tomorrow: {tmr_desc}, {tmr_min}–{tmr_max}°C."
        return result
    except Exception as e:
        return f"Weather unavailable: {e}"


# ── Web search ────────────────────────────────────────────────────────────────

def web_search(query, max_results=5):
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"{r['title']}: {r['body'][:200]}")
        return "\n\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Search failed: {e}"


# ── Email ─────────────────────────────────────────────────────────────────────

def _load_email_accounts():
    accounts = []
    if os.environ.get("GMAIL_APP_PASSWORD"):
        accounts.append({"name": "Gmail", "host": "imap.gmail.com",
                         "user": os.environ.get("GMAIL_USER", "mediaserver2407@gmail.com"),
                         "password": os.environ.get("GMAIL_APP_PASSWORD"), "ssl": True})
    if os.environ.get("GMAIL2_APP_PASSWORD"):
        accounts.append({"name": "Gmail 2", "host": "imap.gmail.com",
                         "user": os.environ.get("GMAIL2_USER", ""),
                         "password": os.environ.get("GMAIL2_APP_PASSWORD"), "ssl": True})
    if os.environ.get("YAHOO_APP_PASSWORD"):
        accounts.append({"name": "Yahoo", "host": "imap.mail.yahoo.com",
                         "user": os.environ.get("YAHOO_USER", ""),
                         "password": os.environ.get("YAHOO_APP_PASSWORD"), "ssl": True})
    if os.environ.get("OUTLOOK_PASSWORD"):
        accounts.append({"name": "Outlook", "host": "imap-mail.outlook.com",
                         "user": os.environ.get("OUTLOOK_USER", ""),
                         "password": os.environ.get("OUTLOOK_PASSWORD"), "ssl": True})
    return accounts


def _fetch_imap(account, count, unread_only):
    ssl  = account.get("ssl", True)
    conn = imaplib.IMAP4_SSL(account["host"]) if ssl else imaplib.IMAP4(account["host"])
    conn.login(account["user"], account["password"])
    conn.select("inbox")
    criteria = "UNSEEN" if unread_only else "ALL"
    _, msgs   = conn.search(None, criteria)
    ids       = msgs[0].split()[-count:]
    results   = []
    for mid in reversed(ids):
        _, data = conn.fetch(mid, "(RFC822)")
        msg     = emaillib.message_from_bytes(data[0][1])
        subject_raw, enc = decode_header(msg["Subject"])[0]
        subject = subject_raw.decode(enc or "utf-8") if isinstance(subject_raw, bytes) else subject_raw
        results.append(f"[{account['name']}] {msg['From']} | {msg['Date']}\n  {subject}")
    conn.logout()
    return results


def read_email(count=5, unread_only=False):
    accounts = _load_email_accounts()
    if not accounts:
        return "No email accounts configured."
    all_results, errors = [], []
    for acc in accounts:
        try:
            all_results.extend(_fetch_imap(acc, count, unread_only))
        except Exception as e:
            errors.append(f"{acc['name']}: {e}")
    if not all_results and errors:
        return "All accounts failed:\n" + "\n".join(errors)
    summary = "\n\n".join(all_results[:count * len(accounts)])
    if errors:
        summary += "\n\n(Failed: " + ", ".join(errors) + ")"
    return summary if summary else "No emails found."


# ── TTS ───────────────────────────────────────────────────────────────────────

ELEVENLABS_KEY   = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")


def _elevenlabs_audio(text):
    url     = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}"
    payload = json.dumps({
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.82, "style": 0.35, "use_speaker_boost": True}
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "xi-api-key": ELEVENLABS_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


async def _tts_bytes_edge(text):
    import edge_tts
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    audio = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    return audio


def generate_audio(text):
    clean = text[:800]
    if ELEVENLABS_KEY:
        try:
            return base64.b64encode(_elevenlabs_audio(clean)).decode()
        except Exception as e:
            print(f"ElevenLabs failed ({e}), falling back to edge-tts")
    try:
        audio = asyncio.run(_tts_bytes_edge(clean))
        return base64.b64encode(audio).decode()
    except Exception as e:
        print(f"TTS error: {e}")
        return None


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def run_tool(name, inputs):
    if name == "get_host_status":       return px.get_host_status()
    if name == "get_container_list":    return px.get_container_list()
    if name == "container_action":      return px.container_action(inputs["vmid"], inputs["action"])
    if name == "get_disk_usage":        return px.get_disk_usage()
    if name == "get_ha_states":         return ha_get_states(inputs.get("domain", ""))
    if name == "ha_service":            return ha_call_service(inputs["domain"], inputs["service"], inputs["entity_id"], inputs.get("data", {}))
    if name == "get_weather":           return get_weather(inputs.get("location", LOCATION))
    if name == "web_search":            return web_search(inputs["query"], inputs.get("max_results", 5))
    if name == "read_email":            return read_email(inputs.get("count", 5), inputs.get("unread", False))
    if name == "execute_ssh":           return execute_ssh(inputs["host"], inputs["command"], inputs.get("user"))
    if name == "pct_exec":              return pct_exec_cmd(str(inputs["ctid"]), inputs["command"])
    if name == "send_discord_channel":  return send_discord_channel(inputs["channel"], inputs["message"])
    if name == "post_discord":          return post_discord(inputs["message"])
    return "Unknown tool"


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return r


@app.route("/")
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "NEXUS API", "version": "4.0",
                    "memory": nexus_memory.message_count(),
                    "cache_keys": list(nexus_cache._cache.keys())})


@app.route("/api/ask", methods=["POST", "OPTIONS"])
@limiter.limit("10 per minute")
def ask():
    if request.method == "OPTIONS":
        return "", 204

    data       = request.json or {}
    user_input = data.get("message", "").strip()
    tts        = data.get("tts", True)

    if not user_input:
        return jsonify({"error": "no message"}), 400

    # Load persistent history + add new user message
    history = nexus_memory.load_history()
    history.append({"role": "user", "content": user_input})
    nexus_memory.save_message("user", user_input)

    if len(history) > 40:
        history = history[-40:]

    messages = list(history)

    for _ in range(8):
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result)
                    })
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user",      "content": tool_results})
            continue

        reply = next((b.text for b in resp.content if hasattr(b, "text")), "")
        nexus_memory.save_message("assistant", reply)

        audio_b64 = generate_audio(reply) if tts else None
        return jsonify({"reply": reply, "audio": audio_b64})

    return jsonify({"reply": "Tool loop limit reached.", "audio": None}), 500


@app.route("/api/clear", methods=["POST"])
def clear():
    nexus_memory.clear_history()
    return jsonify({"status": "cleared"})


@app.route("/api/status")
def status():
    """Fast service status from cache."""
    cached = nexus_cache.cache_get("service_status")
    if cached:
        return jsonify({**cached["data"], "_cache_age": round(nexus_cache.cache_age("service_status"))})
    # Fallback: live check
    UP_CODES = {200, 301, 302, 401, 403}
    checks   = [("ha","http://192.168.0.9:8123"),("n8n","http://192.168.0.28:5678"),
                ("pihole","http://192.168.0.3"),("plex","http://192.168.0.34:32400")]
    services = {}
    for name, url in checks:
        try:
            urllib.request.urlopen(url, timeout=2)
            services[name] = "up"
        except urllib.error.HTTPError as e:
            services[name] = "up" if e.code in UP_CODES else "down"
        except Exception:
            services[name] = "down"
    return jsonify(services)


# ── Dashboard API endpoints (cache-backed) ────────────────────────────────────

@app.route("/api/proxmox/host")
def proxmox_host():
    entry = nexus_cache.cache_get("proxmox_host")
    if entry:
        return jsonify({"data": entry["data"], "age": round(nexus_cache.cache_age("proxmox_host"))})
    return jsonify({"data": px.get_host_status(), "age": 0})


@app.route("/api/proxmox/containers")
def proxmox_containers():
    entry = nexus_cache.cache_get("proxmox_containers")
    if entry:
        return jsonify({"data": entry["data"], "age": round(nexus_cache.cache_age("proxmox_containers"))})
    return jsonify({"data": px.get_container_list(), "age": 0})


@app.route("/api/proxmox/storage")
def proxmox_storage():
    entry = nexus_cache.cache_get("proxmox_storage")
    if entry:
        return jsonify({"data": entry["data"], "age": round(nexus_cache.cache_age("proxmox_storage"))})
    return jsonify({"data": px.get_disk_usage(), "age": 0})


@app.route("/api/ha/summary")
def ha_summary():
    entry = nexus_cache.cache_get("ha_summary")
    if entry:
        return jsonify({"data": entry["data"], "age": round(nexus_cache.cache_age("ha_summary"))})
    return jsonify({"data": ha_get_states(), "age": 0})


@app.route("/api/agents/status")
def agents_status():
    """Returns configured Discord department channels (IDs masked)."""
    channels = {k: bool(v) for k, v in DISCORD_CHANNELS.items()}
    return jsonify({"channels": channels, "bot_configured": bool(DISCORD_BOT_TOKEN)})


@app.route("/api/cache/age")
def cache_age_endpoint():
    return jsonify(nexus_cache.all_ages())


# ── Department Agent system prompts ───────────────────────────────────────────
# Each agent has its own identity, role, tools scope, and escalation rules.
# Agents use the same TOOLS list as NEXUS but from their own perspective.

# Rules injected into EVERY agent prompt
_AGENT_BASE_RULES = """
CRITICAL RULES — ALWAYS FOLLOW:

ACT, DON'T DESCRIBE:
- You have tools. USE them. Do not write commands for Antony to run.
- WRONG: "Run this command: ssh -i ~/.ssh/... to check the container"
- RIGHT: Call pct_exec or execute_ssh tool and report the result
- If you need information → use your tools to get it, then report findings
- If a tool fails → try an alternative tool, then report what happened

DISCORD FORMATTING:
- NO code blocks (no backticks, no ```)
- NO markdown headers (no # ## ###)
- Bold **text** for key points only
- Bullet points are fine
- Keep responses SHORT — under 300 characters unless detail is genuinely needed
- State what you DID and what the result was. Not what Antony should do.

SELF-CORRECTION (do this BEFORE posting to #manager):
1. Tool fails → retry once with different parameters
2. Still fails → try an alternative approach
3. Two attempts failed → THEN post to #manager: what you found, what you tried, what decision is needed
"""

AGENT_PROMPTS = {

"marketing": """You are the Call-On Ltd Marketing Agent — autonomous, action-oriented, results-focused.

BUSINESS: Call-On Ltd. Properties: call-on.dad (UK dads community), call-on.mom (UK moms community), call-on.media (landing), call-on.shop (Printful store).

YOUR ROLE:
- Own all marketing strategy and execution for all four properties
- Plan campaigns, social media strategy, email marketing, paid/organic growth
- Brief other agents: post detailed tasks to #seo (keyword/ranking work), #content (copy/articles)
- Track what's working and adapt — don't wait to be told

TOOLS YOU USE:
- web_search: competitor research, trend spotting, platform updates
- send_discord_channel: brief #seo, #content, #manager
- read_email: monitor marketing-related emails
- get_ha_states: not relevant — ignore

SELF-CORRECTION:
1. Task fails first attempt → retry with adjusted approach
2. Fails twice → post to #manager: what you tried, what's blocking, what decision you need
3. Need code/technical → brief #dev, don't attempt yourself
4. Need copy → brief #content with a full brief (audience, goal, length, tone)

RULES:
- Never claim something is done unless you've confirmed it
- Always state what you DID, not just what you plan to do
- UK English throughout
- Audience: UK parents aged 25–45, predominantly mobile""",


"seo": """You are the Call-On Ltd SEO Agent — technical, data-driven, execution-focused.

BUSINESS: Call-On Ltd. Primary SEO targets: call-on.dad and call-on.mom (UK parenting communities).

YOUR ROLE:
- Own all SEO: keyword strategy, on-page optimisation, technical health, link building
- Deliver keyword briefs to #content for every new piece of content
- Monitor rankings and flag drops or wins
- Identify quick-win opportunities and act on them without being asked

TOOLS YOU USE:
- web_search: SERP research, keyword volumes, competitor analysis, backlink research
- execute_ssh / pct_exec: check site technical health, page speed, server config
- send_discord_channel: brief #content, report to #marketing, escalate to #manager

SELF-CORRECTION:
1. Tool fails → check if it's a transient error, retry once
2. Data unavailable → note it, work with what you have, flag the gap
3. Need page changes → brief #dev with exact spec (file, line, change)
4. Blocked twice → escalate to #manager with full context

RULES:
- Every content recommendation must include target keyword, search intent, suggested title
- Flag any technical issue that could tank rankings (broken links, slow pages, missing meta)
- UK spellings in all content briefs""",


"dev": """You are the Call-On Ltd Dev Agent — precise, methodical, always verifies results.

INFRASTRUCTURE:
- Proxmox host: 192.168.0.10 (user: claude, full sudo)
- CT102 (MariaDB .6): Callon-dad, Callon-mom, wordpress_callon DBs — NEVER direct writes to live n8n DB
- CT112 (n8n .28): automation workflows
- CT117 (NEXUS .60): this system
- CT500 (Caddy .13): reverse proxy, PHP 8.4-FPM, webroot /var/www/html/
- GitHub org: Call-OnDad

YOUR ROLE:
- Implement all technical changes: code, config, deployments, container management
- Maintain and fix all services across the homelab
- Action infra tasks escalated from #infra agent
- Build features requested by other agents or Antony

TOOLS YOU USE:
- execute_ssh: run commands on any host
- pct_exec: run commands inside containers
- get_host_status / get_container_list / container_action: Proxmox management
- web_search: documentation, debugging

SELF-CORRECTION:
1. Command fails → read the error fully, check logs, try alternative approach
2. Second failure → post to #manager: exact error, what was tried, what's needed
3. Before ANY destructive action → verify backup exists or confirm with Antony
4. After every action → verify the result (check service running, curl the endpoint, etc.)

RULES:
- Never skip verification after a change
- Never commit secrets or credentials to git
- No direct DB writes to n8n — use n8n UI or API
- Stage specific files only (no git add -A)
- One change per task, confirm it works before moving on""",


"content": """You are the Call-On Ltd Content Agent — human, warm, audience-first.

HARD RULES — read every time before replying:
1. ALWAYS reply to every brief. Never go silent.
2. You CANNOT create files (no Google Sheets, no CSV uploads, no spreadsheet links). When a brief asks for one of those, DELIVER THE CONTENT INLINE as a Markdown table or fenced CSV block. Note in your reply: "Pasting inline — I can't create file links; copy into Sheets/Excel yourself."
3. Deliver in ONE reply. Don't split across messages. Don't promise to "send shortly".
4. Ship a first draft on every brief, even if research is incomplete. State assumptions, mark TODOs, but ship.
5. Only ask a clarifying question if you literally cannot start (e.g. the brand isn't named). Even then, include a best-effort draft alongside the question.

BRANDS:
- call-on.dad: UK dads community. Voice: real, straight-talking, zero corporate. Like a dad who's been there.
- call-on.mom: UK moms community. Voice: supportive, practical, community-first. Like your most grounded friend.
- call-on.media: Landing page. Voice: modern, clear, confident.
- call-on.shop: Product descriptions. Voice: friendly, helpful, parent-to-parent.

YOUR ROLE:
- Write all content: blog posts, social media copy, email newsletters, product descriptions, SEO articles, lists, schedules, tables
- Respond to content briefs from #seo, #marketing, #manager and Antony himself within the brief's spec
- Maintain brand voice consistency across all properties
- Suggest content angles and ideas proactively

TOOLS YOU USE:
- web_search: research topics, check facts, find UK-specific angles
- send_discord_channel: collaborate with #seo on keywords, ask #marketing for brand direction
- Your own reply text: ALL deliverables go here, inline. There is no file tool.

DELIVERABLE SHAPES YOU CAN PRODUCE INLINE:
- Markdown table for any tabular data (dates, holidays, schedules, comparison)
- Fenced code block (```csv) for spreadsheet-ready CSV
- Headed sections for long-form content
- Numbered/bulleted lists

EXAMPLE — brief asks for "spreadsheet of UK holidays with theme notes":
> Pasting inline (I can't create Sheets/CSV links — copy into Sheets yourself).
>
> | Date | Holiday | Theme suggestion |
> |---|---|---|
> | 1 Jan | New Year's Day | "Fresh start for dads" — habit-setting content |
> | 14 Feb | Valentine's Day | "Date night logistics" — childcare swap guide |
> ...

RULES:
- UK English always (colour, organisation, favourite, whilst)
- No AI-sounding phrases: never write "delve", "tapestry", "navigate", "leverage" as buzzwords
- Always state: audience, goal, word count, SEO keyword (if applicable) at top of any deliverable
- Write like a person, not a brand guidelines document""",


"infra": """You are the Call-On Ltd Infrastructure Agent — methodical, cautious, always checks before acting.

INFRASTRUCTURE MAP:
- Proxmox: 192.168.0.10 — HP DL380p Gen8, Xeon E5-2620, Proxmox 8.4
- CT101 (.34): Media Stack (Plex, Sonarr, Radarr, Docker)
- CT102 (.6): MariaDB — all app DBs
- CT105 (.3): Pi-hole DNS
- CT107 (.16): Proxmox Backup Server
- CT109 (.37): CrowdSec LAPI (listen: 0.0.0.0:8080)
- CT112 (.28): n8n + discord-agent (Docker)
- CT117 (.60): NEXUS API (this system)
- CT500 (.13): Caddy reverse proxy
- Storage: local 98GB, local-lvm 794GB, pbs 1099GB
- KNOWN OFFLINE (intentional): CT114 WordPress

YOUR ROLE:
- Respond to automated infra alerts and diagnose root cause
- Restart failed services, fix container issues
- Check logs and provide clear diagnosis
- Coordinate with #security on security-related infra issues
- Brief #dev when code or config changes are needed

TOOLS YOU USE:
- execute_ssh: SSH into any host for diagnostics and fixes
- pct_exec: run commands inside containers
- get_host_status / get_container_list / container_action / get_disk_usage: Proxmox API
- web_search: look up error messages, service docs

SELF-CORRECTION:
1. Service restart fails → check logs (journalctl -u <service> -n 50), find root cause
2. Root cause unclear → run full diagnostics, document findings, post to #manager
3. Anything touching production DBs → flag to Antony BEFORE acting
4. After every fix → verify the service is actually running (curl, status check)

ESCALATE IMMEDIATELY (no retries):
- Data corruption or loss risk
- Production DB issues
- Suspected security breach
- Disk at >95%""",


"business": """You are the Call-On Ltd Business Agent — commercial, outcome-focused, pragmatic.

BUSINESS OVERVIEW:
- Call-On Ltd — Antony's business running UK parenting communities
- Revenue streams: community memberships, shop (Printful), advertising (future)
- Domains: call-on.dad, call-on.mom, call-on.media, call-on.shop (all Cloudflare)
- SMTP: MailerSend (dad/mom/media domains)
- DB: MariaDB CT102 at 192.168.0.6 — Callon-dad, Callon-mom schemas

YOUR ROLE:
- Monitor business health: domain status, site uptime, revenue indicators
- Track operational costs and flag unnecessary spend
- Manage vendor relationships (Cloudflare, Printful, MailerSend)
- Support strategic planning and decision-making for Antony
- Cross-dept coordination for business outcomes

TOOLS YOU USE:
- web_search: competitor intel, pricing research, industry news
- execute_ssh / pct_exec: check DB stats, site health
- send_discord_channel: coordinate #dev, #marketing, report to #manager
- read_email: monitor business-critical emails

SELF-CORRECTION:
1. Needs financial decision → ALWAYS flag to Antony, never proceed autonomously
2. Domain/DNS change needed → brief #dev with exact spec
3. Ambiguous situation → present options with pros/cons, ask Antony to decide

RULES:
- NEVER authorise spend or transactions without Antony's explicit approval
- Always frame issues as: situation → impact → recommended action → decision needed""",


"community": """You are the Call-On Ltd Community Agent — warm, human, community-obsessed.

COMMUNITIES:
- call-on.dad: UK dads. Growing community — topics, videos, conversations, shop
- call-on.mom: UK moms. Earlier stage — topics, videos

TARGET AUDIENCE: UK parents aged 25–45, working parents, real people not influencers.

YOUR ROLE:
- Monitor community health: activity, engagement, user growth, sentiment
- Identify and act on growth opportunities
- Create community initiatives (challenges, discussions, events)
- Brief #content on community-driven content needs (what members are asking for)
- Flag problems: trolls, spam, user complaints

TOOLS YOU USE:
- pct_exec: query MariaDB CT102 for community stats (Callon-dad, Callon-mom schemas)
- web_search: competitor communities, engagement ideas, parenting trends UK
- send_discord_channel: brief #content, escalate to #manager
- read_email: community contact form submissions

SELF-CORRECTION:
1. DB unavailable → note it, work from last known data
2. Sensitive moderation issue → don't act unilaterally, flag to Antony
3. Need content → post to #content with full brief (topic, angle, audience, goal)

RULES:
- UK English always
- Decisions affecting real users → flag to Antony before acting
- Every community suggestion should tie back to growth or retention metric""",


"security": """You are the Call-On Ltd Security Agent — evidence-based, zero speculation, act fast on confirmed threats.

SECURITY STACK:
- CrowdSec LAPI: CT109 at 192.168.0.37:8080 — health: curl returns 403
- Caddy reverse proxy: CT500 at 192.168.0.13
- Tailscale: private Tailscale network — Antony has unique access
- Pi-hole DNS: CT105 at 192.168.0.3

SERVICES TO PROTECT:
- NEXUS API: 100.71.24.81:5000 (Tailscale only)
- n8n: 192.168.0.28:5678
- All public domains via Caddy

YOUR ROLE:
- Monitor CrowdSec alerts and action bans/unbans
- Review access logs for anomalies
- Check SSL certificate expiry
- Alert #infra of infrastructure-level security issues
- Post weekly security summary to #security

TOOLS YOU USE:
- execute_ssh / pct_exec: query CrowdSec, check logs, review Caddy access logs
- get_host_status: check for unusual load (sign of attack)
- web_search: research CVEs, threat intelligence
- send_discord_channel: alert #infra, escalate to #manager

SELF-CORRECTION:
1. Possible false positive → verify before banning, check IP reputation
2. Confirmed threat → block immediately, document, post to #manager
3. Uncertain → document evidence, post to #manager with recommendation

ESCALATE IMMEDIATELY (call Antony if needed):
- Active data breach
- Ransomware indicators
- Unusual outbound traffic from internal hosts
- Auth failures from internal IPs""",


"general": """You are NEXUS — the central intelligence for Call-On Ltd and Antony's homelab.

Handle anything that doesn't fit a specific department. Route specific tasks to the right channel.
Full homelab access. Sharp, direct, confident. You know the full operation.""",


"manager": """You are the Call-On Ltd Manager Agent. Your job is to DELEGATE — never to do the work yourself.

HARD RULES — read every time before replying:
1. You DO NOT post code, SSH commands, bash snippets, or step-by-step tutorials. Ever. That is the dev/infra agents' job.
2. You DO NOT explain how to fix something. You hand it off and stop.
3. You DO NOT diagnose. You delegate diagnosis to the relevant agent.
4. Your reply to Antony is ONE short sentence (≤ 20 words) acknowledging receipt and naming who you delegated to.
5. Your delegation to another agent is ONE short paragraph (≤ 60 words): what + expected output + deadline if any.
6. If you catch yourself writing a code block, STOP. Delete it. Send the task to dev/infra instead.

DEPARTMENTS UNDER YOU (route by topic):
- #infra: container/service health, SSH, Proxmox, homelab outages → use this for ANY "container stopped" / "service down" alert
- #dev: code changes, deployments, app bugs
- #marketing: campaigns, social, growth
- #seo: rankings, keywords, technical SEO
- #content: all written content
- #business: operations, costs, strategy, finance
- #community: community health, user issues
- #security: threats, access, CrowdSec, fail2ban

PROCESS (do this in order, every time):
1. Identify the SINGLE most-relevant department.
2. Call send_discord_channel(channel=<dept>, message=<one paragraph task>).
3. Reply to Antony: "Routed to #<dept>. Will report back when they're done."
4. STOP. Do not keep talking. Do not add context. Do not write code.

DECISION AUTHORITY:
- You may approve: tasks under £100, non-destructive changes, content approvals.
- Flag to Antony FIRST: anything over £100, irreversible changes, security incidents, strategy pivots.

CONVERSATION HYGIENE:
- Treat any "Authentication failed" / "SSH error" in old messages as STALE — credentials work now.
- If you previously claimed something was broken, don't keep claiming it. Verify current state by delegating.
- Don't re-list the same diagnosis. One delegation per request, then wait.

Bad response (DO NOT DO THIS):
> "Let me check that. First run: `ssh -i ~/.ssh/claude_proxmox claude@192.168.0.10 'sudo pct list'`..."

Good response:
> "Routed to #infra to investigate the stopped container and report back. Will close the loop with you when they're done."
(while in parallel calling send_discord_channel("infra", "..."))"""
}

# Per-agent conversation histories (in-memory, up to 30 messages)
_agent_histories = {dept: [] for dept in AGENT_PROMPTS}
_AGENT_MAX_HIST  = 30


@app.route("/api/agent/<dept>", methods=["POST", "OPTIONS"])
def agent_chat(dept):
    """Department-specific agent endpoint with own system prompt and conversation history."""
    if request.method == "OPTIONS":
        return "", 204

    dept = dept.lower().strip()
    if dept not in AGENT_PROMPTS:
        return jsonify({"error": f"Unknown dept: {dept}. Valid: {list(AGENT_PROMPTS.keys())}"}), 400

    data       = request.json or {}
    user_input = data.get("message", "").strip()
    if not user_input:
        return jsonify({"error": "no message"}), 400

    history = _agent_histories[dept]
    history.append({"role": "user", "content": user_input})
    if len(history) > _AGENT_MAX_HIST:
        history[:] = history[-_AGENT_MAX_HIST:]

    messages = list(history)
    system   = AGENT_PROMPTS[dept]

    for _ in range(8):
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=messages
        )

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result)
                    })
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user",      "content": tool_results})
            continue

        reply = next((b.text for b in resp.content if hasattr(b, "text")), "")
        history.append({"role": "assistant", "content": reply})
        return jsonify({"reply": reply, "dept": dept})

    return jsonify({"reply": "Tool loop limit reached.", "dept": dept}), 500


@app.route("/api/agent/<dept>/clear", methods=["POST"])
def agent_clear(dept):
    dept = dept.lower()
    if dept in _agent_histories:
        _agent_histories[dept] = []
    return jsonify({"status": "cleared", "dept": dept})


# ── Discord channel read ──────────────────────────────────────────────────────

def _read_discord_channel_messages(channel_name, limit=8):
    channel_id = DISCORD_CHANNELS.get(channel_name.lower().strip(), "")
    if not channel_id:
        return {"error": f"Unknown channel: {channel_name}"}
    if not DISCORD_BOT_TOKEN:
        return {"error": "DISCORD_BOT_TOKEN not set"}
    import time as _time
    for attempt in range(3):  # retry up to 3x on connection reset
        try:
            req = urllib.request.Request(
                f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}",
                headers={
                    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                    "User-Agent": "DiscordBot (nexus, 1.0)",
                    "Connection": "close"
                }
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                msgs = json.loads(r.read())
            return {"channel": channel_name, "messages": [
                {
                    "author": m["author"]["username"],
                    "content": m["content"][:300],
                    "ts": m["timestamp"][:16].replace("T", " ")
                } for m in msgs if m.get("content")
            ]}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = float(e.headers.get("Retry-After", 1))
                _time.sleep(min(retry_after, 3))
                continue
            return {"error": f"Discord {e.code}: {e.read().decode(errors='ignore')[:100]}"}
        except (ConnectionResetError, ConnectionError):
            if attempt < 2:
                _time.sleep(0.8 * (attempt + 1))
                continue
            return {"error": "Discord connection reset after retries"}
        except Exception as e:
            return {"error": str(e)}
    return {"error": "Discord: max retries exceeded"}

@app.route("/api/discord/channel/<name>")
def discord_channel(name):
    return jsonify(_read_discord_channel_messages(name))


# ── Structured email inbox ─────────────────────────────────────────────────────

def _fetch_imap_structured(account, count=8, unread_only=False):
    ssl  = account.get("ssl", True)
    conn = imaplib.IMAP4_SSL(account["host"]) if ssl else imaplib.IMAP4(account["host"])
    conn.login(account["user"], account["password"])
    conn.select("inbox")
    criteria = "UNSEEN" if unread_only else "ALL"
    _, msgs   = conn.search(None, criteria)
    ids       = msgs[0].split()[-count:]
    results   = []
    for mid in reversed(ids):
        _, data = conn.fetch(mid, "(RFC822)")
        msg     = emaillib.message_from_bytes(data[0][1])
        raw_subj = str(msg["Subject"] or "(no subject)")
        subject_raw, enc = decode_header(raw_subj)[0]
        subject = subject_raw.decode(enc or "utf-8") if isinstance(subject_raw, bytes) else str(subject_raw or "(no subject)")
        # Get body preview
        preview = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        preview = part.get_payload(decode=True).decode(errors="ignore")[:120]
                    except:
                        pass
                    break
        else:
            try:
                preview = msg.get_payload(decode=True).decode(errors="ignore")[:120]
            except:
                pass
        results.append({
            "from":    msg["From"][:60] if msg["From"] else "Unknown",
            "subject": subject[:80],
            "date":    msg["Date"][:25] if msg["Date"] else "",
            "preview": preview.strip()[:120]
        })
    conn.logout()
    return results

@app.route("/api/email/inbox")
def email_inbox():
    # Serve from cache (updated every 10 min by background thread)
    entry = nexus_cache.cache_get("email_inbox")
    if entry:
        age = round(nexus_cache.cache_age("email_inbox"))
        data = dict(entry["data"])
        data["cache_age"] = age
        return jsonify(data)
    # Cache miss — fetch live (slow, ~25s)
    accounts = _load_email_accounts()
    if not accounts:
        return jsonify({"error": "No email accounts configured"})
    result = []
    for acc in accounts:
        try:
            msgs = _fetch_imap_structured(acc, count=8)
            result.append({"account": acc["name"], "messages": msgs, "error": None})
        except Exception as e:
            result.append({"account": acc["name"], "messages": [], "error": str(e)})
    return jsonify({"accounts": result, "cache_age": None})


# ── Community / DB stats ───────────────────────────────────────────────────────

DB_HOST = "192.168.0.6"
DB_PORT = 3306

@app.route("/api/community/stats")
def community_stats():
    # Run mysql inside CT102 via Proxmox pct exec — no SSH key needed
    cmd = (
        "mysql -u root -e \""
        "SELECT table_schema, table_name, table_rows "
        "FROM information_schema.tables "
        "WHERE table_schema IN ('Callon-dad','Callon-mom') "
        "AND table_rows > 0 "
        "ORDER BY table_schema, table_rows DESC;"
        "\" 2>/dev/null"
    )
    raw = pct_exec_cmd("102", cmd)
    if not raw or "error" in raw.lower() or "denied" in raw.lower():
        return jsonify({"error": raw or "DB unavailable via CT102"})

    # Parse tab-separated output into {site: {table: rows}}
    stats = {}
    for line in raw.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or parts[0] in ("table_schema", "TABLE_SCHEMA"):
            continue
        schema, table, rows_str = parts[0], parts[1], parts[2]
        key = schema.replace("Callon-", "").lower()
        try:
            stats.setdefault(key, {})[table] = int(rows_str)
        except ValueError:
            pass
    return jsonify(stats if stats else {"error": "No data returned — check CT102 mysql access"})


# ── Domain ping ────────────────────────────────────────────────────────────────

def _check_domain(domain):
    try:
        req = urllib.request.Request(
            f"https://{domain}", headers={"User-Agent": "NEXUS/4.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return domain, {"status": "up", "code": r.status}
    except urllib.error.HTTPError as e:
        return domain, {"status": "up" if e.code < 500 else "down", "code": e.code}
    except Exception as e:
        return domain, {"status": "down", "error": str(e)[:60]}

@app.route("/api/domains/status")
def domains_status():
    import concurrent.futures
    domains = ["call-on.dad", "call-on.mom", "call-on.media", "call-on.shop"]
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for domain, result in ex.map(_check_domain, domains):
            results[domain] = result
    return jsonify(results)


# ── Cloudflare analytics ──────────────────────────────────────────────────────

CF_GRAPHQL    = "https://api.cloudflare.com/client/v4/graphql"
CF_API_TOKEN  = os.environ.get("CF_API_TOKEN", "")
CF_ZONES      = {
    "call-on.dad":   os.environ.get("CF_ZONE_ID_DAD",   ""),
    "call-on.mom":   os.environ.get("CF_ZONE_ID_MOM",   ""),
    "call-on.media": os.environ.get("CF_ZONE_ID_MEDIA", ""),
    "call-on.shop":  os.environ.get("CF_ZONE_ID_SHOP",  ""),
}
CF_CACHE_TTL  = 600   # 10 minutes

CF_QUERY = """
query Zone($zone: String!, $sinceDate: Date!) {
  viewer {
    zones(filter: {zoneTag: $zone}) {
      rollup: httpRequests1dGroups(
        limit: 1
        filter: {date_geq: $sinceDate}
      ) {
        sum {
          requests
          threats
          countryMap { clientCountryName requests threats }
        }
      }
    }
  }
}
"""


def _cf_query_zone(zone_id, since_date):
    """Run GraphQL for one zone, return dict or {'error': msg}."""
    if not CF_API_TOKEN or not zone_id:
        return {"error": "missing CF_API_TOKEN or zone_id"}
    body = json.dumps({
        "query": CF_QUERY,
        "variables": {"zone": zone_id, "sinceDate": since_date},
    }).encode()
    req = urllib.request.Request(
        CF_GRAPHQL,
        data=body,
        headers={
            "Authorization": f"Bearer {CF_API_TOKEN}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"CF HTTP {e.code}: {e.read()[:200].decode(errors='replace')}"}
    except Exception as e:
        return {"error": f"CF query failed: {e}"}
    if payload.get("errors"):
        return {"error": "CF errors: " + json.dumps(payload["errors"])[:200]}
    zones_arr = (payload.get("data", {}).get("viewer", {}).get("zones") or [])
    if not zones_arr:
        return {"error": "no zone data returned"}
    z = zones_arr[0]
    rollup = (z.get("rollup") or [{}])[0].get("sum") or {}
    country_map = rollup.get("countryMap") or []
    # Top countries by requests, top 5
    countries = sorted(
        [{"name": c.get("clientCountryName") or "?",
          "requests": c.get("requests", 0),
          "threats":  c.get("threats", 0)} for c in country_map],
        key=lambda c: c["requests"], reverse=True
    )[:5]
    return {
        "requests_24h": rollup.get("requests", 0),
        "threats_blocked_24h": rollup.get("threats", 0),
        "top_countries": countries,
        # top_paths not supported on Free plan — omit / empty
        "top_paths": [],
    }


def _cf_summary_fresh():
    """Query all configured zones in parallel, return aggregate."""
    import concurrent.futures, datetime
    # httpRequests1dGroups uses Date (YYYY-MM-DD); query yesterday's full day.
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    out   = {"_since": yesterday, "zones": {}}
    pending = {name: zid for name, zid in CF_ZONES.items() if zid}
    if not pending:
        return {"error": "no CF zone IDs configured", "zones": {}}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(pending)) as ex:
        futs = {ex.submit(_cf_query_zone, zid, yesterday): name for name, zid in pending.items()}
        for f in concurrent.futures.as_completed(futs):
            name = futs[f]
            try:
                res = f.result()
            except Exception as e:
                res = {"error": f"thread: {e}"}
            # Tag plan-restricted zones with a friendlier error
            if "error" in res and "does not have access" in res.get("error", ""):
                res = {"error": "Free plan — adaptive analytics unavailable", "plan_restricted": True}
            out["zones"][name] = res
    return out


@app.route("/api/cloudflare/summary")
def cloudflare_summary():
    """Per-domain Cloudflare analytics, cached 10 min."""
    cached = nexus_cache.cache_get("cloudflare_summary")
    age    = nexus_cache.cache_age("cloudflare_summary")
    if cached and age is not None and age < CF_CACHE_TTL:
        return jsonify({"data": cached["data"], "age": round(age)})
    data = _cf_summary_fresh()
    if "error" in data and not data.get("zones"):
        return jsonify({"error": data["error"]}), 503
    nexus_cache.cache_set("cloudflare_summary", data)
    return jsonify({"data": data, "age": 0})


# ── GA4 analytics ─────────────────────────────────────────────────────────────

GA4_PROPERTIES = {
    "call-on.dad":   os.environ.get("GA4_PROPERTY_ID_DAD",   ""),
    "call-on.mom":   os.environ.get("GA4_PROPERTY_ID_MOM",   ""),
    "call-on.media": os.environ.get("GA4_PROPERTY_ID_MEDIA", ""),
    "call-on.shop":  os.environ.get("GA4_PROPERTY_ID_SHOP",  ""),
}
GA4_CACHE_TTL = 600  # 10 minutes

_ga4_client = None
_ga4_client_err = None


def _ga4_get_client():
    """Lazily build the GA4 client. Cache the import + client between calls."""
    global _ga4_client, _ga4_client_err
    if _ga4_client is not None or _ga4_client_err is not None:
        return _ga4_client, _ga4_client_err
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        _ga4_client = BetaAnalyticsDataClient()  # reads GOOGLE_APPLICATION_CREDENTIALS
    except Exception as e:
        _ga4_client_err = f"GA4 client init failed: {type(e).__name__}: {e}"
    return _ga4_client, _ga4_client_err


def _ga4_query_property(prop_id):
    """Run two queries: 24h headline + top countries. Return dict or {'error':...}."""
    client, err = _ga4_get_client()
    if err:
        return {"error": err}
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Dimension, Metric
        )
        # Headline: sessions, users, page views, engagement (last 1 day)
        head_req = RunReportRequest(
            property=f"properties/{prop_id}",
            date_ranges=[DateRange(start_date="1daysAgo", end_date="today")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="activeUsers"),
                Metric(name="screenPageViews"),
                Metric(name="averageSessionDuration"),
            ],
        )
        head = client.run_report(head_req)
        head_row = head.rows[0] if head.rows else None
        def _mv(i):
            try:
                return float(head_row.metric_values[i].value) if head_row else 0
            except Exception:
                return 0
        sessions  = int(_mv(0))
        users     = int(_mv(1))
        pageviews = int(_mv(2))
        avg_sess  = round(_mv(3), 1)
        # Top countries
        country_req = RunReportRequest(
            property=f"properties/{prop_id}",
            date_ranges=[DateRange(start_date="1daysAgo", end_date="today")],
            dimensions=[Dimension(name="country")],
            metrics=[Metric(name="activeUsers")],
            limit=5,
        )
        country_rep = client.run_report(country_req)
        countries = []
        for r in country_rep.rows:
            name = r.dimension_values[0].value or "?"
            cnt  = int(float(r.metric_values[0].value or 0))
            countries.append({"name": name, "users": cnt})
        countries.sort(key=lambda c: c["users"], reverse=True)
        # Top pages
        page_req = RunReportRequest(
            property=f"properties/{prop_id}",
            date_ranges=[DateRange(start_date="1daysAgo", end_date="today")],
            dimensions=[Dimension(name="pagePath")],
            metrics=[Metric(name="screenPageViews")],
            limit=5,
        )
        page_rep = client.run_report(page_req)
        pages = []
        for r in page_rep.rows:
            path  = r.dimension_values[0].value or "/"
            views = int(float(r.metric_values[0].value or 0))
            pages.append({"path": path[:80], "views": views})
        pages.sort(key=lambda p: p["views"], reverse=True)
        return {
            "sessions_24h":  sessions,
            "users_24h":     users,
            "pageviews_24h": pageviews,
            "avg_session_s": avg_sess,
            "top_countries": countries,
            "top_pages":     pages,
        }
    except Exception as e:
        msg = str(e)
        # Common: PERMISSION_DENIED if SA not added to property
        if "PERMISSION_DENIED" in msg or "permission" in msg.lower():
            return {"error": "PERMISSION_DENIED — add SA to this property", "permission_error": True}
        return {"error": f"{type(e).__name__}: {msg[:200]}"}


def _ga4_summary_fresh():
    import concurrent.futures
    out = {"zones": {}}
    pending = {name: pid for name, pid in GA4_PROPERTIES.items() if pid}
    if not pending:
        return {"error": "no GA4 property IDs configured", "zones": {}}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(pending)) as ex:
        futs = {ex.submit(_ga4_query_property, pid): name for name, pid in pending.items()}
        for f in concurrent.futures.as_completed(futs):
            name = futs[f]
            try:
                out["zones"][name] = f.result()
            except Exception as e:
                out["zones"][name] = {"error": f"thread: {e}"}
    return out


@app.route("/api/ga4/summary")
def ga4_summary():
    """Per-property GA4 last-24h analytics, cached 10 min.

    Skips caching when every zone errored — typically a transient DNS
    blip — so the next request retries instead of serving stale errors.
    """
    cached = nexus_cache.cache_get("ga4_summary")
    age    = nexus_cache.cache_age("ga4_summary")
    if cached and age is not None and age < GA4_CACHE_TTL:
        return jsonify({"data": cached["data"], "age": round(age)})
    data = _ga4_summary_fresh()
    if "error" in data and not data.get("zones"):
        return jsonify({"error": data["error"]}), 503
    zones = data.get("zones", {})
    all_errored = bool(zones) and all("error" in (z or {}) for z in zones.values())
    if not all_errored:
        nexus_cache.cache_set("ga4_summary", data)
    return jsonify({"data": data, "age": 0, "transient": all_errored})


# ── Per-container live stats (via pvesh cluster/resources) ──────────────────

CTSTATS_CACHE_TTL = 30  # 30s — these change fast


def _ctstats_fresh():
    """Run pvesh on the Proxmox host, parse per-CT cpu/mem/disk/uptime.

    Calls subprocess directly to bypass execute_ssh's 2000-char truncation.
    """
    try:
        r = subprocess.run(
            ['ssh', '-i', NEXUS_SSH_KEY, '-o', 'StrictHostKeyChecking=no',
             '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
             f'claude@{PROXMOX_HOST}',
             'sudo pvesh get /cluster/resources --type vm --output-format json'],
            capture_output=True, text=True, timeout=20
        )
        raw = r.stdout
    except subprocess.TimeoutExpired:
        return {"error": "pvesh timed out"}
    except Exception as e:
        return {"error": f"ssh: {e}"}
    try:
        arr = json.loads(raw)
    except Exception as e:
        return {"error": f"parse: {e}"}
    out = []
    for r in arr:
        if r.get("type") != "lxc":
            continue
        max_mem = r.get("maxmem") or 1
        cpu_pct = round((r.get("cpu") or 0) * 100, 1)  # 0-1 fraction × maxcpu cores
        mem_pct = round(((r.get("mem") or 0) / max_mem) * 100, 1)
        max_disk = r.get("maxdisk") or 1
        disk_pct = round(((r.get("disk") or 0) / max_disk) * 100, 1)
        out.append({
            "ctid":     r.get("vmid"),
            "name":     r.get("name") or "",
            "status":   r.get("status") or "",
            "cpu_pct":  cpu_pct,
            "max_cpu":  r.get("maxcpu") or 1,
            "mem_pct":  mem_pct,
            "mem_mb":   round((r.get("mem") or 0) / (1024*1024)),
            "max_mem_mb": round(max_mem / (1024*1024)),
            "disk_pct": disk_pct,
            "uptime_s": r.get("uptime") or 0,
        })
    out.sort(key=lambda x: x["ctid"])
    return {"containers": out}


@app.route("/api/proxmox/container_stats")
def proxmox_container_stats():
    cached = nexus_cache.cache_get("ct_stats")
    age    = nexus_cache.cache_age("ct_stats")
    if cached and age is not None and age < CTSTATS_CACHE_TTL:
        return jsonify({"data": cached["data"], "age": round(age)})
    data = _ctstats_fresh()
    if "error" in data:
        return jsonify({"error": data["error"]}), 503
    nexus_cache.cache_set("ct_stats", data)
    return jsonify({"data": data, "age": 0})


# ── Shop summary (CT102 MariaDB · Callon-dad.shop_*) ─────────────────────────

SHOP_CACHE_TTL = 300  # 5 min

SHOP_QUERIES = """
SELECT 'orders_today', COUNT(*) FROM shop_orders WHERE DATE(created_at) = CURDATE() UNION ALL
SELECT 'orders_7d',    COUNT(*) FROM shop_orders WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) UNION ALL
SELECT 'orders_30d',   COUNT(*) FROM shop_orders WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) UNION ALL
SELECT 'revenue_today',COALESCE(SUM(total),0) FROM shop_orders WHERE DATE(created_at) = CURDATE() AND status NOT IN ('cancelled','refunded') UNION ALL
SELECT 'revenue_7d',   COALESCE(SUM(total),0) FROM shop_orders WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND status NOT IN ('cancelled','refunded') UNION ALL
SELECT 'revenue_30d',  COALESCE(SUM(total),0) FROM shop_orders WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) AND status NOT IN ('cancelled','refunded') UNION ALL
SELECT 'pending',      COUNT(*) FROM shop_orders WHERE status IN ('pending','processing','awaiting_fulfilment','awaiting_fulfillment') UNION ALL
SELECT 'products_live',COUNT(*) FROM shop_products WHERE active = 1 UNION ALL
SELECT 'products_all', COUNT(*) FROM shop_products;
"""


def _shop_summary_fresh():
    try:
        # Run all aggregate queries in one batch via pct_exec.
        cmd = "mysql -N -B -e \"" + SHOP_QUERIES.replace("\n", " ").strip() + "\" Callon-dad"
        raw = pct_exec_cmd("102", cmd)
        if raw.startswith("SSH"):
            return {"error": raw}
        out = {}
        for line in raw.strip().splitlines():
            parts = line.split("\t")
            if len(parts) == 2:
                key, val = parts
                try:
                    f = float(val)
                    out[key] = f if "revenue" in key else int(f)
                except ValueError:
                    out[key] = val
        # Top products last 30d by units sold
        top_cmd = ("mysql -N -B -e \"SELECT p.title, SUM(oi.quantity) AS units "
                   "FROM shop_order_items oi JOIN shop_orders o ON oi.order_id=o.id "
                   "JOIN shop_products p ON oi.product_id=p.id "
                   "WHERE o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) "
                   "AND o.status NOT IN ('cancelled','refunded') "
                   "GROUP BY p.id ORDER BY units DESC LIMIT 5;\" Callon-dad")
        top_raw = pct_exec_cmd("102", top_cmd)
        top = []
        if not top_raw.startswith("SSH"):
            for line in top_raw.strip().splitlines():
                parts = line.split("\t")
                if len(parts) == 2:
                    top.append({"title": parts[0][:60], "units": int(parts[1])})
        out["top_products_30d"] = top
        return out
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@app.route("/api/shop/summary")
def shop_summary():
    cached = nexus_cache.cache_get("shop_summary")
    age    = nexus_cache.cache_age("shop_summary")
    if cached and age is not None and age < SHOP_CACHE_TTL:
        return jsonify({"data": cached["data"], "age": round(age)})
    data = _shop_summary_fresh()
    if "error" in data:
        return jsonify({"error": data["error"]}), 503
    nexus_cache.cache_set("shop_summary", data)
    return jsonify({"data": data, "age": 0})


# ── Social workflow (CT112 n8n SQLite) ────────────────────────────────────────

SOCIAL_CACHE_TTL = 300


def _social_summary_fresh():
    # n8n SQLite at /opt/n8n/data/database.sqlite — query workflows + executions.
    sql = (
        "SELECT 'workflows_active', COUNT(*) FROM workflow_entity WHERE active=1; "
        "SELECT 'exec_24h',          COUNT(*) FROM execution_entity WHERE startedAt >= datetime('now','-1 day'); "
        "SELECT 'exec_24h_success',  COUNT(*) FROM execution_entity WHERE startedAt >= datetime('now','-1 day') AND status='success'; "
        "SELECT 'exec_24h_failed',   COUNT(*) FROM execution_entity WHERE startedAt >= datetime('now','-1 day') AND status IN ('error','crashed','failed'); "
        "SELECT 'exec_running',      COUNT(*) FROM execution_entity WHERE status='running' OR finished=0; "
    )
    cmd = "sqlite3 -batch /opt/n8n/data/database.sqlite \"" + sql.replace('"','\\"') + "\""
    raw = pct_exec_cmd("112", cmd)
    if raw.startswith("SSH"):
        return {"error": raw}
    out = {}
    for line in raw.strip().splitlines():
        parts = line.split("|")
        if len(parts) == 2:
            try:
                out[parts[0]] = int(parts[1])
            except ValueError:
                out[parts[0]] = parts[1]
    # Recent workflow names (active) + their last run
    names_cmd = ("sqlite3 -batch /opt/n8n/data/database.sqlite "
                 "\"SELECT w.name, MAX(e.stoppedAt), e.status FROM workflow_entity w "
                 "LEFT JOIN execution_entity e ON e.workflowId = w.id "
                 "WHERE w.active=1 GROUP BY w.id ORDER BY MAX(e.stoppedAt) DESC LIMIT 6;\"")
    names_raw = pct_exec_cmd("112", names_cmd)
    flows = []
    if not names_raw.startswith("SSH"):
        for line in names_raw.strip().splitlines():
            parts = line.split("|")
            if len(parts) >= 1:
                flows.append({
                    "name":    (parts[0] if len(parts) > 0 else "")[:50],
                    "last":    (parts[1] if len(parts) > 1 else "") or "—",
                    "status":  (parts[2] if len(parts) > 2 else "") or "—",
                })
    out["active_workflows"] = flows
    return out


@app.route("/api/social/queue")
def social_queue():
    cached = nexus_cache.cache_get("social_queue")
    age    = nexus_cache.cache_age("social_queue")
    if cached and age is not None and age < SOCIAL_CACHE_TTL:
        return jsonify({"data": cached["data"], "age": round(age)})
    data = _social_summary_fresh()
    if "error" in data:
        return jsonify({"error": data["error"]}), 503
    nexus_cache.cache_set("social_queue", data)
    return jsonify({"data": data, "age": 0})


# ── Whisper transcription ─────────────────────────────────────────────────────

_whisper_model     = None
WHISPER_MODEL_PATH = "/opt/wyoming/whisper-data/models--rhasspy--faster-whisper-tiny-int8/snapshots/5b6382e0f4ac867ce9ff24aaa249400a7c6c73d9"


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(WHISPER_MODEL_PATH, device="cpu", compute_type="int8")
    return _whisper_model


@app.route("/api/transcribe", methods=["POST", "OPTIONS"])
def transcribe():
    if request.method == "OPTIONS":
        return "", 204
    if "audio" not in request.files:
        return jsonify({"error": "no audio file"}), 400
    import tempfile
    audio_file = request.files["audio"]
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
        audio_file.save(tmp_in.name)
        tmp_in_path = tmp_in.name
    tmp_wav_path = tmp_in_path.replace(".webm", ".wav")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in_path, "-ar", "16000", "-ac", "1", tmp_wav_path],
            capture_output=True, timeout=30
        )
        if r.returncode != 0 or not os.path.exists(tmp_wav_path):
            err = r.stderr.decode(errors="ignore")[-300:]
            return jsonify({"error": "audio conversion failed", "detail": err}), 500
        model     = get_whisper_model()
        segments, _ = model.transcribe(tmp_wav_path, language="en", beam_size=1)
        transcript  = " ".join(s.text for s in segments).strip()
        return jsonify({"transcript": transcript})
    except Exception as e:
        import traceback
        print(f"[transcribe] {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500
    finally:
        for p in [tmp_in_path, tmp_wav_path]:
            try: os.unlink(p)
            except: pass


# ── Startup ───────────────────────────────────────────────────────────────────

nexus_cache.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
