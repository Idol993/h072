import json, re, sys, os, glob

html_files = sorted(glob.glob('output/gmv_report_*.html'), key=os.path.getmtime, reverse=True)
filepath = html_files[0]
print(f'Checking: {filepath}')
print(f'File size: {os.path.getsize(filepath)/1024:.2f} KB')
with open(filepath, 'r', encoding='utf-8') as f:
    html = f.read()

has_cdn = 'cdn.jsdelivr.net' in html
has_echarts_inline = 'var echarts' in html or 'function(echarts)' in html or 'echarts =' in html
has_raw_data = 'const RAW_DATA =' in html
has_marker = 'Isolated horizon' in html or ('echarts.min.js' in html and not has_cdn)
print(f'CDN dependency (should be False): {has_cdn}')
print(f'ECharts inlined (should be True): {len(html) > 1000000}')
print(f'Contains RAW_DATA: {has_raw_data}')

start = html.find('const RAW_DATA = ') + len('const RAW_DATA = ')
remaining = html[start:]

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

raw = remaining[:end]
print(f'Extracted JSON length: {len(raw)} chars')
data = json.loads(raw)
print('JSON parsed successfully!')

trend = data.get('overall_trend', [])
print(f'\nTrend data points: {len(trend)} periods')
if trend:
    print(f'First 3 periods: {[d["period"] for d in trend[:3]]}')
    print(f'Last 3 periods: {[d["period"] for d in trend[-3:]]}')

anomalies = data.get('anomalies', [])
print(f'\nAnomalies detected: {len(anomalies)}')
for a in anomalies[:8]:
    dim = a.get('_dim') or a.get('dimension')
    mom = a.get('mom_pct')
    print(f'  {dim}: {a["value"]} ({mom}%) direction={a.get("anomaly_direction")}')

dims = data.get('dimensions', {})
for dim, vals in dims.items():
    anom_count = sum(1 for v in vals if v.get('is_anomaly'))
    print(f'\n{dim}: {len(vals)} items, {anom_count} anomalies')
    for v in vals[:3]:
        mom = v.get('mom_pct')
        print(f'  {v["value"]}: GMV={v["metric_value"]:,.2f}, 环比={mom}%, 异常={v.get("is_anomaly")}')

print(f'\nRaw data records: {len(data.get("raw_data", []))}')
if data.get('raw_data'):
    dims_in_raw = list(data['raw_data'][0].keys())
    print(f'Fields in raw data: {dims_in_raw}')
    has_subcat = 'subcategory' in dims_in_raw
    print(f'Has subcategory for drilldown: {has_subcat}')

config = data.get('config', {})
dd_map = config.get('drilldown_map', {})
print(f'\nDrilldown map: {dd_map}')
print(f'Category drilldown targets: {dd_map.get("category")}')
print(f'Region drilldown targets: {dd_map.get("region")}')
print(f'Channel drilldown targets: {dd_map.get("channel")}')

print(f'\nMA windows: {data.get("ma_windows")}')
if trend:
    sample = trend[0]
    print(f'Sample trend point keys: {list(sample.keys())}')

waterfall = data.get('waterfall', [])
print(f'\nWaterfall items: {len(waterfall)}')
for w in waterfall:
    print(f'  {w["label"]}: {w["value"]:,.2f} ({w["type"]})')
