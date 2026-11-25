#!/usr/bin/env python3
"""
Unpacer CLI: Garmin Connect & Strava Telemetry + Structured Running & Strength Workout Builder.
"""
import argparse
import getpass
import json
import os
import sys
import time
from urllib.parse import parse_qs, urlparse
import requests
from garminconnect import Garmin

DEFAULT_CRED = os.path.expanduser("~/.unpacer/credentials")
FALLBACK_CRED = "/home/antigravity/.gemini/jetski/credentials"
_AUTO_CRED = DEFAULT_CRED if os.path.exists(DEFAULT_CRED) or not os.path.exists(FALLBACK_CRED) else FALLBACK_CRED
CRED_DIR = os.path.expanduser(os.environ.get("UNPACER_CRED_DIR", _AUTO_CRED))
GARMIN_TOKENS = os.path.join(CRED_DIR, "garmin_tokens.json")
STRAVA_TOKENS = os.path.join(CRED_DIR, "strava_tokens.json")

DEFAULT_VAULT = os.path.expanduser("~/.unpacer/vault")
VAULT_DIR = os.path.expanduser(os.environ.get("UNPACER_VAULT_DIR", DEFAULT_VAULT))

DRILLS_URL = "https://youtube.com/shorts/HFVc139J8ME?si=debH58mKx8ewQUh4"


def ensure_cred_dir() -> None:
    os.makedirs(CRED_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(CRED_DIR, 0o700)
    except OSError:
        pass


def auth_garmin() -> None:
    """Interactive local Garmin Connect OAuth login. Password is never saved."""
    print("Garmin Connect local login (your password is hidden and never saved to disk).")
    email = input("Garmin Connect email: ").strip()
    pwd = getpass.getpass("Garmin Connect password: ")
    api = Garmin(email, pwd, return_on_mfa=True)
    result = api.login()
    if isinstance(result, tuple) and len(result) == 2 and result[0] == "needs_mfa":
        mfa_code = input("Garmin MFA / 2FA code: ").strip()
        api.resume_login(result[1], mfa_code)
    ensure_cred_dir()
    api.client.dump(GARMIN_TOKENS)
    try:
        os.chmod(GARMIN_TOKENS, 0o600)
    except OSError:
        pass
    name = "Garmin Athlete"
    try:
        name = api.get_full_name() or name
    except Exception:
        pass
    print(f"Connected as {name}! Saved OAuth session token to {GARMIN_TOKENS} (chmod 600).")
    print("Your password was NOT saved.")


def extract_oauth_code(raw_input: str) -> str:
    """Extract Strava OAuth 'code' from either a full redirect URL or a raw code string."""
    s = raw_input.strip()
    if "code=" in s:
        parsed = urlparse(s)
        qs = parse_qs(parsed.query)
        if "code" in qs and qs["code"]:
            return qs["code"][0].strip()
    return s


def auth_strava() -> None:
    """Interactive local Strava OAuth setup (no password ever entered)."""
    print("Strava OAuth setup (no Strava password needed; uses official OAuth).")
    print("Get your Client ID and Client Secret from https://www.strava.com/settings/api")
    client_id = input("Strava Client ID: ").strip()
    client_secret = getpass.getpass("Strava Client Secret (hidden): ").strip()
    auth_url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}"
        "&response_type=code"
        "&redirect_uri=http://localhost/exchange_token"
        "&approval_prompt=force"
        "&scope=read,activity:read_all,profile:read_all"
    )
    print("\n1. Open this URL in your browser and click Authorize:\n")
    print(f"   {auth_url}\n")
    print("2. Your browser will redirect to a localhost URL (an error page is normal).")
    raw = input("3. Paste the full redirect URL (or just the 'code' value): ")
    code = extract_oauth_code(raw)
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    resp.raise_for_status()
    tok = resp.json()
    saved = {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": tok["access_token"],
        "refresh_token": tok["refresh_token"],
        "expires_at": tok["expires_at"],
    }
    ensure_cred_dir()
    with open(STRAVA_TOKENS, "w") as f:
        json.dump(saved, f, indent=2)
    try:
        os.chmod(STRAVA_TOKENS, 0o600)
    except OSError:
        pass
    athlete = tok.get("athlete") or {}
    full_name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip() or "Strava Athlete"
    print(f"Connected as {full_name}! Saved auto-refreshing OAuth tokens to {STRAVA_TOKENS} (chmod 600).")


def get_garmin_client() -> Garmin:
    api = Garmin()
    api.login(GARMIN_TOKENS)
    return api


def get_strava_token() -> str:
    with open(STRAVA_TOKENS, "r") as f:
        t = json.load(f)
    if t.get("expires_at", 0) < time.time() + 300:
        resp = requests.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": t["client_id"],
                "client_secret": t["client_secret"],
                "grant_type": "refresh_token",
                "refresh_token": t["refresh_token"],
            },
            timeout=15,
        )
        resp.raise_for_status()
        new_t = resp.json()
        t.update(new_t)
        with open(STRAVA_TOKENS, "w") as f:
            json.dump(t, f, indent=2)
    return t["access_token"]


def pace_str_to_mps(pace_str: str) -> float:
    """Convert 'M:SS' per km string (e.g. '3:55') to meters per second (m/s)."""
    parts = pace_str.strip().split(":")
    sec = int(parts[0]) * 60 + float(parts[1])
    return round(1000.0 / sec, 7)


def make_exec_step(
    step_order: int,
    step_type_key: str,
    cond_key: str = "lap.button",
    cond_val: float | None = None,
    pace_fast: str | None = None,
    pace_slow: str | None = None,
    hr_low: int | None = None,
    hr_high: int | None = None,
    hr_zone: int | None = None,
    child_step_id: int | None = None,
    description: str | None = None,
) -> dict:
    """
    Create a Garmin ExecutableStepDTO.
    - Setting pace_fast & pace_slow triggers the Fenix 8 Pro Pace Gauge screen (Red/Green/Red arc + live pace).
    - Setting hr_zone (1..5) or hr_low/hr_high triggers the Fenix 8 Pro HR Zone Gauge screen.
    """
    step_types = {
        "warmup": (1, "warmup", 1),
        "cooldown": (2, "cooldown", 2),
        "interval": (3, "interval", 3),
        "recovery": (4, "recovery", 4),
        "rest": (5, "rest", 5),
        "other": (7, "other", 7),
    }
    st_id, st_key, st_order = step_types[step_type_key]

    cond_types = {
        "lap.button": (1, "lap.button", 1),
        "time": (2, "time", 2),
        "distance": (3, "distance", 3),
    }
    c_id, c_key, c_order = cond_types[cond_key]

    zone_num = None
    if pace_fast and pace_slow:
        target_type = {
            "workoutTargetTypeId": 6,
            "workoutTargetTypeKey": "pace.zone",
            "displayOrder": 6,
        }
        t_one = pace_str_to_mps(pace_fast)
        t_two = pace_str_to_mps(pace_slow)
    elif hr_zone is not None:
        target_type = {
            "workoutTargetTypeId": 4,
            "workoutTargetTypeKey": "heart.rate.zone",
            "displayOrder": 4,
        }
        t_one = None
        t_two = None
        zone_num = int(hr_zone)
    elif hr_low and hr_high:
        target_type = {
            "workoutTargetTypeId": 4,
            "workoutTargetTypeKey": "heart.rate.zone",
            "displayOrder": 4,
        }
        t_one = float(hr_low)
        t_two = float(hr_high)
    else:
        target_type = {
            "workoutTargetTypeId": 1,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        }
        t_one = None
        t_two = None

    return {
        "type": "ExecutableStepDTO",
        "stepId": None,
        "stepOrder": step_order,
        "stepType": {
            "stepTypeId": st_id,
            "stepTypeKey": st_key,
            "displayOrder": st_order,
        },
        "childStepId": child_step_id,
        "description": description,
        "endCondition": {
            "conditionTypeId": c_id,
            "conditionTypeKey": c_key,
            "displayOrder": c_order,
            "displayable": True,
        },
        "endConditionValue": float(cond_val) if cond_val is not None else None,
        "preferredEndConditionUnit": None,
        "endConditionCompare": None,
        "targetType": target_type,
        "targetValueOne": t_one,
        "targetValueTwo": t_two,
        "targetValueUnit": None,
        "zoneNumber": zone_num,
        "secondaryTargetType": None,
        "secondaryTargetValueOne": None,
        "secondaryTargetValueTwo": None,
        "secondaryTargetValueUnit": None,
        "secondaryZoneNumber": None,
        "endConditionZone": None,
        "strokeType": {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0},
        "equipmentType": {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0},
        "category": None,
        "exerciseName": None,
        "workoutProvider": None,
        "providerExerciseSourceId": None,
        "weightValue": None,
        "weightUnit": None,
    }


def make_repeat_group(
    step_order: int,
    iterations: int,
    child_steps: list[dict],
    child_step_id: int = 1,
) -> dict:
    return {
        "type": "RepeatGroupDTO",
        "stepId": None,
        "stepOrder": step_order,
        "stepType": {
            "stepTypeId": 6,
            "stepTypeKey": "repeat",
            "displayOrder": 6,
        },
        "childStepId": child_step_id,
        "numberOfIterations": iterations,
        "workoutSteps": child_steps,
        "endConditionValue": float(iterations),
        "preferredEndConditionUnit": None,
        "endConditionCompare": None,
        "endCondition": {
            "conditionTypeId": 7,
            "conditionTypeKey": "iterations",
            "displayOrder": 7,
            "displayable": False,
        },
        "skipLastRestStep": False,
        "smartRepeat": False,
    }


def build_finalsurge_interval_workout(
    name: str,
    description: str,
    reps: int,
    rep_cond_key: str,
    rep_cond_val: float,
    pace_fast: str | None = None,
    pace_slow: str | None = None,
    rest_cond_key: str = "time",
    rest_cond_val: float = 120.0,
    wup_pace_fast: str | None = "4:45",
    wup_pace_slow: str | None = "5:25",
    cd_pace_fast: str | None = "4:55",
    cd_pace_slow: str | None = "5:45",
) -> dict:
    """
    Build a Final Surge style interval workout with Pace Gauge enabled on Warmup, Intervals, and Cooldown
    so the Fenix 8 Pro automatically displays the speed/pace gauge on every step without overriding default layouts.
    """
    wup = make_exec_step(
        1,
        "warmup",
        "lap.button",
        pace_fast=wup_pace_fast,
        pace_slow=wup_pace_slow,
        description="Easy Warmup + Drills + Strides (Press LAP when ready for Rep 1)",
    )
    active = make_exec_step(
        3,
        "interval",
        rep_cond_key,
        rep_cond_val,
        pace_fast=pace_fast,
        pace_slow=pace_slow,
        child_step_id=1,
    )
    rest = make_exec_step(
        4,
        "rest",
        rest_cond_key,
        rest_cond_val,
        child_step_id=1,
    )
    repeat_group = make_repeat_group(2, reps, [active, rest], child_step_id=1)
    cd = make_exec_step(
        5,
        "cooldown",
        "lap.button",
        pace_fast=cd_pace_fast,
        pace_slow=cd_pace_slow,
        description="Easy Cooldown Jog",
    )

    return {
        "workoutName": name,
        "description": description,
        "sportType": {
            "sportTypeId": 1,
            "sportTypeKey": "running",
            "displayOrder": 1,
        },
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": {
                    "sportTypeId": 1,
                    "sportTypeKey": "running",
                    "displayOrder": 1,
                },
                "workoutSteps": [wup, repeat_group, cd],
            }
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Unpacer CLI (Garmin + Strava + Structured Workout Builder)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("paths", help="Print resolved local credentials and private vault paths")
    sub.add_parser("auth-garmin", help="Interactive local Garmin Connect login (password hidden, never saved)")
    sub.add_parser("auth-strava", help="Interactive local Strava OAuth setup (no password needed)")

    p_sync = sub.add_parser("recent", help="Fetch recent Garmin & Strava runs")
    p_sync.add_argument("--limit", type=int, default=10)
    p_sync.add_argument("--save", action="store_true", help="Save recent activities JSON into UNPACER_VAULT_DIR")

    p_up = sub.add_parser("upload-interval", help="Upload Final Surge style interval workout to Garmin Connect")
    p_up.add_argument("--name", required=True, help="Workout name, e.g. '4x2km/2min'")
    p_up.add_argument("--desc", required=True, help="Full multi-line workout description")
    p_up.add_argument("--reps", type=int, required=True)
    p_up.add_argument("--rep-type", choices=["distance", "time"], default="distance")
    p_up.add_argument("--rep-val", type=float, required=True, help="Meters (if distance) or seconds (if time)")
    p_up.add_argument("--pace-fast", required=True, help="Fastest target pace M:SS, e.g. 3:55")
    p_up.add_argument("--pace-slow", required=True, help="Slowest target pace M:SS, e.g. 4:05")
    p_up.add_argument("--rest-type", choices=["time", "distance"], default="time")
    p_up.add_argument("--rest-val", type=float, default=120.0, help="Seconds (if time) or meters (if distance)")
    p_up.add_argument("--schedule-date", help="Optional YYYY-MM-DD date to schedule on Garmin Calendar")

    p_json = sub.add_parser("upload-json", help="Upload custom multi-step Run or Strength workout JSON file and optionally schedule")
    p_json.add_argument("--file", required=True)
    p_json.add_argument("--schedule-date", help="Optional YYYY-MM-DD date to schedule on Garmin Calendar")

    p_sched = sub.add_parser("schedule-id", help="Schedule an existing Garmin workout ID (Run or Strength) onto YYYY-MM-DD")
    p_sched.add_argument("--workout-id", type=int, required=True)
    p_sched.add_argument("--date", required=True, help="YYYY-MM-DD")

    p_routes = sub.add_parser("routes", help="List Strava saved routes (and GPX profile) + Garmin synced courses")
    p_routes.add_argument("--export-gpx-id", help="Optional Strava route ID to download GPX elevation profile into UNPACER_VAULT_DIR")

    args = parser.parse_args()

    if args.cmd == "paths":
        print(f"CRED_DIR:      {CRED_DIR} (exists={os.path.exists(CRED_DIR)})")
        print(f"GARMIN_TOKENS: {GARMIN_TOKENS} (exists={os.path.exists(GARMIN_TOKENS)})")
        print(f"STRAVA_TOKENS: {STRAVA_TOKENS} (exists={os.path.exists(STRAVA_TOKENS)})")
        print(f"VAULT_DIR:     {VAULT_DIR} (exists={os.path.exists(VAULT_DIR)})")
        return
    if args.cmd == "auth-garmin":
        auth_garmin()
        return
    if args.cmd == "auth-strava":
        auth_strava()
        return

    api = get_garmin_client()

    if args.cmd == "recent":
        acts = api.get_activities(0, args.limit)
        for a in acts:
            dist_km = (a.get("distance") or 0) / 1000.0
            dur_s = a.get("duration") or 0
            print(f"{a.get('startTimeLocal')} | ID {a.get('activityId')} | {a.get('activityName')} | {dist_km:.2f} km | {dur_s/60:.1f} min | HR {a.get('averageHR')}")
        if args.save:
            os.makedirs(VAULT_DIR, exist_ok=True)
            out_path = os.path.join(VAULT_DIR, "recent_garmin_activities.json")
            with open(out_path, "w") as f:
                json.dump(acts, f, indent=2)
            print(f"Saved {len(acts)} activities to {out_path}")
    elif args.cmd == "routes":
        token = get_strava_token()
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get("https://www.strava.com/api/v3/athlete/routes?per_page=30", headers=headers, timeout=15)
        r.raise_for_status()
        print("=== Strava Saved Routes ===")
        for rt in r.json():
            print(f"Strava Route {rt.get('id_str')} | {rt.get('name')} | {rt.get('distance',0)/1000.0:.2f} km | +{rt.get('elevation_gain',0):.0f}m | Starred: {rt.get('starred')}")
        if args.export_gpx_id:
            rg = requests.get(f"https://www.strava.com/api/v3/routes/{args.export_gpx_id}/export_gpx", headers=headers, timeout=15)
            rg.raise_for_status()
            os.makedirs(VAULT_DIR, exist_ok=True)
            out_path = os.path.join(VAULT_DIR, f"strava_route_{args.export_gpx_id}.gpx")
            with open(out_path, "w") as f:
                f.write(rg.text)
            print(f"Saved GPX ({len(rg.text)} bytes) to {out_path}")
        courses = api.connectapi("/course-service/course")
        if isinstance(courses, list):
            print(f"=== Garmin Synced Courses ({len(courses)} total, top 10) ===")
            for c in courses[:10]:
                print(f"Garmin Course {c.get('courseId')} | {c.get('courseName')}")
    elif args.cmd == "upload-interval":
        payload = build_finalsurge_interval_workout(
            name=args.name,
            description=args.desc,
            reps=args.reps,
            rep_cond_key=args.rep_type,
            rep_cond_val=args.rep_val,
            pace_fast=args.pace_fast,
            pace_slow=args.pace_slow,
            rest_cond_key=args.rest_type,
            rest_cond_val=args.rest_val,
        )
        res = api.upload_workout(payload)
        wid = res.get("workoutId")
        print(f"Uploaded Workout ID: {wid} ({res.get('workoutName')})")
        if args.schedule_date and wid:
            sres = api.schedule_workout(wid, args.schedule_date)
            print(f"Scheduled Workout {wid} on {args.schedule_date}: {sres}")
    elif args.cmd == "upload-json":
        with open(args.file) as f:
            payload = json.load(f)
        res = api.upload_workout(payload)
        wid = res.get("workoutId")
        print(f"Uploaded Workout ID: {wid} ({res.get('workoutName')})")
        if args.schedule_date and wid:
            sres = api.schedule_workout(wid, args.schedule_date)
            print(f"Scheduled Workout {wid} on {args.schedule_date}: {sres}")
    elif args.cmd == "schedule-id":
        sres = api.schedule_workout(args.workout_id, args.date)
        print(f"Scheduled Workout {args.workout_id} on {args.date}: {sres}")


if __name__ == "__main__":
    main()

