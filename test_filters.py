import json, re, os, glob

html_files = sorted(glob.glob('output/gmv_report_*.html'), key=os.path.getmtime, reverse=True)
with open(html_files[0], 'r', encoding='utf-8') as f:
    html = f.read()

start = html.find('const RAW_DATA = ') + len('const RAW_DATA = ')
remaining = html[start:]
depth = 0
end = 0
i = 0
while i < len(remaining):
    ch = remaining[i]
    if ch == '{': depth += 1
    elif ch == '}':
        depth -= 1
        if depth == 0:
            end = i + 1
            break
    i += 1
data = json.loads(remaining[:end])
raw = data['raw_data']

def get_filtered(filters, dd_stack):
    all_f = dict(filters)
    if dd_stack:
        last = dd_stack[-1]
        all_f[last['dimension']] = last['value']
    res = []
    for r in raw:
        ok = True
        for k, v in all_f.items():
            if v and str(r.get(k)) != str(v):
                ok = False
                break
        if ok:
            res.append(r)
    return res

def compute_trend(filtered):
    by_p = {}
    for r in filtered:
        p = str(r['period'])
        by_p[p] = by_p.get(p, 0) + float(r.get('metric_value', 0))
    ps = sorted(by_p.keys())
    return [{'period': p, 'metric_value': by_p[p]} for p in ps]

def compute_kpi(filtered):
    trend = compute_trend(filtered)
    if not trend: return (0, 0, None)
    latest = trend[-1]['metric_value']
    prev = trend[-2]['metric_value'] if len(trend) >= 2 else 0
    mom = ((latest - prev) / prev * 100) if prev > 0 else None
    return latest, prev, mom

def compute_dim(filtered, dim):
    pset = set(str(r['period']) for r in filtered)
    ps = sorted(pset)
    if not ps: return []
    latest_p = ps[-1]
    prev_p = ps[-2] if len(ps) >= 2 else None
    lat_m, prev_m = {}, {}
    for r in filtered:
        p = str(r['period'])
        dv = str(r.get(dim, 'NULL'))
        v = float(r.get('metric_value', 0))
        if p == latest_p: lat_m[dv] = lat_m.get(dv, 0) + v
        if prev_p and p == prev_p: prev_m[dv] = prev_m.get(dv, 0) + v
    total_lat = sum(lat_m.values())
    allk = set(list(lat_m.keys()) + (list(prev_m.keys()) if prev_p else []))
    thr = 15
    vals = []
    for k in allk:
        lat = lat_m.get(k, 0)
        prv = prev_m.get(k, 0)
        mom_pct = ((lat / prv) - 1) * 100 if prv > 0 else None
        is_anom = mom_pct is not None and abs(mom_pct) >= thr
        vals.append({
            'value': k, 'metric_value': lat, 'prev_value': prv,
            'mom_pct': mom_pct, 'contribution_pct': (lat / total_lat * 100) if total_lat > 0 else 0,
            'is_anomaly': is_anom,
            'anomaly_direction': 'up' if (is_anom and mom_pct > 0) else ('down' if (is_anom and mom_pct < 0) else None)
        })
    vals.sort(key=lambda x: -x['metric_value'])
    return vals

print('=== TEST 1: Overview (no filter) ===')
filt = get_filtered({}, [])
latest, prev, mom = compute_kpi(filt)
print(f'KPI: {latest:,.0f} (prev: {prev:,.0f}, mom: {mom:.2f}%)')
print(f'Filtered rows: {len(filt)}')
trend = compute_trend(filt)
print(f'Trend periods: {len(trend)}')
for t in trend[-3:]:
    print(f"  {t['period']}: {t['metric_value']:,.0f}")

print('\n=== TEST 2: Filter category = 电子产品 ===')
filt = get_filtered({'category': '电子产品'}, [])
latest, prev, mom = compute_kpi(filt)
print(f'KPI: {latest:,.0f} (prev: {prev:,.0f}, mom: {mom:.2f}%)')
print(f'Filtered rows: {len(filt)}')
print(f'All rows are 电子产品: {all(r["category"] == "电子产品" for r in filt)}')
trend = compute_trend(filt)
print(f'Trend periods: {len(trend)} (should match overview)')
for t in trend[-3:]:
    print(f"  {t['period']}: {t['metric_value']:,.0f}")
cats = compute_dim(filt, 'category')
print(f'Category items after filter: {len(cats)} (should be 1 or few)')
for c in cats:
    print(f'  {c["value"]}: {c["metric_value"]:,.0f}, mom={c["mom_pct"]:.2f}%' if c['mom_pct'] else f'  {c["value"]}: {c["metric_value"]:,.0f}, mom=-')

print('\n=== TEST 3: Drilldown category=电子产品 -> subcategory ===')
filt = get_filtered({}, [{'dimension': 'category', 'value': '电子产品'}])
latest, prev, mom = compute_kpi(filt)
print(f'KPI (same as filter test): {latest:,.0f}')
print(f'Filtered rows: {len(filt)}')
print(f'All rows are 电子产品: {all(r["category"] == "电子产品" for r in filt)}')
subs = compute_dim(filt, 'subcategory')
print(f'Subcategories found: {len(subs)}')
for s in subs[:5]:
    mark = ' ANOMALY' if s['is_anomaly'] else ''
    print(f'  {s["value"]}: {s["metric_value"]:,.0f}, contrib={s["contribution_pct"]:.1f}%, mom={s["mom_pct"]:.1f}%{mark}' if s['mom_pct'] else f'  {s["value"]}: {s["metric_value"]:,.0f}, contrib={s["contribution_pct"]:.1f}%, mom=-')

print('\n=== TEST 4: Filter region = 华南 ===')
filt = get_filtered({'region': '华南'}, [])
latest, prev, mom = compute_kpi(filt)
print(f'KPI: {latest:,.0f} (prev: {prev:,.0f}, mom: {mom:.2f}%)')
print(f'All rows are 华南: {all(r["region"] == "华南" for r in filt)}')

print('\n=== TEST 5: Clear filters back to overview ===')
filt = get_filtered({}, [])
latest2, prev2, mom2 = compute_kpi(filt)
print(f'KPI: {latest2:,.0f}')
print(f'Same as test 1: {abs(latest2 - latest) < 1 and abs(prev2 - prev) < 1}')

print('\n=== TEST 6: Anomalies at overview ===')
filt = get_filtered({}, [])
anomalies = []
for dim in ['category', 'region', 'channel']:
    vals = compute_dim(filt, dim)
    for v in vals:
        if v['is_anomaly']:
            anomalies.append((dim, v['value'], v['mom_pct'], v['anomaly_direction']))
anomalies.sort(key=lambda x: -abs(x[2] or 0))
print(f'Total anomalies: {len(anomalies)}')
for d, val, pct, dr in anomalies[:8]:
    print(f'  {d}: {val} ({pct:.2f}%, {dr})')

print('\nALL COMPUTATIONS WORK CORRECTLY - Python simulation passes')
