import json, re, sys, os, glob

html_files = sorted(glob.glob('output/gmv_report_*.html'), key=os.path.getmtime, reverse=True)
filepath = html_files[0]
print('=' * 60)
print('报告文件:', filepath)
print('文件大小: {:.2f} KB'.format(os.path.getsize(filepath) / 1024))
print()

with open(filepath, 'r', encoding='utf-8') as f:
    html = f.read()

print('【离线渲染测试】')
has_cdn = 'cdn.jsdelivr.net' in html or 'cdnjs.cloudflare.com' in html or 'unpkg.com' in html
print('  CDN 依赖（应为 False）:', has_cdn)
print('  内联 ECharts（文件 > 1.2MB):', os.path.getsize(filepath) > 1.2 * 1024 * 1024)
has_raw_data = 'const RAW_DATA = ' in html
print('  内联原始数据:', has_raw_data)
print()

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
    return [(p, by_p[p]) for p in ps]

def compute_kpi(filtered):
    trend = compute_trend(filtered)
    if not trend: return (0, 0, None)
    latest = trend[-1][1]
    prev = trend[-2][1] if len(trend) >= 2 else 0
    mom = ((latest - prev) / prev * 100) if prev > 0 else None
    return latest, prev, mom

print('【趋势图测试】')
trend = compute_trend(get_filtered({}, []))
print('  周期点数:', len(trend), '（每周一个点）')
print('  最近 3 期:')
for p, v in trend[-3:]:
    print('     {}: ¥{:,.0f}'.format(p, v))
print()

print('【KPI + 筛选联动测试】')
tests = [
    ('总览', {}, [], 149848),
    ('品类=电子产品', {'category': '电子产品'}, [], 113799),
    ('地区=华南', {'region': '华南'}, [], 87484),
    ('渠道=天猫', {'channel': '天猫'}, [], 101499),
    ('华南+天猫交叉', {'region': '华南', 'channel': '天猫'}, [], 80327),
]
all_pass = True
for name, f, dd, exp in tests:
    lat, prev, mom = compute_kpi(get_filtered(f, dd))
    ok = abs(lat - exp) < 500
    status = 'PASS' if ok else 'FAIL'
    if not ok: all_pass = False
    mom_str = '{:.2f}%'.format(mom) if mom is not None else '-'
    print('  [{}] {}: KPI=¥{:,.0f}（预期≈¥{:,.0f}）环比={}'.format(status, name, lat, exp, mom_str))
print('  全部通过:', all_pass)
print()

print('【维度下钻测试】')
filt_dd = get_filtered({}, [{'dimension': 'category', 'value': '电子产品'}])
lat_dd, prev_dd, mom_dd = compute_kpi(filt_dd)
print('  下钻品类=电子产品 KPI=¥{:,.0f}'.format(lat_dd))

def compute_dim(filtered, dim):
    pset = set(str(r['period']) for r in filtered)
    ps = sorted(pset)
    if not ps: return []
    latest_p = ps[-1]
    prev_p = ps[-2] if len(ps) >= 2 else None
    lat_m = {}
    prev_m = {}
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
        if is_anom and mom_pct > 0: dr = 'up'
        elif is_anom and mom_pct < 0: dr = 'down'
        else: dr = None
        vals.append({'value': k, 'metric_value': lat, 'mom_pct': mom_pct, 'is_anomaly': is_anom, 'anomaly_direction': dr})
    vals.sort(key=lambda x: -x['metric_value'])
    return vals

subs = compute_dim(filt_dd, 'subcategory')
print('  子分类数:', len(subs))
for s in subs:
    mark = ' 异常' if s['is_anomaly'] else ''
    mom_s = '{:.1f}%'.format(s['mom_pct']) if s['mom_pct'] else '-'
    print('     {}: ¥{:,.0f}, 环比={}{}'.format(s['value'], s['metric_value'], mom_s, mark))
print()

print('【异常检测测试】')
anomalies = []
for dim in ['category', 'region', 'channel']:
    for v in compute_dim(get_filtered({}, []), dim):
        if v['is_anomaly']:
            anomalies.append((dim, v['value'], v['mom_pct'], v['anomaly_direction']))
anomalies.sort(key=lambda x: -abs(x[2] or 0))
print('  异常项总数:', len(anomalies), '（预期 18）')
up_count = sum(1 for a in anomalies if a[3] == 'up')
down_count = sum(1 for a in anomalies if a[3] == 'down')
print('  上涨异常: {}, 下跌异常: {}'.format(up_count, down_count))
print('  前 5 项:')
for d, val, pct, dr in anomalies[:5]:
    icon = 'UP' if dr == 'up' else 'DOWN'
    print('     [{}] {}: {}（{:.2f}%）'.format(icon, d, val, pct))
print()

print('【清空筛选回到总览测试】')
lat_back, prev_back, mom_back = compute_kpi(get_filtered({}, []))
print('  清空筛选 KPI=¥{:,.0f}（与总览一致: {}）'.format(lat_back, abs(lat_back - 149848) < 500))

print()
print('=' * 60)
if all_pass:
    print('所有主流程验证通过！')
else:
    print('有测试失败！')
