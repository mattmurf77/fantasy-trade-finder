const {chromium}=require('playwright');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.FLEECED_CHROME_PATH?{executablePath:process.env.FLEECED_CHROME_PATH}:{})});
  try {
    const context=await browser.newContext({viewport:{width:432,height:1100},deviceScaleFactor:2});
    const page=await context.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    for(const state of ['launch','resume']){
      await page.goto('file://'+path.join(__dirname,'entry-mock.html')+'?state='+state,{waitUntil:'load'});
      await page.evaluate(()=>document.fonts.ready);
      const capture=page.locator(`[data-capture="${state}"]`);
      assert.equal(await capture.locator('.bottom-nav .active').innerText(),'Acquire');
      assert.equal(await capture.locator('.bottom-nav .tab').count(),5);
      assert.equal(await capture.locator('[data-entry-action]').innerText(),state==='launch'?'Start overhaul':'Resume overhaul');
      assert.equal(await capture.evaluate(el=>el.scrollWidth>el.clientWidth),false);
      const file=path.join(__dirname,'screenshots',`entry-${state}.png`);
      await capture.screenshot({path:file});
      console.log(file);
      await capture.locator('[data-entry-action]').click();
      assert(await capture.locator('.destination').count());
      if(state==='launch'){
        assert.equal(await capture.locator('[data-outlook]').count(),2);
        await capture.locator('[data-outlook="rebuild"]').click();
        assert.equal(await capture.locator('[data-outlook="rebuild"]').getAttribute('aria-pressed'),'true');
      }else assert.equal(await capture.locator('.tracker-row').count(),4);
      await capture.locator('[data-back]').click();
      assert.equal(await capture.locator('[data-entry-action]').count(),1);
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: offline fonts, launch/resume, current Acquire tab context, no capture overflow, local entry/back interactions, no browser errors.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e.stack);process.exit(1);});
