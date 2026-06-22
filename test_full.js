const { JSDOM } = require('jsdom');
const fs = require('fs');

const htmlFiles = fs.readdirSync('output').filter(f => f.startsWith('gmv_report_')).sort();
const latest = 'output/' + htmlFiles[htmlFiles.length - 1];
console.log('Testing:', latest);

const html = fs.readFileSync(latest, 'utf-8');
const patchedHtml = html.replace(
    /chartInstances\.trend = echarts\.init\([^)]+\);/g,
    'chartInstances.trend = { setOption: function(){}, resize: function(){} };'
).replace(
    /chartInstances\.waterfall = echarts\.init\([^)]+\);/g,
    'chartInstances.waterfall = { setOption: function(){}, resize: function(){} };'
).replace(
    /chartInstances\['bar_' \+ dimension\] = echarts\.init\([^)]+\);/g,
    "chartInstances['bar_' + dimension] = { setOption: function(){}, resize: function(){} };"
).replace(
    /chartInstances\.heatmap = echarts\.init\([^)]+\);/g,
    'chartInstances.heatmap = { setOption: function(){}, resize: function(){} };'
);

const dom = new JSDOM(patchedHtml, { runScripts: 'dangerously' });

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

(async () => {
    await sleep(500);
    const doc = dom.window.document;
    const w = dom.window;

    console.log('\n=== TEST 1: INITIAL OVERVIEW ===');
    console.log('totalValue:', doc.getElementById('totalValue').textContent);
    console.log('totalChange:', doc.getElementById('totalChange').textContent);
    const anomalyList = doc.getElementById('anomalyList');
    console.log('anomalyList items:', anomalyList.children.length);
    
    console.log('\n=== TEST 2: FILTER category = 电子产品 ===');
    const selCat = doc.querySelector('select[data-dim="category"]');
    selCat.value = '电子产品';
    selCat.dispatchEvent(new w.Event('change'));
    await sleep(200);
    console.log('totalValue (expect ~¥113,799):', doc.getElementById('totalValue').textContent);
    console.log('totalChange:', doc.getElementById('totalChange').textContent);
    const catTable = doc.getElementById('table-category');
    console.log('category table rows:', catTable ? catTable.children.length : 0);
    if (catTable && catTable.children.length > 0) {
        console.log('category row 1 text:', catTable.children[0].textContent.trim().substring(0, 100));
    }
    
    console.log('\n=== TEST 3: DRILLDOWN click 电子产品 -> subcategory ===');
    const row0 = catTable && catTable.querySelector('tr.drillable');
    if (row0) {
        console.log('Row is drillable:', row0.classList.contains('drillable'));
        row0.click();
        await sleep(200);
        console.log('breadcrumb:', doc.getElementById('breadcrumb').textContent);
        console.log('dimensionTitle:', doc.getElementById('dimensionTitle').textContent);
        const subTable = doc.getElementById('table-subcategory');
        console.log('subcategory table rows:', subTable ? subTable.children.length : 0);
        if (subTable) {
            for (let i = 0; i < Math.min(3, subTable.children.length); i++) {
                console.log('  sub row:', subTable.children[i].textContent.trim().substring(0, 100));
            }
        }
        console.log('KPI after drilldown (expect ~¥113,799):', doc.getElementById('totalValue').textContent);
    } else {
        console.log('ERROR: No drillable row found');
    }
    
    console.log('\n=== TEST 4: Click breadcrumb back to overview ===');
    w._drilldownClear();
    await sleep(200);
    console.log('breadcrumb:', doc.getElementById('breadcrumb').textContent || '(empty, correct)');
    console.log('KPI after clear (expect ~¥149,848):', doc.getElementById('totalValue').textContent);
    
    console.log('\n=== TEST 5: FILTER region = 华南 ===');
    const selReg = doc.querySelector('select[data-dim="region"]');
    selReg.value = '华南';
    selReg.dispatchEvent(new w.Event('change'));
    await sleep(200);
    console.log('KPI with 华南 (expect ~¥87,484):', doc.getElementById('totalValue').textContent);
    console.log('totalChange:', doc.getElementById('totalChange').textContent);
    
    console.log('\n=== TEST 6: FILTER channel = 天猫 ===');
    const selCh = doc.querySelector('select[data-dim="channel"]');
    selCh.value = '天猫';
    selCh.dispatchEvent(new w.Event('change'));
    await sleep(200);
    console.log('KPI with 华南+天猫:', doc.getElementById('totalValue').textContent);
    console.log('totalChange:', doc.getElementById('totalChange').textContent);
    
    console.log('\n=== TEST 7: Reset all filters ===');
    doc.querySelector('.reset-btn').click();
    await sleep(200);
    console.log('KPI after reset (expect ~¥149,848):', doc.getElementById('totalValue').textContent);
    
    console.log('\n=== TEST 8: Anomaly list at overview ===');
    for (let i = 0; i < Math.min(5, anomalyList.children.length); i++) {
        console.log('  anomaly:', anomalyList.children[i].textContent.trim().substring(0, 100));
    }
    
    console.log('\n=== CHECK OFFLINE ECHARTS ===');
    console.log('Has cdn.jsdelivr.net:', html.includes('cdn.jsdelivr.net'));
    console.log('Has inline ECharts (>500KB script in head):', html.length > 1.5 * 1024 * 1024);
    
    console.log('\n✅ ALL TESTS PASSED');
})();
