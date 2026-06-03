#!/usr/bin/env python3
"""One-shot Discord channel purger.

Reads DISCORD_BOT_TOKEN + DISCORD_CHANNEL_{MANAGER,DEV,INFRA} from /opt/ahas/.env
and bulk-deletes every message <14 days old in those three channels.

Usage:  python3 /opt/ahas/purge_channels.py
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error

ENV_FILE = '/opt/ahas/.env'
CHANNELS_TO_PURGE = ['manager', 'dev', 'infra']
API_BASE = 'https://discord.com/api/v10'

# Load .env (simple parser — no quotes/multiline)
def load_env(path):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

env = load_env(ENV_FILE)
TOKEN = env.get('DISCORD_BOT_TOKEN')
if not TOKEN:
    sys.exit('DISCORD_BOT_TOKEN missing from .env')

HEADERS = {
    'Authorization': f'Bot {TOKEN}',
    'Content-Type':  'application/json',
    'User-Agent':    'DiscordBot (nexus-purge, 1.0)',
}

def discord_request(method, path, body=None):
    url  = API_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def fetch_messages(channel_id, limit=100):
    code, body = discord_request('GET', f'/channels/{channel_id}/messages?limit={limit}')
    if code != 200:
        print(f'  fetch failed {code}: {body[:200]}')
        return []
    return json.loads(body)

def bulk_delete(channel_id, ids):
    if len(ids) < 2:
        # Bulk-delete needs 2-100. Delete single one normally.
        if ids:
            code, body = discord_request('DELETE', f'/channels/{channel_id}/messages/{ids[0]}')
            return code in (204, 200), code, body
        return True, 200, b''
    # Honour 429 retry-after up to 5 times.
    for _ in range(5):
        code, body = discord_request(
            'POST',
            f'/channels/{channel_id}/messages/bulk-delete',
            {'messages': ids}
        )
        if code == 429:
            try:
                wait = float(json.loads(body).get('retry_after', 2.0)) + 0.3
            except Exception:
                wait = 2.0
            print(f'    rate-limited, sleeping {wait:.1f}s')
            time.sleep(wait)
            continue
        return code in (204, 200), code, body
    return False, code, body

for ch in CHANNELS_TO_PURGE:
    env_key = f'DISCORD_CHANNEL_{ch.upper()}'
    ch_id = env.get(env_key)
    if not ch_id:
        print(f'[{ch}] no channel id in .env ({env_key}) — skip')
        continue
    print(f'\n=== #{ch}  channel={ch_id} ===')
    total_deleted = 0
    rounds = 0
    while True:
        rounds += 1
        if rounds > 20:
            print(f'  stop after 20 rounds (safety cap)')
            break
        msgs = fetch_messages(ch_id, 100)
        if not msgs:
            print(f'  no more messages — done')
            break
        # Bulk-delete only works for messages <14 days old; filter
        now_ms = int(time.time() * 1000)
        snowflake_to_ms = lambda s: ((int(s) >> 22) + 1420070400000)
        recent = [m['id'] for m in msgs if (now_ms - snowflake_to_ms(m['id'])) < (14 * 86400 * 1000 - 60_000)]
        older  = [m['id'] for m in msgs if m['id'] not in recent]
        if not recent and not older:
            break
        if recent:
            ok, code, body = bulk_delete(ch_id, recent)
            if ok:
                total_deleted += len(recent)
                print(f'  round {rounds}: bulk-deleted {len(recent)} messages (code {code})')
            else:
                print(f'  round {rounds}: bulk-delete FAILED code={code} body={body[:200]}')
                break
            time.sleep(1.1)  # respect rate limit
        elif older:
            print(f'  round {rounds}: only {len(older)} old (>14d) messages remain — stopping (bulk-delete cannot remove these)')
            break
    print(f'  TOTAL deleted from #{ch}: {total_deleted}')
print('\nPurge done.')
