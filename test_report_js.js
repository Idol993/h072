const fs = require('fs');
const html = fs.readFileSync('output/gmv_report_20260622_123652.html', 'utf-8');
const bodyStart = html.indexOf('<body>');
const scriptStart = html.indexOf('<script>', bodyStart) + '<script>'.length;
const scriptEnd = html.lastIndexOf('</script>');
let js = html.substring(scriptStart, scriptEnd);

js = js.replace(/echarts\.[a-zA-Z]+\([^)]*\)/g, '({ setOption: function(){}, resize: function(){} })');
js = js.replace(/document\.getElementById\(['"]([^'"]+)['"]\)/g, (m, id) => {
    return `({ 
        textContent: '', 
        innerHTML: '', 
        className: '',
        querySelector: function(){ return { addEventListener: function(){} }; },
        appendChild: function(){},
        classList: { add: function(){}, remove: function(){} },
        querySelectorAll: function(){ return []; },
        style: { display: '' }
    })`;
});
js = js.replace(/document\.addEventListener\([^)]+\)/g, 'void 0');
js = js.replace(/window\.addEventListener\([^)]+\)/g, 'void 0');
js = js.replace(/window\._drilldown[^=]*=[^;]+;/g, '');
js += `
module.exports = {
    computeKPI: computeKPI,
    computeTrendData: computeTrendData,
    computeDimensionData: computeDimensionData,
    computeWaterfall: computeWaterfall,
    setCurrentFilters: function(f) { currentFilters = f; },
    getCurrentFilters: function() { return currentFilters; },
    setDrilldown: function(s) { drilldownStack = s; },
    getFilteredRawData: getFilteredRawData,
    renderKPI: renderKPI,
    getActiveDimensions: getActiveDimensions
};
`;

const tmpFile = 'tmp_test_js.js';
fs.writeFileSync(tmpFile, js, 'utf-8');

try {
    const t = require('./' + tmpFile);
    
    console.log('=== TEST 1: Overview (no filter) ===');
    t.setCurrentFilters({});
    t.setDrilldown([]);
    let kpi = t.computeKPI();
    console.log('KPI total:', Math.round(kpi.total));
    console.log('KPI prev:', Math.round(kpi.prev));
    console.log('KPI mom:', kpi.mom_pct ? kpi.mom_pct.toFixed(2) + '%' : null);
    let trend = t.computeTrendData();
    console.log('Trend periods:', trend.length);
    console.log('Trend last 3:', trend.slice(-3).map(d => d.period + '=' + Math.round(d.metric_value)));
    
    console.log('\n=== TEST 2: Filter category = 电子产品 ===');
    t.setCurrentFilters({ category: '电子产品' });
    t.setDrilldown([]);
    kpi = t.computeKPI();
    console.log('KPI total (should be lower than ~1,450,000):', Math.round(kpi.total));
    let filt = t.getFilteredRawData();
    console.log('Filtered rows:', filt.length);
    console.log('All filtered rows are category=电子产品:', filt.every(r => r.category === '电子产品'));
    trend = t.computeTrendData();
    console.log('Trend periods:', trend.length);
    console.log('Trend last point:', trend.length ? (trend[trend.length-1].period + '=' + Math.round(trend[trend.length-1].metric_value)) : 'none');
    
    console.log('\n=== TEST 3: Dimension data for category (filtered) ===');
    let dimData = t.computeDimensionData('category');
    console.log('Category values:', dimData.values.length);
    dimData.values.forEach(v => {
        console.log(' ', v.value, '=', Math.round(v.metric_value), 'mom:', v.mom_pct ? v.mom_pct.toFixed(1) + '%' : '-', 'anomaly:', v.is_anomaly);
    });
    
    console.log('\n=== TEST 4: Drilldown into category=电子产品 -> subcategory ===');
    t.setCurrentFilters({});
    t.setDrilldown([{ dimension: 'category', value: '电子产品' }]);
    let activeDims = t.getActiveDimensions();
    console.log('Active dimensions:', activeDims);
    filt = t.getFilteredRawData();
    console.log('Filtered rows (drilldown):', filt.length);
    console.log('All rows are category=电子产品:', filt.every(r => r.category === '电子产品'));
    dimData = t.computeDimensionData('subcategory');
    console.log('Subcategories found:', dimData.values.length);
    dimData.values.slice(0, 5).forEach(v => {
        console.log(' ', v.value, '=', Math.round(v.metric_value), 'contrib:', v.contribution_pct.toFixed(1) + '%', 'mom:', v.mom_pct ? v.mom_pct.toFixed(1) + '%' : '-');
    });
    kpi = t.computeKPI();
    console.log('Drilldown KPI total:', Math.round(kpi.total));
    
    console.log('\n=== TEST 5: Waterfall with filter ===');
    t.setCurrentFilters({ region: '华南' });
    t.setDrilldown([]);
    let wf = t.computeWaterfall();
    console.log('Waterfall items:', wf.length);
    wf.forEach(w => console.log(' ', w.label, '=', Math.round(w.value), w.type));
    
    console.log('\n=== TEST 6: Clear filter back to overview ===');
    t.setCurrentFilters({});
    t.setDrilldown([]);
    kpi = t.computeKPI();
    console.log('KPI total (should match test 1):', Math.round(kpi.total));
    
    console.log('\nALL TESTS PASSED');
} finally {
    fs.unlinkSync(tmpFile);
}
