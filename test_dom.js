const { JSDOM } = require('jsdom');
const fs = require('fs');

const htmlFiles = fs.readdirSync('output').filter(f => f.startsWith('gmv_report_')).sort();
const latest = 'output/' + htmlFiles[htmlFiles.length - 1];
console.log('Testing:', latest);

const html = fs.readFileSync(latest, 'utf-8');
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true });

setTimeout(() => {
    const doc = dom.window.document;
    console.log('\n=== INITIAL STATE (Overview) ===');
    console.log('totalValue:', doc.getElementById('totalValue').textContent);
    console.log('totalChange:', doc.getElementById('totalChange').textContent);
    console.log('trendTitle:', doc.getElementById('trendTitle').textContent);
    console.log('breadcrumb:', doc.getElementById('breadcrumb').textContent);
    
    console.log('\n=== SELECT CATEGORY = 电子产品 ===');
    const selects = doc.querySelectorAll('select');
    let found = false;
    selects.forEach(sel => {
        if (sel.getAttribute('data-dim') === 'category') {
            sel.value = '电子产品';
            sel.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
            found = true;
        }
    });
    console.log('Found category select:', found);
    
    setTimeout(() => {
        console.log('totalValue (should be ~¥113,799):', doc.getElementById('totalValue').textContent);
        console.log('totalChange:', doc.getElementById('totalChange').textContent);
        console.log('trendTitle:', doc.getElementById('trendTitle').textContent);
        
        const anomalyList = doc.getElementById('anomalyList');
        console.log('anomalyList children:', anomalyList.children.length);
        
        console.log('\n=== DRILLDOWN: Click 电子产品 row ===');
        const table = doc.getElementById('table-category');
        if (table) {
            const firstRow = table.querySelector('tr');
            if (firstRow) {
                console.log('First row text:', firstRow.textContent.trim().substring(0, 80));
                console.log('Row has drillable class:', firstRow.classList.contains('drillable'));
                firstRow.click();
            }
        }
        
        setTimeout(() => {
            console.log('\n=== AFTER DRILLDOWN ===');
            console.log('breadcrumb:', doc.getElementById('breadcrumb').textContent);
            console.log('dimensionTitle:', doc.getElementById('dimensionTitle').textContent);
            console.log('totalValue (should match ~¥113,799):', doc.getElementById('totalValue').textContent);
            const subTable = doc.getElementById('table-subcategory');
            if (subTable) {
                console.log('subcategory table rows:', subTable.children.length);
                for (let i = 0; i < Math.min(3, subTable.children.length); i++) {
                    console.log('  row:', subTable.children[i].textContent.trim().substring(0, 80));
                }
            } else {
                console.log('ERROR: subcategory table not found');
                const tabs = doc.getElementById('dimensionTabs');
                console.log('Available tabs:', tabs ? tabs.textContent : 'N/A');
            }
            
            console.log('\n=== GO BACK TO OVERVIEW ===');
            const resetBtn = doc.querySelector('.reset-btn');
            if (resetBtn) resetBtn.click();
            
            setTimeout(() => {
                console.log('totalValue (should be ~¥149,848):', doc.getElementById('totalValue').textContent);
                console.log('breadcrumb:', doc.getElementById('breadcrumb').textContent || '(empty, correct)');
                
                console.log('\n=== CHECK FILTER SELECT = 华南 REGION ===');
                selects.forEach(sel => {
                    if (sel.getAttribute('data-dim') === 'region') {
                        sel.value = '华南';
                        sel.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
                    }
                });
                setTimeout(() => {
                    console.log('totalValue (should be ~¥87,484):', doc.getElementById('totalValue').textContent);
                    console.log('totalChange:', doc.getElementById('totalChange').textContent);
                    console.log('\nALL TESTS COMPLETE');
                    process.exit(0);
                }, 200);
            }, 200);
        }, 200);
    }, 200);
}, 1000);
