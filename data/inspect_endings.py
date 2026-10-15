import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
base = 'E:/ACG/魔法少女るなとななみ-悪の遺伝子を孕まされる母娘-/data/'

with open(base + 'CommonEvents.json', 'r', encoding='utf-8') as f:
    ces = json.load(f)

with open(base + 'System.json', 'r', encoding='utf-8') as f:
    sys_data = json.load(f)

sw_names = {i: name for i, name in enumerate(sys_data.get('switches', [])) if name}
var_names = {i: name for i, name in enumerate(sys_data.get('variables', [])) if name}

target_ce_ids = [814, 815, 818, 819, 820, 821, 822, 823, 824, 825, 827, 831, 832, 833, 1301, 1302, 1303, 1304, 1305, 1306]

for ce in ces:
    if ce and ce.get('id') in target_ce_ids:
        print(f"\n==================== CE {ce['id']}: {ce['name']} ====================")
        for cmd in ce.get('list', []):
            code = cmd['code']
            params = cmd['parameters']
            # 101: Show Text, 102: Show Choices, 111: Conditional Branch, 121: Control Switches, 122: Control Variables, 201: Transfer Player
            if code == 111: # Conditional branch
                cond_type = params[0]
                if cond_type == 0: # Switch
                    sw_id = params[1]
                    sw_val = "ON" if params[2] == 0 else "OFF"
                    print(f"  [IF Switch {sw_id} ({sw_names.get(sw_id, '?')}) == {sw_val}]")
                elif cond_type == 1: # Variable
                    var_id = params[1]
                    op = ['==', '>=', '<=', '>', '<', '!='][params[4]] if len(params) > 4 else '?'
                    val = params[3] if params[2] == 0 else f"Var({params[3]})"
                    print(f"  [IF Var {var_id} ({var_names.get(var_id, '?')}) {op} {val}]")
                else:
                    print(f"  [IF condition: {params}]")
            elif code == 101: # Show Text
                pass
            elif code == 401: # Text line
                if any(k in params[0] for k in ['结局', 'ED', 'Ending', 'るな', 'ななみ', '琉奈', '七海', '博士']):
                    print(f"    Text: {params[0]}")
            elif code == 121: # Switch
                pass
            elif code == 122: # Var
                pass
            elif code == 102: # Choice
                print(f"  [CHOICE]: {params[0]}")
