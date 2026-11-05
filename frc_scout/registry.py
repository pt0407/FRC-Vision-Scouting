"""Mechanism registry: human-authored per-team CAD/mechanism tags.

Registry lives in data/registry/teams.json:

    {"8749": {"mechanisms": [{"type": "turret_shooter",
                              "params": {"mount": "corner"}},
                             {"type": "climb", "params": {"level": 2}}],
              "cad_url": "...", "robot_name": "...", "notes": "..."}}

Mechanism types with a sim geometry preset are emitted as [[mech]]
tables in archetype TOMLs (frc-multi-sim issue #61 schema). Tag-only
types carry semantic info for strategies/agents but no physics body.
"""
import json
from pathlib import Path

# mechanism type -> sim MechSpec preset (or None = tag only).
# pivot/half_extents are chassis-frame metres (+x forward, +y up).
MECH_PRESETS = {
    "ground_intake": {
        "joint_type": "revolute", "pivot": [0.40, 0.35, 0.0],
        "half_extents": [0.35, 0.03, 0.35], "mass": 4.0,
        "stow_angle": 1.3, "limits": [-0.6, 1.4],
        "motor_stiffness": 300.0, "motor_damping": 30.0,
        "motor_max_force": 400.0},
    "climb_elevator": {
        "joint_type": "prismatic", "pivot": [0.0, 0.30, 0.0],
        "half_extents": [0.05, 0.40, 0.05], "mass": 6.0,
        "stow_angle": 0.0, "limits": [0.0, 1.0],
        "motor_stiffness": 400.0, "motor_damping": 40.0,
        "motor_max_force": 800.0},
    "climb_arm": {
        "joint_type": "revolute", "pivot": [-0.30, 0.35, 0.0],
        "half_extents": [0.45, 0.03, 0.05], "mass": 5.0,
        "stow_angle": 1.5, "limits": [0.0, 1.6],
        "motor_stiffness": 400.0, "motor_damping": 40.0,
        "motor_max_force": 600.0},
    "turret_shooter": {
        "joint_type": "revolute", "pivot": [0.0, 0.45, 0.0],
        "half_extents": [0.10, 0.10, 0.10], "mass": 8.0,
        "stow_angle": 0.0, "limits": [-3.2, 3.2],
        "motor_stiffness": 150.0, "motor_damping": 20.0,
        "motor_max_force": 100.0},
    # tag-only: no rigid body in the sim
    "station_intake": None, "hopper": None, "feeder": None,
    "die_rotor": None, "inline_shooter": None, "over_bumper_intake": None,
    "defense": None,
}

MECH_TYPES = sorted(MECH_PRESETS)


def load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save(path: Path, reg: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, indent=2) + "\n")


def set_mechanisms(path: Path, team: str, mech_specs: list[str],
                   cad_url=None, robot_name=None, notes=None):
    """mech_specs: ["turret_shooter:mount=corner,range_m=4.5", ...]"""
    reg = load(path)
    entry = reg.setdefault(team, {})
    mechs = []
    for spec in mech_specs:
        name, _, kv = spec.partition(":")
        name = name.strip()
        if name not in MECH_PRESETS:
            raise ValueError(
                f"unknown mech type {name!r}; known: {MECH_TYPES}")
        params = {}
        for pair in kv.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                try:
                    params[k.strip()] = float(v)
                except ValueError:
                    params[k.strip()] = v.strip()
        mechs.append({"type": name, "params": params})
    entry["mechanisms"] = mechs
    if cad_url:
        entry["cad_url"] = cad_url
    if robot_name:
        entry["robot_name"] = robot_name
    if notes:
        entry["notes"] = notes
    save(path, reg)
    return entry


def merge_export(path: Path, exported: dict):
    """Merge an exported dict from the review page into the registry."""
    reg = load(path)
    for team, entry in exported.items():
        cur = reg.setdefault(team, {})
        if entry.get("mechanisms"):
            cur["mechanisms"] = entry["mechanisms"]
        for k in ("cad_url", "robot_name", "notes"):
            if entry.get(k):
                cur[k] = entry[k]
    save(path, reg)
    return reg


def _f(v):
    return int(v) if float(v).is_integer() else round(float(v), 3)


def mech_toml_blocks(team: str, reg: dict) -> str:
    """TOML [[mech]] tables for a team's sim-geometry mechanisms."""
    entry = reg.get(str(team)) or {}
    out = []
    for m in entry.get("mechanisms", []):
        preset = MECH_PRESETS.get(m["type"])
        if preset is None:
            continue
        spec = dict(preset)
        # allow param overrides for scalar MechSpec fields
        for k in ("mass", "stow_angle", "motor_stiffness",
                  "motor_damping", "motor_max_force"):
            if k in m.get("params", {}):
                spec[k] = m["params"][k]
        blk = ["[[mech]]",
               f'joint_type = "{spec["joint_type"]}"',
               f"pivot = [{_f(spec['pivot'][0])}, "
               f"{_f(spec['pivot'][1])}, {_f(spec['pivot'][2])}]",
               f"half_extents = [{_f(spec['half_extents'][0])}, "
               f"{_f(spec['half_extents'][1])}, "
               f"{_f(spec['half_extents'][2])}]",
               f"mass = {_f(spec['mass'])}",
               f"stow_angle = {_f(spec['stow_angle'])}",
               f"limits = [{_f(spec['limits'][0])}, "
               f"{_f(spec['limits'][1])}]",
               f"motor_stiffness = {_f(spec['motor_stiffness'])}",
               f"motor_damping = {_f(spec['motor_damping'])}",
               f"motor_max_force = {_f(spec['motor_max_force'])}"]
        out.append("\n".join(blk))
    return "\n\n".join(out) + "\n" if out else ""


def mech_tags(team: str, reg: dict) -> list[str]:
    """All mechanism type names for a team (geometry or tag-only)."""
    entry = reg.get(str(team)) or {}
    return [m["type"] for m in entry.get("mechanisms", [])]
