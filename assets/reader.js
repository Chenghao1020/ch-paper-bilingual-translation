
const blocks=[...document.querySelectorAll('article .block')];
const searchableText=new Map(blocks.map(b=>[b,(b.textContent+' '+[...b.querySelectorAll('.math-inline')].map(x=>x.dataset.original).join(' ')).toLowerCase()]));
function mode(value){document.body.classList.remove('target-only','source-only');if(value!=='both')document.body.classList.add(value+'-only');document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===value));schedulePairHighlight();}
document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',()=>mode(b.dataset.mode)));
document.getElementById('search').addEventListener('input',e=>{const q=e.target.value.trim().toLowerCase();let n=0;for(const b of blocks){const show=!q||searchableText.get(b).includes(q);b.classList.toggle('hidden',!show);if(show)n++;}document.getElementById('count').textContent=q?'匹配 '+n+' 个文本块':'';schedulePairHighlight();});

// Counterparts come from reviewed sentence alignment, never paragraph position
// or a guessed sentence index. One sentence may correspond to several units.
const bilingualText=[...document.querySelectorAll('article .aligned-sentence')];
const sentenceUnits=new Map(bilingualText.map(node=>[node.dataset.unit,node]));
let highlighted=new Set(),highlightFrame=0;
function visible(node){return node.getClientRects().length>0;}
function selectedText(range,node){
 if(!range.intersectsNode(node))return false;
 const clipped=document.createRange();clipped.selectNodeContents(node);
 if(range.compareBoundaryPoints(Range.START_TO_START,clipped)>0)clipped.setStart(range.startContainer,range.startOffset);
 if(range.compareBoundaryPoints(Range.END_TO_END,clipped)<0)clipped.setEnd(range.endContainer,range.endOffset);
 return !clipped.collapsed&&clipped.toString().trim().length>0;
}
function updatePairHighlight(){
 highlightFrame=0;
 const next=new Set(),selection=window.getSelection();
 if(selection&&!selection.isCollapsed&&!document.body.matches('.source-only,.target-only')){
  for(const node of bilingualText){
   if(!visible(node))continue;
   let selected=false;
   for(let i=0;i<selection.rangeCount;i++)if(selectedText(selection.getRangeAt(i),node)){selected=true;break;}
   if(!selected)continue;
   for(const key of node.dataset.peers.split(' ')){
    const peer=sentenceUnits.get(key);if(peer&&visible(peer))next.add(peer);
   }
  }
 }
 for(const node of highlighted)if(!next.has(node))node.classList.remove('paired-highlight');
 for(const node of next)if(!highlighted.has(node))node.classList.add('paired-highlight');
 highlighted=next;
}
function schedulePairHighlight(){if(!highlightFrame)highlightFrame=requestAnimationFrame(updatePairHighlight);}
document.addEventListener('selectionchange',schedulePairHighlight);
