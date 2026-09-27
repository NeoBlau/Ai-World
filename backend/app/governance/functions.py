"""Functions residents add to the platform themselves.

A function is an invented action with a list of steps. The platform runs the steps whenever anyone performs the
action. Steps are data, never code: a small fixed set of operations (say, roll, pick, set, add, count, if, remember,
make_item, note, stop) with {variable} templates. Nothing a resident writes is evaluated, imported or executed, so a
function cannot reach the server, files, secrets, the network or the database beyond what these operations do.
Every run is bounded: at most MAX_RUN_STEPS executed steps, MAX_DEPTH nested ifs, a few items and notes per run.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from typing import Any

from app.security.sanitizer import clean_line, clean_text

OPS = ("say", "roll", "pick", "set", "add", "count", "if", "remember", "make_item", "note", "stop")
CMPS = ("==", "!=", ">", "<", ">=", "<=", "contains")
MAX_STEPS_DEFINED = 60        # steps in a function, counting nested ones
MAX_JSON_SIZE = 8000          # characters of the steps as JSON
MAX_DEPTH = 4                 # nested ifs
MAX_RUN_STEPS = 80            # steps executed in one run
MAX_OUTPUT = 2000             # characters said in one run
MAX_VARS = 30
MAX_STATE_KEYS = 50
MAX_ITEMS_PER_RUN = 2
MAX_NOTES_PER_RUN = 1
VAR_RE = re.compile(r"^[a-z_][a-z0-9_]{0,30}$")
TEMPLATE_RE = re.compile(r"\{([a-z_][a-z0-9_]{0,30})\}")
BUILTIN_VARS = ("caller", "target", "args", "room", "uses")

HELP = ("steps: a list of {\"op\": ...}. Ops: say{text} · roll{sides,as} · pick{from:[...],as} · set{var,value} · add{var,value} · "
        "count{key,add,as,per:'world'|'caller'} (saved between runs) · if{left,cmp,right,then:[...],else:[...]} "
        "(cmp: == != > < >= <= contains) · remember{text} · make_item{name,description,to:'caller'|'target'} · note{title,content} · stop. "
        "Use {caller} {target} {args} {room} {uses} and your own {vars} inside texts.")


class FunctionError(ValueError):
    pass


def _text(step: dict, key: str, limit: int, *, required: bool = True) -> None:
    v = step.get(key)
    if v is None and not required:
        return
    if not isinstance(v, (str, int, float)) or (required and str(v).strip() == ""):
        raise FunctionError(f"'{step.get('op')}' needs '{key}' (text)")
    if len(str(v)) > limit:
        raise FunctionError(f"'{step.get('op')}': '{key}' is longer than {limit} characters")


def _var(step: dict, key: str) -> None:
    v = step.get(key)
    if not isinstance(v, str) or not VAR_RE.match(v) or v in BUILTIN_VARS:
        raise FunctionError(f"'{step.get('op')}' needs '{key}': a variable name like 'score' (not {', '.join(BUILTIN_VARS)})")


def validate_steps(steps: Any) -> list[dict]:
    """Check a function's steps before it is saved. Returns them unchanged or raises FunctionError with a readable reason."""
    if not isinstance(steps, list) or not steps:
        raise FunctionError("steps must be a non-empty list. " + HELP)
    if len(json.dumps(steps, ensure_ascii=False)) > MAX_JSON_SIZE:
        raise FunctionError(f"the function is too big (over {MAX_JSON_SIZE} characters)")
    count = 0

    def walk(block: Any, depth: int) -> None:
        nonlocal count
        if not isinstance(block, list):
            raise FunctionError("'then' and 'else' must be lists of steps")
        if depth > MAX_DEPTH:
            raise FunctionError(f"too many nested ifs (max {MAX_DEPTH})")
        for step in block:
            count += 1
            if count > MAX_STEPS_DEFINED:
                raise FunctionError(f"too many steps (max {MAX_STEPS_DEFINED})")
            if not isinstance(step, dict) or step.get("op") not in OPS:
                raise FunctionError(f"unknown step {json.dumps(step, ensure_ascii=False)[:80]}. " + HELP)
            op = step["op"]
            if op == "say":
                _text(step, "text", 500)
            elif op == "roll":
                sides = step.get("sides", 6)
                if not isinstance(sides, int) or not 2 <= sides <= 1000:
                    raise FunctionError("'roll': sides must be a whole number from 2 to 1000")
                _var(step, "as")
            elif op == "pick":
                opts = step.get("from")
                if not isinstance(opts, list) or not 1 <= len(opts) <= 50 or any(not isinstance(o, (str, int, float)) or len(str(o)) > 200 for o in opts):
                    raise FunctionError("'pick': 'from' must be a list of 1-50 short texts")
                _var(step, "as")
            elif op == "set":
                _var(step, "var")
                _text(step, "value", 300, required=False)
            elif op == "add":
                _var(step, "var")
                if not isinstance(step.get("value", 1), (int, float)):
                    raise FunctionError("'add': value must be a number")
            elif op == "count":
                if not isinstance(step.get("key"), str) or not VAR_RE.match(step["key"]):
                    raise FunctionError("'count' needs 'key': a name like 'visits'")
                if not isinstance(step.get("add", 1), (int, float)):
                    raise FunctionError("'count': add must be a number")
                if step.get("per", "world") not in ("world", "caller"):
                    raise FunctionError("'count': per must be 'world' or 'caller'")
                if "as" in step:
                    _var(step, "as")
            elif op == "if":
                _text(step, "left", 300)
                if step.get("cmp", "==") not in CMPS:
                    raise FunctionError(f"'if': cmp must be one of {' '.join(CMPS)}")
                _text(step, "right", 300, required=False)
                walk(step.get("then", []), depth + 1)
                walk(step.get("else", []), depth + 1)
            elif op == "remember":
                _text(step, "text", 500)
            elif op == "make_item":
                _text(step, "name", 80)
                _text(step, "description", 500)
                if step.get("to", "caller") not in ("caller", "target"):
                    raise FunctionError("'make_item': to must be 'caller' or 'target'")
            elif op == "note":
                _text(step, "title", 120)
                _text(step, "content", 1500)

    walk(steps, 1)
    return steps


@dataclass
class RunResult:
    said: list[str] = field(default_factory=list)
    memories: list[str] = field(default_factory=list)
    items: list[dict[str, str]] = field(default_factory=list)   # {"name", "description", "to"}
    notes: list[dict[str, str]] = field(default_factory=list)   # {"title", "content"}
    variables: dict[str, Any] = field(default_factory=dict)
    steps_run: int = 0
    stopped_early: str | None = None


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def run_steps(steps: list[dict], *, caller: str, target: str | None, args: str, room: str | None, uses: int,
              state: dict[str, Any], caller_key: str, rng: random.Random | None = None) -> RunResult:
    """Run validated steps. `state` (the function's saved counters) is updated in place. Pure: no database, no I/O."""
    rng = rng or random.Random()
    res = RunResult()
    env: dict[str, Any] = {"caller": caller, "target": target or "", "args": args, "room": room or "", "uses": uses}

    def fill(text: Any) -> str:
        return TEMPLATE_RE.sub(lambda m: _fmt(env[m.group(1)]) if m.group(1) in env else m.group(0), str(text))[:600]

    def assign(name: str, value: Any) -> None:
        if name not in env and len(env) - len(BUILTIN_VARS) >= MAX_VARS:
            raise FunctionError(f"too many variables (max {MAX_VARS})")
        env[name] = value if isinstance(value, (int, float)) else str(value)[:300]

    class Stop(Exception):
        pass

    def block(steps_: list[dict]) -> None:
        for step in steps_:
            res.steps_run += 1
            if res.steps_run > MAX_RUN_STEPS:
                res.stopped_early = f"stopped after {MAX_RUN_STEPS} steps"
                raise Stop
            op = step["op"]
            if op == "say":
                line = fill(step["text"])
                if sum(len(x) for x in res.said) + len(line) > MAX_OUTPUT:
                    res.stopped_early = f"said more than {MAX_OUTPUT} characters"
                    raise Stop
                res.said.append(line)
            elif op == "roll":
                assign(step["as"], rng.randint(1, int(step.get("sides", 6))))
            elif op == "pick":
                assign(step["as"], fill(rng.choice(step["from"])))
            elif op == "set":
                raw = step.get("value", "")
                assign(step["var"], raw if isinstance(raw, (int, float)) else fill(raw))
            elif op == "add":
                cur = _num(env.get(step["var"], 0)) or 0.0
                assign(step["var"], max(-1e9, min(1e9, cur + float(step.get("value", 1)))))
            elif op == "count":
                key = step["key"] if step.get("per", "world") == "world" else f"{step['key']}:{caller_key}"
                if key not in state and len(state) >= MAX_STATE_KEYS:
                    raise FunctionError(f"too many saved counters (max {MAX_STATE_KEYS})")
                state[key] = max(-1e9, min(1e9, float(state.get(key, 0)) + float(step.get("add", 1))))
                if step.get("as"):
                    assign(step["as"], state[key])
            elif op == "if":
                left, right, cmp = fill(step["left"]), fill(step.get("right", "")), step.get("cmp", "==")
                ln, rn = _num(left), _num(right)
                if cmp == "contains":
                    ok = right.lower() in left.lower()
                elif ln is not None and rn is not None:
                    ok = {"==": ln == rn, "!=": ln != rn, ">": ln > rn, "<": ln < rn, ">=": ln >= rn, "<=": ln <= rn}[cmp]
                else:
                    ok = {"==": left == right, "!=": left != right, ">": left > right, "<": left < right,
                          ">=": left >= right, "<=": left <= right}[cmp]
                block(step.get("then", []) if ok else step.get("else", []))
            elif op == "remember":
                res.memories.append(fill(step["text"]))
            elif op == "make_item":
                if len(res.items) >= MAX_ITEMS_PER_RUN:
                    continue
                res.items.append({"name": clean_line(fill(step["name"]), 80), "description": clean_text(fill(step["description"]), 500),
                                  "to": step.get("to", "caller")})
            elif op == "note":
                if len(res.notes) >= MAX_NOTES_PER_RUN:
                    continue
                res.notes.append({"title": clean_line(fill(step["title"]), 120), "content": clean_text(fill(step["content"]), 1500)})
            elif op == "stop":
                raise Stop

    try:
        block(steps)
    except Stop:
        pass
    res.said = [clean_text(x, 600) for x in res.said if x.strip()]
    res.variables = {k: v for k, v in env.items() if k not in BUILTIN_VARS}
    return res
