/* Verify the generated reader using explicit runtime/browser paths. No installs. */
const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url');
const args={};
for(let i=2;i<process.argv.length;i+=2){
 if(!process.argv[i].startsWith('--')||process.argv[i+1]===undefined)throw Error('Use --key value arguments');
 args[process.argv[i].slice(2)]=process.argv[i+1];
}
function inside(root,value){
 const p=path.resolve(root,value),r=path.relative(root,p);
 if(r==='..'||r.startsWith('..'+path.sep)||path.isAbsolute(r))throw Error('Output escapes workspace');
 let parent=p;while(!fs.existsSync(parent)){const next=path.dirname(parent);if(next===parent)break;parent=next;}
 const real=fs.realpathSync(parent),relative=path.relative(root,real);
 if(relative==='..'||relative.startsWith('..'+path.sep)||path.isAbsolute(relative))throw Error('Output symlink escapes workspace');
 return p;
}
(async()=>{
 for(const key of ['workspace','html','out','playwright','browser'])if(!args[key])throw Error('Required --'+key);
 const root=fs.realpathSync(path.resolve(args.workspace));
 const out=inside(root,args.out),temp=inside(root,path.join(out,'browser-runtime'));
 const file=fs.realpathSync(path.resolve(args.html));inside(root,file);
 fs.mkdirSync(temp,{recursive:true});
 const {chromium}=require(path.resolve(args.playwright));
 const context=await chromium.launchPersistentContext(path.join(temp,'profile'),{
  executablePath:path.resolve(args.browser),headless:true,viewport:{width:1440,height:1080},
  env:{...process.env,TEMP:temp,TMP:temp,TMPDIR:temp},downloadsPath:path.join(temp,'downloads'),
  args:['--disable-gpu','--no-first-run','--disable-extensions','--disable-background-networking',
        '--disk-cache-dir='+path.join(temp,'cache'),'--crash-dumps-dir='+path.join(temp,'crash')]
 });
 let report;const errors=[];
 try{
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  // Self-contained artifacts must not load remote resources during QA.
  await page.route('https://**',route=>route.abort());await page.route('http://**',route=>route.abort());
  await page.goto(pathToFileURL(file).href);
  await page.locator('img').evaluateAll(xs=>xs.forEach(x=>x.loading='eager'));
  await page.waitForFunction(()=>[...document.images].every(x=>x.complete&&x.naturalWidth>0));
  report=await page.evaluate(()=>({
   images:document.images.length,loadedImages:[...document.images].filter(x=>x.complete&&x.naturalWidth>0).length,
   records:document.querySelectorAll('article .block').length,
   horizontalOverflow:document.documentElement.scrollWidth>innerWidth,
   overflowingCells:[...document.querySelectorAll('.cell,td,th')].filter(x=>x.scrollWidth>x.clientWidth+2).map(x=>x.textContent.slice(0,70)),
   brokenTocLinks:[...document.querySelectorAll('nav a')].filter(x=>!document.getElementById(x.hash.slice(1))).length
  }));
  await page.screenshot({path:path.join(out,'desktop.png')});
  // Capture each visual/table for the agent to inspect; no paper-specific IDs.
  const sections=page.locator('section').filter({has:page.locator('img,table')});
  for(let i=0;i<await sections.count();i++){
   const section=sections.nth(i);const id=await section.getAttribute('id');
   if(id&&/^[A-Za-z][A-Za-z0-9_-]*$/.test(id))await section.screenshot({path:path.join(out,id+'.png')});
  }
  for(const mode of ['target','source']){
   await page.locator('[data-mode="'+mode+'"]').click();
   report[mode+'Mode']=await page.evaluate(mode=>({
    bodyClass:document.body.className,
    incorrectlyVisible:[...document.querySelectorAll(mode==='target'?'.source-text':'.target-text')].filter(x=>x.getBoundingClientRect().height>0).length
   }),mode);
  }
  await page.locator('[data-mode="both"]').click();
  // Exercise native Selection/Range events, including both directions, moving
  // and clearing a selection, table cells, and spans across multiple records.
  report.selectionHighlight=await page.evaluate(async()=>{
   const result={},selection=getSelection();
   const settle=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
   const count=()=>document.querySelectorAll('.paired-highlight').length;
   const pairs=[...document.querySelectorAll('article .columns')].filter(p=>p.querySelector(':scope > .source-text')&&p.querySelector(':scope > .target-text'));
   if(!pairs.length)return {passed:false,reason:'No paired text to verify'};
   const multi=pairs.find(p=>p.querySelectorAll('.source-text p > .aligned-sentence').length>1);
   const first=multi||pairs[0],source=first.querySelector('.source-text .aligned-sentence');
   const peer=node=>document.querySelector('[data-unit="'+node.dataset.peers.split(' ')[0]+'"]');
   const target=peer(source);
   function select(node){const range=document.createRange();range.selectNodeContents(node);selection.removeAllRanges();selection.addRange(range);}
   select(source);await settle();result.sourceToTarget=target.classList.contains('paired-highlight')&&count()===1;
   select(target);await settle();result.targetToSource=source.classList.contains('paired-highlight')&&count()===1;
   result.sentenceGranularity=Boolean(multi)&&count()===1&&document.querySelectorAll('.cell.paired-highlight,.source-text.paired-highlight,.target-text.paired-highlight').length===0;
   if(multi){
    const second=multi.querySelectorAll('.source-text p > .aligned-sentence')[1];
    select(second);await settle();result.moveWithinParagraph=count()===1&&peer(second).classList.contains('paired-highlight')&&!target.classList.contains('paired-highlight');
    const range=document.createRange();range.setStart(source,0);range.setEnd(second,second.childNodes.length);selection.removeAllRanges();selection.addRange(range);
    await settle();result.multipleSentences=count()===2&&target.classList.contains('paired-highlight')&&peer(second).classList.contains('paired-highlight');
   }
   if(pairs.length>1){
    const start=pairs[0].querySelector('.source-text .aligned-sentence'),end=pairs[1].querySelector('.source-text .aligned-sentence'),range=document.createRange();
    range.setStart(start,0);range.setEnd(end,end.childNodes.length);selection.removeAllRanges();selection.addRange(range);
    await settle();result.multipleRecords=peer(start).classList.contains('paired-highlight')&&peer(end).classList.contains('paired-highlight');
    select(end);await settle();result.moveSelection=count()===1&&!peer(start).classList.contains('paired-highlight');
   }
   const table=document.querySelector('td .source-text .aligned-sentence,th .source-text .aligned-sentence');
   if(table){select(table);await settle();result.tableCell=count()===1&&peer(table).classList.contains('paired-highlight');}
   const reordered=[...document.querySelectorAll('.aligned-sentence')].find(node=>node.dataset.peers&&node.dataset.unit.split('-').at(-1)!==node.dataset.peers.split(' ')[0].split('-').at(-1));
   if(reordered){select(reordered);await settle();result.explicitReorderedMapping=peer(reordered).classList.contains('paired-highlight');}
   const oneToMany=[...document.querySelectorAll('.aligned-sentence')].find(node=>node.dataset.peers.trim().split(' ').length>1);
   if(oneToMany){
    select(oneToMany);await settle();result.oneToMany=count()===oneToMany.dataset.peers.trim().split(' ').length&&oneToMany.dataset.peers.trim().split(' ').every(key=>document.querySelector('[data-unit="'+key+'"]').classList.contains('paired-highlight'));
    select(peer(oneToMany));await settle();result.manyToOne=oneToMany.classList.contains('paired-highlight')&&count()===1;
   }
   const range=document.createRange();range.selectNodeContents(source);range.collapse(true);selection.removeAllRanges();selection.addRange(range);
   await settle();result.collapsedClears=count()===0;
   select(source);await settle();selection.removeAllRanges();await settle();result.deselectClears=count()===0;
   select(source);await settle();document.querySelector('[data-mode="target"]').click();await settle();result.singleLanguageClears=count()===0;
   document.querySelector('[data-mode="both"]').click();selection.removeAllRanges();await settle();
   select(source);await settle();const search=document.getElementById('search');search.value='__reader_qa_no_match_8d28__';search.dispatchEvent(new Event('input'));
   await settle();result.filteredClears=count()===0;search.value='';search.dispatchEvent(new Event('input'));selection.removeAllRanges();await settle();
   result.passed=Object.values(result).every(value=>value===true);return result;
  });
  // Drag-select actual text with the mouse, then extend a Chinese selection
  // with the keyboard. These must trigger highlighting without script events.
  const paragraph=page.locator('article .columns .source-text p:has(.aligned-sentence + .aligned-sentence)').first();
  if(await paragraph.count()){
   await paragraph.scrollIntoViewIfNeeded();
   const rect=await paragraph.evaluate(p=>{
    const walker=document.createTreeWalker(p,NodeFilter.SHOW_TEXT);let node;
    while((node=walker.nextNode()))if(node.textContent.trim().length>=5)break;
    if(!node)return null;
    const r=document.createRange();r.setStart(node,0);r.setEnd(node,Math.min(5,node.length));
    const b=r.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height};
   });
   if(rect){
    await page.mouse.move(rect.x+1,rect.y+rect.height/2);await page.mouse.down();
    await page.mouse.move(rect.x+rect.width-1,rect.y+rect.height/2,{steps:8});await page.mouse.up();
    await page.waitForFunction(()=>document.querySelector('.paired-highlight'));
    report.selectionHighlight.mouseDrag=await paragraph.evaluate(p=>{
     const unit=p.querySelector('.aligned-sentence'),peer=document.querySelector('[data-unit="'+unit.dataset.peers.split(' ')[0]+'"]');
     return getSelection().toString().trim().length>0&&peer.classList.contains('paired-highlight')&&document.querySelectorAll('.paired-highlight').length===1;
    });
    await page.screenshot({path:path.join(out,'selection-highlight.png')});
    const blockId=await paragraph.evaluate(p=>p.closest('.block').id);
    const target=page.locator('#'+blockId+' .columns .target-text p').first();
    const targetRect=await target.evaluate(p=>{
     const node=document.createTreeWalker(p,NodeFilter.SHOW_TEXT).nextNode();
     const range=document.createRange();range.setStart(node,0);range.setEnd(node,Math.min(2,node.length));
     const b=range.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height};
    });
    await page.mouse.move(targetRect.x+1,targetRect.y+targetRect.height/2);await page.mouse.down();
    await page.mouse.move(targetRect.x+targetRect.width-1,targetRect.y+targetRect.height/2,{steps:8});await page.mouse.up();
    const beforeKey=await page.evaluate(()=>getSelection().toString());
    await page.keyboard.press('Shift+ArrowRight');await page.keyboard.press('Shift+ArrowRight');
    await page.waitForFunction(()=>document.querySelector('.source-text .aligned-sentence.paired-highlight'));
    report.selectionHighlight.keyboardSelection=await page.evaluate(before=>getSelection().toString().trim().length>before.trim().length&&document.querySelectorAll('.paired-highlight').length===1,beforeKey);
    await page.evaluate(()=>getSelection().removeAllRanges());
   }
  }
  report.selectionHighlight.passed=Object.values(report.selectionHighlight).every(value=>value===true);
  const query=await page.locator('article .block').first().innerText();
  const token=(query.match(/[A-Za-z]{4,}/)||query.match(/[\u4e00-\u9fff]{2,}/)||[''])[0];
  if(token){await page.locator('#search').fill(token);report.searchVisible=await page.locator('article .block:not(.hidden)').count();}
  await page.locator('#search').fill('');
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>scrollTo(0,0));
  await page.screenshot({path:path.join(out,'mobile.png')});
  report.mobileHorizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  report.mobileSelectionHighlight=await page.evaluate(async()=>{
   const source=document.querySelector('article .source-text p > .aligned-sentence'),range=document.createRange();range.selectNodeContents(source);
   getSelection().removeAllRanges();getSelection().addRange(range);
   await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
   const peer=document.querySelector('[data-unit="'+source.dataset.peers.split(' ')[0]+'"]');
   return peer.classList.contains('paired-highlight')&&document.querySelectorAll('.paired-highlight').length===1;
  });
  report.errors=errors;
 }finally{await context.close();}
 report.passed=!report.horizontalOverflow&&!report.mobileHorizontalOverflow&&!report.overflowingCells.length&&!report.brokenTocLinks&&!errors.length&&report.targetMode.incorrectlyVisible===0&&report.sourceMode.incorrectlyVisible===0&&report.searchVisible!==0&&report.selectionHighlight.passed&&report.mobileSelectionHighlight;
 fs.writeFileSync(path.join(out,'reader_audit.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report,null,2));if(!report.passed)process.exitCode=1;
})().catch(e=>{console.error(e.message);process.exitCode=1;});
