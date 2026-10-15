import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
base = 'E:/ACG/魔法少女るなとななみ-悪の遺伝子を孕まされる母娘-/data/'

with open(base + 'Actors.json', 'r', encoding='utf-8') as f:
    actors = json.load(f)
print("=== ACTORS ===")
for a in actors:
    if a:
        print(f"Actor {a['id']}: {a['name']} | Nickname: {a.get('nickname')} | Profile: {a.get('profile')}")

with open(base + 'CommonEvents.json', 'r', encoding='utf-8') as f:
    ces = json.load(f)

print("\n=== STORY & ENDING COMMON EVENTS ===")
for ce in ces:
    if ce and ce.get('name'):
        name = ce['name']
        if any(k in name for k in ['结局', 'ED', 'Ending', '章', '幕间', 'プロローグ', 'エピローグ', 'クリア', '回想', '败北', '博士', '七海', '琉奈', '母亲']):
            print(f"CE {ce['id']}: {name}")
