import re, json, sys

with open('output/gmv_report_20260622_123652.html', 'r', encoding='utf-8') as f:
    html = f.read()

m = re.search(r'<script>(.*?)</script>\s*</body>', html, re.DOTALL)
if not m:
    print('No script found')
    sys.exit(1)
js = m.group(1)
print(f'JS length: {len(js)} chars')

raw_start = js.find('const RAW_DATA = ')
if raw_start < 0:
    print('RAW_DATA not found')
    sys.exit(1)

remaining = js[raw_start + len('const RAW_DATA = '):]
depth = 0
end = 0
i = 0
while i < len(remaining):
    ch = remaining[i]
    if ch == '{':
        depth += 1
    elif ch == '}':
        depth -= 1
        if depth == 0:
            end = i + 1
            break
    i += 1

raw_json = remaining[:end]
print(f'RAW_DATA JSON length: {len(raw_json)}')
data = json.loads(raw_json)
print(f'Raw data rows: {len(data.get("raw_data", []))}')
print(f'Dimensions in config: {data.get("config", {}).get("dimensions")}')
print(f'Filters: {list((data.get("filters") or {}).keys())}')

sample = data['raw_data'][0]
print(f'Sample row keys: {list(sample.keys())}')
print(f'Sample row: {sample}')

cats = set(r.get('category') for r in data['raw_data'])
regions = set(r.get('region') for r in data['raw_data'])
channels = set(r.get('channel') for r in data['raw_data'])
print(f'Categories: {sorted(cats)}')
print(f'Regions: {sorted(regions)}')
print(f'Channels: {sorted(channels)}')

print(f'\nTotal GMV sum: {sum(r.get("metric_value", 0) for r in data["raw_data"]):.2f}')
elec = [r for r in data['raw_data'] if r.get('category') == '电子产品']
print(f'电子产品 GMV sum: {sum(r.get("metric_value", 0) for r in elec):.2f}')
huanan = [r for r in data['raw_data'] if r.get('region') == '华南']
print(f'华南 GMV sum: {sum(r.get("metric_value", 0) for r in huanan):.2f}')
