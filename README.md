# NEXUS — Home Intelligence App

A voice-first home assistant app that connects to your self-hosted NEXUS backend API. Speak commands, get AI responses with audio, trigger phone calls, send SMS, and control smart home devices.

Built with HTML/CSS/JS + [Capacitor](https://capacitorjs.com) for native Android packaging.

---

## What It Does

- **Voice input** — tap the orb, speak, audio sent to your server for transcription
- **AI responses** — NEXUS backend processes your request and returns text + optional audio
- **Audio playback** — MP3 audio responses played back in-app
- **Phone commands** — NEXUS can trigger calls (`tel:`), SMS (`sms:`), and URL opens
- **Dual-mode** — voice orb or keyboard text input
- **Auto endpoint** — tries local server first, falls back to external URL

---

## Project Structure

```
nexus-app/
  pwa/               # Web source (HTML/CSS/JS) — edit this
    index.html
    app.js
    style.css
    manifest.json
    sw.js            # Service worker (offline shell)
    config.js        # YOUR config — not in git (see config.example.js)
    config.example.js
    generate-icons.js
    icons/
  capacitor/         # Capacitor Android wrapper
    capacitor.config.json
    package.json
    android/         # Android Studio project — generated, not in git
  expo/              # Original Expo React Native version (reference/archive)
  desktop/           # Electron desktop app
```

---

## Requirements

- **NEXUS backend API** running somewhere accessible:
  - `POST /api/ask` — accepts `{ message }`, returns `{ reply, audio? }`
  - `POST /api/transcribe` — accepts FormData `audio` file, returns `{ transcript }`
  - `POST /api/clear` — resets conversation history
  - `GET  /health` — returns 200 if server is up
- **Node.js 18+** — for Capacitor CLI
- **Android Studio** — for building the Android APK

---

## Setup — PWA (browser)

```bash
# 1. Copy the config template
cp pwa/config.example.js pwa/config.js

# 2. Edit pwa/config.js with your server details

# 3. Open pwa/index.html in Chrome, or serve it:
npx serve pwa
```

---

## Setup — Android APK (Capacitor)

```bash
# 1. Set up config as above

# 2. Install Capacitor dependencies
cd capacitor
npm install

# 3. Add Android platform (first time only)
npx cap add android

# 4. Sync web code into Android project
npx cap sync android

# 5. Open in Android Studio
npx cap open android
```

In Android Studio:
1. Wait for Gradle sync to finish
2. **Build → Build Bundle(s)/APK(s) → Build APK(s)**
3. APK saved to `android/app/build/outputs/apk/debug/app-debug.apk`
4. Transfer to phone → install (enable "Install from unknown sources" in settings)

---

## Config

Copy `pwa/config.example.js` to `pwa/config.js` and set your values:

```js
window.NEXUS_CONFIG = {
  localUrl:    'http://YOUR_SERVER_IP:5000',   // Local network IP of your NEXUS server
  externalUrl: 'https://YOUR_NEXUS_DOMAIN',    // Public HTTPS URL (optional)
};
```

`config.js` is in `.gitignore` and will not be committed.

---

## Capacitor Config

Edit `capacitor/capacitor.config.json`:

```json
{
  "appId": "com.yourname.nexus",
  "appName": "NEXUS",
  "webDir": "../pwa",
  "server": {
    "cleartext": true,
    "allowNavigation": ["YOUR_SERVER_IP", "YOUR_NEXUS_DOMAIN"]
  }
}
```

Change `appId` to your own reverse-domain identifier.

---

## Android Permissions

The app requests these permissions (declared in `AndroidManifest.xml`):

| Permission | Why |
|------------|-----|
| `RECORD_AUDIO` | Voice input |
| `INTERNET` | API calls to NEXUS backend |
| `CALL_PHONE` | When NEXUS triggers a phone call |
| `SEND_SMS` | When NEXUS sends an SMS |
| `VIBRATE` | Haptic feedback on orb tap |
| `MODIFY_AUDIO_SETTINGS` | Audio mode switching |

---

## Phone Commands

NEXUS backend can embed commands in its replies that the app executes:

| Tag | Action |
|----|--------|
| `<<CALL:+441234567890>>` | Opens phone dialler |
| `<<SMS:+441234567890:Hello>>` | Opens SMS composer |
| `<<URL:https://example.com>>` | Opens URL in browser |
| `<<OPEN:spotify://>>` | Opens app by URI scheme |

---

## Building the NEXUS Backend

You'll need to run a compatible backend API. The backend should be a Python Flask server with these endpoints. The specific AI model, home automation integrations, and tools are up to you.

---

## Icon Generation

```bash
cd pwa
npm install sharp --save-dev
node generate-icons.js
# Creates icons/icon-192.png and icons/icon-512.png
```

---

## License

MIT
