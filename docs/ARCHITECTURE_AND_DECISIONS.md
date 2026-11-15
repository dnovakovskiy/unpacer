# Unpacer — Architecture Decision Records (`ADR`) & Technical Reference

This document captures the technical discoveries, reverse-engineered Garmin Connect DTO schemas, and physiological/biomechanical heuristics behind `unpacer`.

---

## ADR-001: Reverse-Engineering the Final Surge → Garmin Connect Running Workout Schema
* **Context:** Human coaches using **Final Surge Workout Builder** push structured workouts to Garmin Connect that give on-wrist pace guidance during intervals while leaving warmup (easy jog + dynamic drills + strides) and cooldown open-ended on the `LAP` button.
* **Solution (`scripts/unpacer_cli.py`):**
  1. **Top-Level Metadata:**
     - `workoutName`: Compact shorthand string (e.g., `"4x2km/2min"`, `"3k-2k-1k-3k/1min&3min"`).
     - `description`: Multi-line pre-run coaching brief displayed on the phone/watch before pressing Start (warmup duration, drills link, strides, rep pacing notes, cooldown).
     - `sportType`: `{"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}`.
  2. **Step 1 — Open Warmup (`ExecutableStepDTO`):**
     - `stepType`: `{"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1}`.
     - `endCondition`: `{"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True}`.
     - *Why:* Allows the athlete to finish easy warmup + drills + strides without the watch prematurely starting Rep 1; Rep 1 begins the instant the athlete presses **LAP**.
  3. **Step 2 — Interval Repeat Block (`RepeatGroupDTO`):**
     - `stepType`: `{"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}`, `numberOfIterations: N`, `endCondition.conditionTypeKey: "iterations"` (`conditionTypeId: 7`).
     - **Active Step (`interval`, `stepTypeId: 3`):**
       - `endCondition`: `distance` (`conditionTypeId: 3`, meters) or `time` (`conditionTypeId: 2`, seconds).
       - `targetType`: `pace.zone` (`workoutTargetTypeId: 6`).
       - `targetValueOne`: **Faster pace bound in meters/second (`m/s`)** = `1000.0 / fast_seconds_per_km` (e.g., `3:55/km` = `235s` → `4.2553193 m/s`).
       - `targetValueTwo`: **Slower pace bound in meters/second (`m/s`)** = `1000.0 / slow_seconds_per_km`.
     - **Recovery Step (`rest`, `stepTypeId: 5` or `recovery`, `stepTypeId: 4`):** `time` (`conditionTypeId: 2`) or `distance` (`conditionTypeId: 3`).
  4. **Final Step — Open Cooldown (`ExecutableStepDTO`):**
     - `stepType`: `cooldown` (`stepTypeId: 2`), `endCondition`: `lap.button` (`conditionTypeId: 1`).
  5. **Upload & Scheduling Endpoints (`garminconnect`):**
     - `POST /workout-service/workout` (`api.upload_workout(payload)`) → returns `workoutId`.
     - `POST /workout-service/schedule/{workout_id}` (`api.schedule_workout(workout_id, "YYYY-MM-DD")`) → places the workout on the Garmin Calendar so the watch automatically prompts `"Do Workout"` on that date.

---

## ADR-002: Dynamic Garmin Gauge Screen Injection (Without Overriding Default Watch Layouts)
* **Problem:** When a workout step has `targetType = no.target` (`workoutTargetTypeId: 1`), Garmin Fenix/Forerunner watches render a plain step-timer/distance screen with **no semicircular gauge and no live pace/HR field**.
* **Mechanism:** Structured workouts never overwrite the user's custom `Run` data pages; instead, Garmin OS dynamically inserts a dedicated **Workout Gauge Screen** at the top of the page loop **only for steps that define a `targetType`** (`pace.zone` or `heart.rate.zone`).
* **Solution:**
  1. **Always-On Pace Gauge (`pace.zone`, `workoutTargetTypeId: 6`):**
     - **Warmup Steps:** Attach a non-intrusive easy range (`4:45–5:25/km` = `3.509` to `3.077 m/s`) so the Red/Green/Red Pace Gauge + Live Pace (`min/km`) appears automatically during warmup.
     - **Stride Steps (`20–30s`):** Use `3:30–4:05/km` (`4.762` to `4.082 m/s`)—wide enough to absorb 3–5s of initial GPS acceleration lag while keeping the live gauge active.
  2. **Native HR Zone Gauge (`heart.rate.zone`, `workoutTargetTypeId: 4`, `zoneNumber: 1..5`):**
     - Passing `"zoneNumber": 2` (with `targetValueOne: None, targetValueTwo: None`) switches the Garmin Workout Screen to the **Zone 2 Heart Rate Gauge** tethered to the athlete's configured Garmin Running HR Zones.

---

## ADR-003: Crisp `6–7 sec/km` Single-Regime Pace Bands & Multi-Gear Terrain Race Pacers
* **Discovery:**
  1. Programming `1.00 km` workout steps across a 15K/21.1K race creates 15–21 transition chimes and screen resets.
  2. Programming wide `12–18 sec/km` pace bands (e.g., `3:58–4:12/km`) crosses two completely different metabolic regimes when an athlete's lactate threshold sits around `3:52–4:00/km`.
  3. Across city road races, Garmin GPS measures **`+0.6% to +1.5%` extra distance** from start-corral weaving and course tangents.
* **Standard:**
  - Group race pacers into **5–8 natural terrain macro-blocks** (`2–4 km` where grade is uniform; `1 km` only on isolated steep drops/walls).
  - Keep every step's `pace.zone` band strictly **`6–7 sec/km` wide** so each step corresponds to **one unmistakable physiological gear**.
  - Offset watch target bands **`2–3 sec/km` faster** than target official chip pace (e.g., `3:56–3:57/km` watch GPS pace to hit `<3:58.9/km` / `Sub-1:24:00` chip in a Half Marathon).

---

## ADR-004: Phone-Free Animated Strength Workouts (`sportTypeId: 5`)
* **Problem:** Opening YouTube or phone apps between gym sets to check exercise names, target reps, or form cues breaks focus and demotivates solo open-gym strength sessions.
* **Solution:**
  - Use Garmin's native `strength_training` workout type (`sportTypeId: 5`, `sportTypeKey: "strength_training"`, `displayOrder: 5`).
  - Wrap each exercise in a `RepeatGroupDTO` (`numberOfIterations: sets`) containing an active `interval` step (`endCondition`: `reps` `conditionTypeId: 10`, `weightValue` in `kg` with `unitId: 8, factor: 1000.0`, coaching cue in `description`) and a timed `rest` step (`conditionTypeId: 2`, `45–75s`).
  - Map every exercise to **verified Garmin 3D muscle-animation `category` + `exerciseName` pairs** (note: Garmin's API silently strips unrecognized `exerciseName` strings to `""` while returning HTTP 200—always verify returned `workoutSteps` after upload!):
    - `("CALF_RAISE", "SEATED_DUMBBELL_TOE_RAISE")`
    - `("CALF_RAISE", "SINGLE_LEG_STANDING_DUMBBELL_CALF_RAISE")`
    - `("LUNGE", "DUMBBELL_BULGARIAN_SPLIT_SQUAT")`
    - `("DEADLIFT", "SINGLE_LEG_ROMANIAN_DEADLIFT_WITH_DUMBBELL")`
    - `("DEADLIFT", "STRAIGHT_LEG_DEADLIFT")` *(use instead of `DUMBBELL_ROMANIAN_DEADLIFT`, which Garmin strips)*
    - `("SQUAT", "GOBLET_SQUAT")`
    - `("ROW", "ONE_ARM_BENT_OVER_ROW")`
    - `("SHOULDER_PRESS", "DUMBBELL_SHOULDER_PRESS")`
    - `("PLANK", "SIDE_PLANK")`
    - `("HIP_STABILITY", "DEAD_BUG")` *(use `HIP_STABILITY` category rather than `CORE`, which Garmin strips for `DEAD_BUG`)*

---

## ADR-005: Optical HR Sensor Artifacts vs. Verified Official Chip `VDOT`
* **Finding:** Wrist-only optical HR sensors (`Elevate v4/v5`) exhibit two systematic distortions in runners:
  1. **Race Cadence-Lock Inflation (`+5 to +8 bpm`):** At `180–186 spm` in carbon racing shoes, wrist optical HR can lock onto step cadence (`172–175 avg / 184–187 max`), inflating auto-detected `HRmax`.
  2. **Cool-Weather Easy Run Under-Reading (`-6 to -8 bpm`):** In `<12°C` weather, peripheral wrist vasoconstriction causes optical HR to read `118–128 bpm` during true `135–138 bpm` Zone 2 runs—artificially inflating Firstbeat/Garmin `VO₂max` estimates by `+2 to +3.5 mL/kg/min`.
* **Rule:** Always pair an external optical bicep armband (`Polar Verity Sense / OH1`) or chest strap for HR-zone runs and races, and anchor training paces to **verified official chip `VDOT`** (extracted from official race mat splits / Strava race result screenshots) rather than raw watch `VO₂max`.
