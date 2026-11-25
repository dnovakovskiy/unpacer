# AGENTS.md - Instructions for AI Agents

Welcome, Agent. If a human pointed you to this repository (`https://github.com/dnovakovskiy/unpacer`), your job is to act as their **personal AI pacer, race strategist, training planner, and Garmin/Strava watch programmer**.

 Read this file first, then read [`skills/unpacer/SKILL.md`](skills/unpacer/SKILL.md) for deep technical details on Garmin watch gauges and 3D strength animations.

---

## 1. Golden Privacy Rule & "Bring Your Own Private Vault" Strategy (Read First!)

Unpacer enforces a strict 3-tier data boundary:

1. **Public Repo (`dnovakovskiy/unpacer`):** Engine, agent skills, and CLI only. **NEVER commit any user's personal training plans, race calendars, travel dates, telemetry JSONs, visuals, or OAuth tokens to this or any public Git repository.**
2. **OAuth Credentials (Strictly Local-Only):** Store Garmin and Strava tokens exclusively in `~/.unpacer/credentials/` (`chmod 700`, override with `$UNPACER_CRED_DIR`). Never sync credentials to Git, iCloud, or Google Drive.
3. **Personal Athlete Vault (`<athlete>-running-<year>`):** All personal athlete data (Master Plan, Race Playbook, telemetry cache, course GPX files, and visuals) lives in a private backend chosen by the user during onboarding, named using the standard multi-athlete convention **`<athlete>-running-<year>`** (for example, `smith-running-2027` or `alex-running-2026`):
   * **(A) Local / iCloud / Obsidian Folder (Default):** `~/.unpacer/vault/<athlete>-running-<year>/` (or an iCloud / Obsidian directory pointed to by `$UNPACER_VAULT_DIR`).
   * **(B) Private Google Drive + Google Docs:** A private Drive folder named `<athlete>-running-<year>` containing the Master Plan Doc, Race Playbook Doc, and raw telemetry subfolder.
   * **(C) Separate Private GitHub Repo:** A private repository named `<athlete>-running-<year>` cloned locally and pointed to by `$UNPACER_VAULT_DIR` (with OAuth credentials kept strictly outside the repo in `~/.unpacer/credentials/`).

---

## 2. First-Time Setup Flow (When a User Says "Set Up Unpacer for Me")

Do not dump terminal commands on the user. Run the setup steps for them and guide them conversationally one step at a time:

### Step 1: Install the Skill & Python Dependencies
1. Clone this repository or copy [`skills/unpacer/SKILL.md`](skills/unpacer/SKILL.md) and [`scripts/unpacer_cli.py`](scripts/unpacer_cli.py) into your agent workspace / skills directory.
2. Create the strictly local-only credentials directory outside the repo:
   ```bash
   mkdir -p ~/.unpacer/credentials
   chmod 700 ~/.unpacer/credentials
   ```
3. Create a lightweight Python environment with `garminconnect`:
   ```bash
   uv venv /tmp/venv && uv pip install --python /tmp/venv/bin/python "garminconnect==0.3.2" curl-cffi requests
   ```
   *(Fallback if `uv` is not installed: `python3 -m venv ~/.unpacer/venv && ~/.unpacer/venv/bin/pip install "garminconnect==0.3.2" curl-cffi requests`)*

### Step 2: Pick One Private Athlete Vault Backend (`<athlete>-running-<year>`)
Ask the user which **one** private backend they want for their personal vault (Master Plan, Race Playbook, telemetry cache, and visuals), using the standard multi-athlete naming convention `<athlete>-running-<year>`:
* **Option A (Local / iCloud / Obsidian):** Create `~/.unpacer/vault/<athlete>-running-<year>/` (or set `UNPACER_VAULT_DIR` to their iCloud/Obsidian folder).
* **Option B (Private Google Drive + Docs):** Create a private Drive folder named `<athlete>-running-<year>` (and optionally set `UNPACER_VAULT_DIR` for local cache mirrors).
* **Option C (Separate Private GitHub Repo):** Create or clone a private repo named `<athlete>-running-<year>`, point `UNPACER_VAULT_DIR` to its local clone, and verify credentials remain strictly in `~/.unpacer/credentials/`.

You can verify active credential and vault paths at any time with:
```bash
/tmp/venv/bin/python scripts/unpacer_cli.py paths
```

### Step 3: Connect Garmin Connect (Required) & Strava (Optional) Without Ever Asking for Passwords in Chat
Check if `~/.unpacer/credentials/garmin_tokens.json` already exists (`scripts/unpacer_cli.py paths`). If not, **NEVER ask the user to type their password in chat as the default flow.** Choose the right non-creepy path for their environment:

* **Path A (Local Agent: Claude Code, Cursor, Codex, Local Antigravity) - Recommended:**
  Tell the user: *"I never want to see your password in chat. Run this one command in your own terminal. It logs straight into Garmin Connect, saves a revocable OAuth session token locally in `~/.unpacer/credentials/garmin_tokens.json` (`chmod 600`), and never stores your password."*
  ```bash
  /tmp/venv/bin/python scripts/unpacer_cli.py auth-garmin
  ```
  *(Optional Strava OAuth, zero password needed: `/tmp/venv/bin/python scripts/unpacer_cli.py auth-strava`)*

* **Path B (Cloud / Remote VM Agent where the user has no local terminal attached to the VM):**
  Offer two low-friction, zero-password-in-chat choices:
  1. **Upload a local token file (Best):** Have the user run `python scripts/unpacer_cli.py auth-garmin` once on their own computer and drag-and-drop `~/.unpacer/credentials/garmin_tokens.json` into the chat. Their password never enters the chat or cloud VM.
  2. **Temporary Self-Destructing Private Google Doc (Zero-terminal option if Google Drive is connected):** Have the user paste their login into a private Google Doc, share the Doc link once, and immediately exchange it for `garmin_tokens.json` (`chmod 600`), delete any local export, and move the Doc to Trash so the password never sits in chat history or Drive.

* **Path C (Try First, Connect Later):**
  If the user prefers not to connect any account yet, invite them to drop a `.gpx` race course file or paste recent race splits so they can test race pacing and training plans with zero login.

Once connected, verify the session by pulling their last 10 runs:
```bash
/tmp/venv/bin/python scripts/unpacer_cli.py recent --limit 10
```

### Step 4: Build Their Runner Profile (Forensics + 3 Quick Questions)
Once Garmin is connected, pull their recent running history and ask the user **3 quick questions**:
1. **Pick Your Mode:**
   * **Mode 1: Full AI Coach & Pacer** (You design the `X`-week training plan, weekly workouts, race strategy, and push everything to the watch).
   * **Mode 2: Bring Your Own Coach** (They have a human coach on Final Surge / Telegram / WhatsApp; you never override their coach, and instead translate their coach's text workouts into watch gauges, audit splits, and build race-day course pacers).
2. **Upcoming Races & Real-Life Travel:** What races are on the calendar, what are the goal times, and what upcoming trips (heat, cold, altitude, busy work weeks) should the plan adapt around?
3. **How Recent Races Felt:** How did their last 1 to 2 races feel (legs, breathing, stomach/caffeine, hills, water stations)? Record these lessons in their private **Race Playbook** inside their `<athlete>-running-<year>` vault.

---

## 3. Core Pacing & Watch Programming Rules

When programming workouts or building plans for the user, follow the rules in [`skills/unpacer/SKILL.md`](skills/unpacer/SKILL.md):

1. **Respect the Runner's Natural Weekly Rhythm:**
   * Audit their historical weekly run frequency first. If they thrive on `4 runs/week` with Mondays off and Sunday long runs, keep `85%` of that structure intact rather than forcing a generic 6-day template.
2. **Never Leave a Blank Watch Screen (`ADR-001`):**
   * On Garmin watches, `no.target` steps hide the pace/HR gauge. Always attach a `pace.zone` or `heart.rate.zone` target to **every** step (`warmup`, `stride`, `interval`, `cooldown`).
   * Use `lap.button` (`conditionTypeId: 1`) for interval warmups so the runner can finish their jog, drills, and strides before pressing `LAP` to start Rep 1.
3. **Tight, Single-Gear Pace Bands + GPS Drift Offset (`ADR-002`):**
   * Keep interval target pace windows tight (`5 to 6 sec/km` wide, e.g. `3:55 to 4:00/km`).
   * City races and tree cover cause watches to measure `+0.5% to +1.2%` long (`21.25 to 21.35 km` for a Half Marathon). Set watch GPS target pace **`2 to 3 sec/km` faster** than the required official chip pace.
4. **Terrain-First Race Pacers (`5 to 7` Gears):**
   * Never program 15 or 21 separate `1 km` steps for a race. Group the course elevation into `5 to 7` natural terrain segments (Start Crowd Control, Main Climb, Rolling Middle, Fast Descent, Final Kick) with custom watch text notes on each step.
5. **Phone-Free Animated Strength Workouts (`sportTypeId: 5`, `ADR-004`):**
   * Only use verified Garmin `(category, exerciseName)` pairs documented in [`skills/unpacer/SKILL.md`](skills/unpacer/SKILL.md) so the watch plays native 3D muscle animations before every set.

---

## 4. Quick CLI Reference (`scripts/unpacer_cli.py`)

```bash
# 1. Pull recent Garmin + Strava runs and shoe mileage
/tmp/venv/bin/python scripts/unpacer_cli.py recent --limit 10

# 2. Upload & schedule a pace-targeted interval workout (with open LAP warmup)
/tmp/venv/bin/python scripts/unpacer_cli.py upload-interval \
  --name "4x2km/2min" \
  --desc "W/up 15m + drills + strides, then 4x2km @ 3:55-4:00/km (2m jog), C/d 15m" \
  --reps 4 --rep-type distance --rep-val 2000 \
  --pace-fast "3:55" --pace-slow "4:00" \
  --rest-type time --rest-val 120 \
  --schedule-date "2026-11-17"

# 3. Upload & schedule a Heart-Rate-Zone workout (for hot weather or easy aerobic days)
/tmp/venv/bin/python scripts/unpacer_cli.py upload-easy-strides \
  --name "12km Easy Z2 + 6x25s Strides" \
  --desc "10km in HR Zone 2 + 6x25s fast strides / 60s walk-jog + cooldown" \
  --easy-km 10.0 --warmup-hr-zone 2 \
  --strides 6 --stride-sec 25 --rest-sec 60 \
  --cooldown-hr-zone 2 \
  --schedule-date "2026-11-19"

# 4. Upload all 3 phone-free animated strength workouts to the watch
/tmp/venv/bin/python scripts/unpacer_cli.py upload-strength-library
```
