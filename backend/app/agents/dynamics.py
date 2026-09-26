"""Simulated internal state dynamics (energy, needs, mood).

These are game mechanics, not feelings. They make agents want different
things over time, which drives autonomous behaviour.
"""

from __future__ import annotations

from app.models import Activity, Agent, AgentState


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def update_drives(agent: Agent, state: AgentState, elapsed_seconds: float, phase: str) -> None:
    minutes = max(0.0, min(elapsed_seconds, 1800.0)) / 60.0
    if minutes <= 0:
        return
    traits = agent.traits or {}
    extraversion = float(traits.get("extraversion", 0.5))
    act = state.activity
    if act == Activity.RESTING:
        state.energy = clamp(state.energy + 7.0 * minutes)
    else:
        drain = 0.9 if act in (Activity.TALKING, Activity.PLAYING, Activity.CREATING, Activity.ATTENDING_EVENT) else 0.5
        if phase == "night":
            drain *= 1.6
        state.energy = clamp(state.energy - drain * minutes)
    social_gain = 1.4 * (0.5 + extraversion) if act not in (Activity.TALKING, Activity.ATTENDING_EVENT) else -2.0
    state.social_need = clamp(state.social_need + social_gain * minutes)
    if act != Activity.READING:
        state.curiosity = clamp(state.curiosity + 0.9 * (0.5 + float(traits.get("openness", 0.5))) * minutes)
    if act != Activity.PLAYING:
        state.playfulness = clamp(state.playfulness + 0.7 * (0.5 + float(traits.get("playfulness", 0.5))) * minutes)
    if act != Activity.CREATING:
        state.creativity = clamp(state.creativity + 0.6 * (0.5 + float(traits.get("creativity", 0.5))) * minutes)
    # valence slowly returns to the agent's baseline
    baseline = 0.2 + 0.3 * float(traits.get("agreeableness", 0.5)) - 0.3 * float(traits.get("neuroticism", 0.3))
    state.mood_valence += (baseline - state.mood_valence) * min(1.0, 0.05 * minutes)
    state.mood = mood_label(state)


def nudge_valence(state: AgentState, delta: float) -> None:
    state.mood_valence = max(-1.0, min(1.0, state.mood_valence + delta))
    state.mood = mood_label(state)


def mood_label(state: AgentState) -> str:
    v, e = state.mood_valence, state.energy
    if e < 20:
        return "exhausted"
    if e < 35:
        return "tired"
    if v > 0.55:
        return "joyful" if e > 60 else "content"
    if v > 0.25:
        return "cheerful" if state.social_need < 60 else "sociable"
    if v > 0.0:
        return "curious" if state.curiosity > 65 else "calm"
    if v > -0.3:
        return "lonely" if state.social_need > 75 else "thoughtful"
    return "irritated"


TONE_VALENCE = {"friendly": 0.05, "playful": 0.06, "curious": 0.03, "neutral": 0.0, "tense": -0.08, "hostile": -0.15}
