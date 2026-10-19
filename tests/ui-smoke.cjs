/* Test-only bridge fixtures. Not bundled into either application. */
const {chromium} = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const screenshots = process.env.SACRED_SCREENSHOTS || path.join(root, 'artifacts', 'screenshots');
fs.mkdirSync(screenshots, {recursive:true});
const fixture = ({mode, tier}) => {
  const features = ['single_edit','performance','measurements','themes','potato','filter_keys','owner_presets','drag','advanced','profiles','beta','prefire','pickup','wall_replace','auto_build','mantle','quick_reset','floor_cone','double_edit','gun_pullout'];
  const floors = [0,0,0,0,1,2,2,3,3,3,3,3,3,3,3,3,3,3];
  const level = ['Core','Plus','Pro','Elite'].indexOf(tier);
  let macro = {kind:'single_edit',enabled:false,active:false,available:true,game_running:false,reason:'Disabled after login',config:{activation:'F',edit:'E',select:'MOUSE1',confirm:'E',emergency:'F8',toggle:'F9',step_delay_ms:20,repeat_ms:150,press_ms:15,confirm_mode:'manual',game_auto_confirm:false}};
  macro.macros={single_edit:{kind:'single_edit',config:macro.config,enabled:false,reason:'Disabled after login'}};
  macro.catalog={single_edit:macro.config};
  const session = {user:{id:mode==='manager'?1:2,username:mode==='manager'?'TestOwner':'TestMember',role:mode==='manager'?'owner':'member'},tier:'Sacred',permissions:Object.fromEntries(features.map(f=>[f,true])),enforced:{},overrides:{},expires_at:null,lease_seconds:25,welcome:{}};
  const license = {id:1,key_hint:'…TEST',tier,duration_days:30,redeemed_at:1800000000,expires_at:1900000000,status:'active',overrides:{},enforced:{},welcome:{},permanent:false};
  const user = {...session.user,id:2,username:'TestMember',role:'member',license_id:1,created_at:1800000000,banned:0};
  const content = {presets:[{id:1,name:'Owner FPS preset',version:1,body:{preset:'performance',target_fps:144},channel:'stable'}],announcements:[{id:2,name:'Welcome to Sacred',body:{message:'Test fixture: your workspace is ready.'},channel:'stable'}],releases:[{id:3,name:'0.1.0',channel:'stable',body:{notes:'Test release.',url:'https://downloads.example.com/test.zip',version:'0.1.0'}}],welcomes:[]};
  window.__calls = [];
  window.pywebview = {api:{
    bootstrap:async()=>({ok:true,data:{mode,api_url:'https://test.invalid',device_id:'fixture-device',native:true,version:'0.1.0'}}),
    request:async(method,url,data={})=>{
      window.__calls.push({method,url,data});
      let result={};
      if(url==='/v1/auth/login')result=session;
      else if(url==='/v1/license/validate')result={tier,duration_days:30,permanent:false};
      else if(url==='/v1/auth/register')result={...session,recovery_codes:['TEST-ONLY-RECOVERY-001','TEST-ONLY-RECOVERY-002']};
      else if(url==='/v1/auth/logout'||url==='/v1/auth/recover'||url==='/v1/device/request')result={message:'Complete'};
      else if(url==='/v1/content'||url==='/v1/admin/content')result=content;
      else if(url==='/v1/admin/overview')result={users:24,licenses:31,active_sessions:9,alerts:[]};
      else if(url.startsWith('/v1/admin/users?')||url==='/v1/admin/users')result={users:[user]};
      else if(url.startsWith('/v1/admin/users/'))result=method==='GET'?{user,license,sessions:[],devices:[]}:{message:'Updated'};
      else if(url==='/v1/admin/licenses')result=method==='GET'?{licenses:[license]}:{keys:['TEST-ONLY-LICENSE'],licenses:[license]};
      else if(url.startsWith('/v1/admin/licenses/'))result={license};
      else if(url==='/v1/admin/transfers')result={transfers:[{id:1,user_id:2,username:'TestMember',reason:'New test PC',created_at:1800000000,status:'pending'}]};
      else if(url.startsWith('/v1/admin/transfers/'))result={message:'Reviewed'};
      else if(url==='/v1/admin/audit')result={audit:[{id:1,action:'license_created',actor_id:1,target_type:'license',target_id:1,created_at:1800000000,details:{tier:'Elite'}}]};
      else if(url==='/v1/admin/feedback')result={feedback:[{id:1,username:'TestMember',message:'Test fixture feedback.',created_at:1800000000,diagnostics:{}}]};
      else if(url==='/v1/admin/settings')result={transfer_cooldown_hours:24,reset_cooldown_hours:1};
      else if(url==='/v1/profiles')result={profiles:[{id:1,name:'Daily setup',config:{kind:'single_edit',config:macro.config},created_at:1800000000}]};
      else if(url==='/v1/me')result=session;
      else if(url==='/v1/tools/authorize')result={settings:data.settings};
      else if(url==='/v1/feedback')result={message:'Saved'};
      else return {ok:false,error:'Unexpected test route: '+method+' '+url};
      return {ok:true,data:result};
    },
    local:async(action,data={})=>{
      window.__calls.push({action,data});
      if(window.__failLocal===action)return {ok:false,error:'Test service unavailable'};
      let result={};
      if(action==='hardware')result={cpu:'AMD Ryzen 7 5700G',gpu:'AMD Radeon RX 7600',ram_gb:32,windows:'Windows 11 · test fixture',display:{width:1920,height:1080,refresh_hz:144}};
      else if(action==='macro_status')result=macro;
      else if(action==='macro_configure'){macro={...macro,...data,enabled:false,macros:{...macro.macros,[data.kind]:{kind:data.kind,config:data.config,enabled:false,reason:'Ready'}}};result=macro;}
      else if(action==='macro_enable'){macro.macros[data.kind].enabled=data.enabled;macro.enabled=Object.values(macro.macros).some(m=>m.enabled);result=macro;}
      else if(action==='emergency_stop'){macro.enabled=false;result=macro;}
      else if(action==='macro_warning')result={acknowledged:true};
      else if(action==='loadout_list')result={loadouts:[]};
      else if(action==='loadout_save')result={id:'fixture',name:data.name,macros:macro.macros,appearance:{accent:'#9A82F7'}};
      else if(action==='macro_preferences')result={...macro,editing_conflicts:data.editing_conflicts};
      else if(action==='backups')result={backups:[{id:'testbackup',kind:'fortnite',created_at:1800000000,status:'applied'}]};
      else if(action==='restore')result={success:true,restored:['FrameRateLimit'],conflicts:[],errors:[]};
      else if(action==='settings_preview')result={plan_id:'test-plan',preset:data.preset,target_fps:data.target_fps,changes:[{section:'/Script/FortniteGame.FortGameUserSettings',key:'FrameRateLimit',current:'60.000000',proposed:'144.000000'}],tradeoffs:['VSync off may cause screen tearing.'],skipped:[],compatibility:'Test fixture values; no game files accessed.',restart_required:true,administrator_required:false};
      else if(action==='settings_apply')result={success:true,backup_id:'testbackup',applied:['FrameRateLimit'],errors:[]};
      else if(action==='filter_get')result={enabled:false,wait_ms:0,delay_ms:500,repeat_ms:33,bounce_ms:0};
      else if(action==='filter_apply')result={success:true,backup_id:'testbackup'};
      else if(action==='measurements')result={measurements:[{name:'Baseline',fps:120,frame_time_ms:8.3,cpu_usage_percent:32,cpu_sample_seconds:60,ram_usage_percent:45,gpu_usage_percent:null,created_at:1800000000,notes:'Test observation'}],procedure:'Repeat the same 60-second test route.',limitations:['Automatic FPS capture is unavailable.']};
      else if(action==='measurement_save')result={id:'testrecord',...data};
      else if(action==='theme')result=data;
      else if(action==='windows_settings')result={opened:data.page};
      else if(action==='export_recovery')result={cancelled:true};
      else return {ok:false,error:'Unexpected test local action '+action};
      return {ok:true,data:result};
    }
  }};
};

(async()=>{
  const server = http.createServer((req,res)=>{
    const name = req.url.split('?')[0] === '/' ? 'index.html' : req.url.split('?')[0].slice(1);
    if(!['index.html','styles.css','app.js','manager.js','assets/sacred-icon.png'].includes(name)){res.writeHead(404);res.end();return;}
    const file=path.join(root,'web',name);
    if(!fs.existsSync(file)){res.writeHead(404);res.end();return;}
    res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.png')?'image/png':'text/html');res.end(fs.readFileSync(file));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch({headless:true,...(process.env.SACRED_CHROMIUM?{executablePath:process.env.SACRED_CHROMIUM}:{}),args:['--no-sandbox']});
  const results=[];
  try{
    for(const [mode,tier] of [['member','Sacred'],['manager','Sacred']]){
      const context=await browser.newContext({viewport:{width:1280,height:900},reducedMotion:'reduce'});
      await context.addInitScript(fixture,{mode,tier});
      const page=await context.newPage();const errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto(`http://127.0.0.1:${server.address().port}/`);
      await page.locator('form[data-form="login"]').waitFor();
      await page.waitForFunction(()=>[...document.querySelectorAll('img.sacred-app-icon')].every(i=>i.complete&&i.naturalWidth>0));
      await page.screenshot({path:path.join(screenshots,`${mode}-${tier}-login.png`),fullPage:true});
      if(mode==='member'&&tier==='Sacred'){
        await page.locator('[data-action="open-restore"]').click();
        await page.locator('[data-action="restore-backup"]').click();
        await page.locator('[data-action="confirm-operation"]').click();
        await page.getByRole('heading',{name:'Restore completed'}).waitFor();
        await page.locator('[data-action="close-modal"]').first().click();
        await page.screenshot({path:path.join(screenshots,'member-offline-restore.png'),fullPage:true});
        await page.locator('[data-action="back-to-login"]').click();
      }
      await page.locator('#username').fill(mode==='manager'?'TestOwner':'TestMember');
      await page.locator('#password').fill('Test password 123!');
      if(mode==='manager')await page.locator('#totp').fill('123456');
      await page.locator('form[data-form="login"] button[type="submit"]').click();
      await page.locator('.welcome').waitFor();
      await page.screenshot({path:path.join(screenshots,`${mode}-${tier}-welcome.png`)});
      await page.locator('[data-action="enter-workspace"]').click();
      await page.locator('.page-heading').waitFor();
      await page.locator('[data-action="account-menu"]').click();
      assert(await page.locator('.account-menu').isVisible());
      await page.screenshot({path:path.join(screenshots,`${mode}-${tier}-menu.png`),fullPage:true});
      await page.locator('.breadcrumbs').click();
      assert.equal(await page.locator('.account-menu').count(),0);
      const views=mode==='manager'?['admin-overview','admin-users','admin-licenses','admin-transfers','admin-content','admin-feedback','admin-audit','admin-settings']:['dashboard','performance','macros','filter','profiles','measurements','backups','misc','theme','account'];
      for(const view of views){
        await page.locator(`nav [data-nav="${view}"]`).click();
        await page.locator('#view-content .loading').waitFor({state:'detached'});
        assert.equal(await page.getByRole('heading',{name:'Could not load this view'}).count(),0,`${mode}/${tier}/${view} failed`);
        await page.screenshot({path:path.join(screenshots,`${mode}-${tier}-${view}.png`),fullPage:true});
        const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);
        assert.equal(overflow,false,`${mode}/${tier}/${view} overflow`);
      }
      if(mode==='manager'){
        for(const [view,action,name] of [['admin-users','user-detail','member-details'],['admin-licenses','license-detail','license-overrides'],['admin-licenses','generate-licenses','generate-licenses'],['admin-content','preview-welcome','welcome-preview']]){
          await page.locator(`nav [data-nav="${view}"]`).click();
          await page.locator(`[data-action="${action}"]`).first().click();
          await page.locator('.modal').waitFor();
          await page.screenshot({path:path.join(screenshots,`manager-${name}.png`),fullPage:true});
          await page.locator('[data-action="close-modal"]').first().click();
        }
        await page.locator('[data-action="content-tab"][data-kind="release"]').click();
        await page.locator('#name').fill('0.1.1');
        await page.locator('#version').fill('0.1.1');
        await page.locator('#notes').fill('Fixture release');
        await page.locator('#url').fill('https://downloads.example.com/sacred.zip');
        await page.screenshot({path:path.join(screenshots,'manager-release-editor.png'),fullPage:true});
        await page.locator('form[data-form="publish-content"] button[type="submit"]').click();
        await page.waitForFunction(()=>window.__calls.some(c=>c.method==='POST'&&c.url==='/v1/admin/content'));
        const publish=await page.evaluate(()=>window.__calls.find(c=>c.method==='POST'&&c.url==='/v1/admin/content'));
        assert.equal(publish.data.body.url,'https://downloads.example.com/sacred.zip');
      }
      if(mode==='member'&&tier==='Sacred'){
        await page.locator('nav [data-nav="account"]').click();
        await page.locator('[data-action="release-details"]').click();
        await page.getByRole('heading',{name:'Download 0.1.0'}).waitFor();
        await page.screenshot({path:path.join(screenshots,'member-release-details.png'),fullPage:true});
        await page.locator('[data-action="close-modal"]').first().click();
        await page.evaluate(()=>window.__failLocal='measurements');
        await page.locator('nav [data-nav="measurements"]').click();
        await page.getByRole('heading',{name:'Could not load this view'}).waitFor();
        await page.screenshot({path:path.join(screenshots,'member-error-state.png'),fullPage:true});
        await page.evaluate(()=>window.__failLocal=null);
        await page.locator('nav [data-nav="dashboard"]').click();
        await page.emulateMedia({reducedMotion:'no-preference'});
        await page.evaluate(()=>window.dispatchEvent(new CustomEvent('sacred-status',{detail:{game_running:true}})));
        assert.equal(await page.locator('.brand-mark.large').evaluate(e=>getComputedStyle(e).animationPlayState),'paused');
        await page.evaluate(()=>window.dispatchEvent(new CustomEvent('sacred-status',{detail:{game_running:false,minimized:false}})));
        assert.equal(await page.locator('.brand-mark.large').evaluate(e=>getComputedStyle(e).animationPlayState),'running');
        await page.emulateMedia({reducedMotion:'reduce'});
        await page.locator('nav [data-nav="performance"]').click();
        await page.locator('form[data-form="performance"] button[type="submit"]').click();
        await page.locator('.modal').waitFor();
        await page.screenshot({path:path.join(screenshots,'member-Elite-settings-preview.png'),fullPage:true});
        await page.locator('[data-action="close-modal"]').first().click();
        await page.locator('nav [data-nav="macros"]').click();
        for(const kind of ['prefire','pickup','wall_replace','auto_build','mantle','quick_reset','floor_cone','double_edit','gun_pullout']) {
          await page.locator(`[data-kind="${kind}"]`).click();
          await page.locator('form[data-form="extended-macro"]').waitFor();
        assert.match(await page.locator('main').innerText(),/Timing is best effort/);
          await page.locator('form[data-form="extended-macro"] button[type="submit"]').click();
          await page.waitForTimeout(100);
          const last=await page.evaluate(()=>window.__calls.filter(c=>c.action==='macro_configure').at(-1));
          assert.equal(last.data.kind,kind);
          await page.screenshot({path:path.join(screenshots,`member-Elite-${kind}.png`),fullPage:true});
        }
        await page.locator('[data-kind="drag"]').click();
        await page.screenshot({path:path.join(screenshots,'member-Elite-drag.png'),fullPage:true});
        await page.locator('#edit').fill('X');
        await page.evaluate(()=>window.dispatchEvent(new CustomEvent('sacred-status',{detail:{macro:{enabled:false,reason:'Emergency stop',foreground:false}}})));
        assert.equal(await page.locator('[data-macro-enabled]').textContent(),'Disabled');
        assert.match(await page.locator('[data-macro-status]').textContent(),/Emergency stop/);
        assert.equal(await page.locator('#edit').inputValue(),'X');
        await page.setViewportSize({width:900,height:720});
        await page.screenshot({path:path.join(screenshots,'member-Elite-900px.png'),fullPage:true});
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
        await page.evaluate(()=>window.dispatchEvent(new CustomEvent('sacred-status',{detail:{authorized:false,reason:'Test disconnection'}})));
        await page.screenshot({path:path.join(screenshots,'member-Elite-disconnected.png'),fullPage:true});
        await page.locator('[data-action="relogin"]').click();
        await page.locator('form[data-form="login"]').waitFor();
      }
      assert.deepEqual(errors,[],`${mode}/${tier} JavaScript errors`);
      results.push({mode,tier,views:views.length,errors:0});
      await context.close();
    }
    fs.writeFileSync(path.join(screenshots,'results.json'),JSON.stringify(results,null,2));
    console.log(JSON.stringify({passed:true,results,screenshots},null,2));
  }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exit(1);});
