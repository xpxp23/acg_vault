import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
base = 'E:/ACG/魔法少女るなとななみ-悪の遺伝子を孕まされる母娘-/data/'

print("=== ACTORS ===")
with open(base + 'Actors.json', 'r', encoding='utf-8') as f:
    actors = json.load(f)
for a in actors:
    if a:
        print(f"Actor {a['id']}: {a['name']} | Nickname: {a.get('nickname')} | Profile: {a.get('profile')}")

print("\n=== MAPS ===")
with open(base + 'MapInfos.json', 'r', encoding='utf-8') as f:
    maps = json.load(f)
for m in maps:
    if m:
        print(f"Map {m['id']}: {m['name']} (parentId: {m['parentId']})")

print("\n=== SYSTEM VARIABLES (ALL) ===")
with open(base + 'System.json', 'r', encoding='utf-8') as f:
    sys_data = json.load(f)
for i, v in enumerate(sys_data.get('variables', [])):
    if v:
        print(f"Var {i}: {v}")

print("\n=== SYSTEM SWITCHES (ALL) ===")
for i, s in enumerate(sys_data.get('switches', [])):
    if s:
        print(f"Switch {i}: {s}")

print("\n=== COMMON EVENTS ===")
with open(base + 'CommonEvents.json', 'r', encoding='utf-8') as f:
    ces = json.load(f)
for ce in ces:
    if ce and ce.get('name'):
        print(f"CE {ce['id']}: {ce['name']}")
