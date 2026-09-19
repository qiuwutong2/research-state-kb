"use strict";
const $=id=>document.getElementById(id), NS="http://www.w3.org/2000/svg";
const colors={source:"#389a87",method:"#5587ca",formula:"#a57dcc",experiment_plan:"#d9a041",research_file:"#c67d64",route_node:"#768998"};
const names={source:"资料来源",method:"方法",formula:"公式",experiment_plan:"实验方案",research_file:"数据 / 产物",route_node:"实验节点"};
let data={nodes:[],edges:[],domains:[]}, selected="", revision="", generation=0, previewGeneration=0, busy=false, zoom=1, pan={x:0,y:0};
$("namespace").value=new URLSearchParams(location.search).get("namespace")==="demo"?"demo":"real";
const namespace=()=>$("namespace").value;
function el(tag,text,parent,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;if(parent)parent.append(e);return e}
function svg(tag,attrs,parent){const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(parent)parent.append(e);return e}
async function api(path,params={}){const q=new URLSearchParams({namespace:namespace(),...params});const r=await fetch(path+"?"+q);if(!r.ok)throw Error((await r.json()).error||"读取失败");return r.json()}
function heading(text){el("h3",text,$("detail"))}
function text(value){el("pre",typeof value==="string"?value:JSON.stringify(value,null,2),$("detail"))}
function pick(n){selected=n.uid;render();details(n)}
function details(n){
 $("detailTitle").textContent=n.data.title||n.id;$("detail").replaceChildren();
 el("span",names[n.kind]+" · "+n.id+" v"+n.version+(n.historical?" · 历史引用版本":""),$("detail"),"tag");
 heading("领域");for(const d of n.domains.length?n.domains:["待分类"])el("span",d,$("detail"),"tag");
 text(n.classification?n.classification.data.rationale:"尚未登记领域分类；通过 classify_knowledge 提交归属与理由。");
 for(const key of ["origin","content","expression","conditions","limitations","question","goal","method","summary"]){if(n.data[key]){heading(({origin:"来源",content:"内容",expression:"公式",conditions:"适用条件",limitations:"局限",question:"问题",goal:"目标",method:"方法",summary:"摘要"})[key]);text(n.data[key])}}
 heading("引用依据 →");
 const refs=data.edges.filter(e=>e.from===n.uid);
 if(!refs.length)text("没有登记引用；来源原件可在下方查看。");
 for(const e of refs){const r=data.nodes.find(x=>x.uid===e.to);if(r)el("button",(r.data.title||r.id)+" · v"+r.version,$("detail")).onclick=()=>pick(r)}
 heading("被谁引用 ←");
 const incoming=data.edges.filter(e=>e.to===n.uid);
 if(!incoming.length)text("尚无引用记录。");
 for(const e of incoming){const r=data.nodes.find(x=>x.uid===e.from);if(r)el("button",r.data.title||r.id,$("detail")).onclick=()=>pick(r)}
 el("button","查看归档文件与来源链 ↗",$("detail")).onclick=()=>preview(n);
}
async function preview(n){
 const ticket=++previewGeneration;$("previewPanel").hidden=false;$("previewTitle").textContent="正在核验归档来源…";$("files").replaceChildren();$("preview").removeAttribute("src");
 try{const t=await api("/api/trace",{id:n.id,version:n.version});if(ticket!==previewGeneration)return;
 $("previewTitle").textContent=n.data.title+" · 归档来源（哈希已核验）";
 if(!t.files.length)el("p","此节点没有归档文件。",$("files"));
 for(const file of t.files){const url="/api/file?"+new URLSearchParams({namespace:namespace(),id:file.source_id,version:file.version});
 const b=el("button",file.title,$("files"));b.onclick=()=>{$("preview").src=url};}
 if(t.files.length)$("files").firstChild.click();
 }catch(e){if(ticket===previewGeneration)$("previewTitle").textContent="来源读取失败："+e.message}
}
function render(){
 const graph=$("graph");graph.replaceChildren();graph.setAttribute("viewBox","0 0 1100 700");
 const defs=svg("defs",{},graph),marker=svg("marker",{id:"arrow",viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:5,markerHeight:5,orient:"auto-start-reverse"},defs);svg("path",{d:"M 0 0 L 10 5 L 0 10 z",fill:"#91aca1"},marker);
 const world=svg("g",{id:"world"},graph);
 const domain=$("domain").value,kind=$("kind").value,q=$("search").value.toLocaleLowerCase().trim();
 const nodes=data.nodes.filter(n=>(!domain||(domain==="__unclassified"?n.domains.length===0:n.domains.includes(domain)))&&(!kind||n.kind===kind)&&(!q||JSON.stringify(n).toLocaleLowerCase().includes(q)));
 $("empty").hidden=nodes.length>0;
 const groups=[...new Set(nodes.flatMap(n=>n.domains.length?n.domains:["待分类"]))].sort();
 const hubs=new Map(),positions=new Map(),assigned=new Map(),loads=new Map(groups.map(g=>[g,0]));
 nodes.forEach(n=>{const ds=n.domains.length?n.domains:["待分类"];const d=[...ds].sort((a,b)=>loads.get(a)-loads.get(b)||a.localeCompare(b))[0];assigned.set(n.uid,d);loads.set(d,loads.get(d)+1)});
 groups.forEach((g,i)=>{const a=i*2*Math.PI/groups.length-Math.PI/2;hubs.set(g,{x:550+(groups.length===1?0:310*Math.cos(a)),y:350+(groups.length===1?0:220*Math.sin(a))})});
 groups.forEach(g=>{const hub=hubs.get(g),members=nodes.filter(n=>assigned.get(n.uid)===g);
 members.forEach((n,i)=>{const a=members.length<=10?i*2*Math.PI/members.length-Math.PI/2:i*2.39996323,r=members.length<=10?85:60+24*Math.sqrt(i);positions.set(n.uid,{x:hub.x+r*Math.cos(a),y:hub.y+r*Math.sin(a)})});
 svg("circle",{cx:hub.x,cy:hub.y,r:Math.max(100,62+17*Math.sqrt(members.length)),fill:"#cddfc5",opacity:.15},world);
 });
 for(const n of nodes){const p=positions.get(n.uid);for(const d of n.domains.length?n.domains:["待分类"]){const h=hubs.get(d);svg("line",{x1:p.x,y1:p.y,x2:h.x,y2:h.y,class:"membership"},world)}}
 for(const edge of data.edges){const a=positions.get(edge.from),b=positions.get(edge.to);if(!a||!b)continue;
 const len=Math.hypot(b.x-a.x,b.y-a.y)||1,dx=(b.x-a.x)/len,dy=(b.y-a.y)/len;
 svg("line",{x1:a.x+dx*12,y1:a.y+dy*12,x2:b.x-dx*15,y2:b.y-dy*15,class:"link"+(edge.from===selected||edge.to===selected?" active-link":""),"marker-end":"url(#arrow)"},world);
 }
 for(const [name,p] of hubs){svg("circle",{cx:p.x,cy:p.y,r:5,fill:"#82966d"},world);const t=svg("text",{x:p.x,y:p.y-15,"text-anchor":"middle","font-size":14,"font-weight":700},world);t.textContent=name}
 for(const n of nodes){const p=positions.get(n.uid),g=svg("g",{class:"node"+(n.uid===selected?" selected":""),tabindex:0,role:"button","aria-label":n.data.title||n.id},world);
 svg("rect",{x:p.x-60,y:p.y-14,width:120,height:46,fill:"transparent"},g);
 svg("circle",{cx:p.x,cy:p.y,r:n.kind==="source"?11:8,fill:colors[n.kind]||"#888",stroke:"white","stroke-width":2,opacity:n.historical?.55:1},g);
 svg("title",{},g).textContent=(n.data.title||n.id)+" · v"+n.version;
 if(nodes.length<=80||n.uid===selected){const t=svg("text",{x:p.x,y:p.y+25,"text-anchor":"middle","font-size":10},g);const title=n.data.title||n.id;t.textContent=title.length>16?title.slice(0,15)+"…":title}
 g.onclick=()=>pick(n);g.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();pick(n)}};
 }
 transform();
}
function transform(){const w=document.getElementById("world");if(w)w.setAttribute("transform",`translate(${550+pan.x} ${350+pan.y}) scale(${zoom}) translate(-550 -350)`)}
function scale(f){zoom=Math.max(.25,Math.min(5,zoom*f));transform()}
$("plus").onclick=()=>scale(1.2);$("minus").onclick=()=>scale(1/1.2);$("reset").onclick=()=>{zoom=1;pan={x:0,y:0};transform()};
$("graph").addEventListener("wheel",e=>{e.preventDefault();scale(e.deltaY<0?1.1:1/1.1)},{passive:false});
let drag=null;
$("graph").addEventListener("pointerdown",e=>{if(e.target.closest(".node"))return;drag={x:e.clientX,y:e.clientY,px:pan.x,py:pan.y};$("graph").setPointerCapture(e.pointerId)});
$("graph").addEventListener("pointermove",e=>{if(!drag)return;const rect=$("graph").getBoundingClientRect(),s=Math.min(rect.width/1100,rect.height/700);pan={x:drag.px+(e.clientX-drag.x)/s,y:drag.py+(e.clientY-drag.y)/s};transform()});
$("graph").addEventListener("pointerup",()=>drag=null);$("graph").addEventListener("pointercancel",()=>drag=null);
async function refresh(force=false){
 if(busy)return;busy=true;const ticket=generation;
 try{const next=await api("/api/knowledge-graph");if(ticket!==generation)return;
 $("sync").textContent="● 已同步 "+new Date().toLocaleTimeString()+" · 3 秒自动更新";
 if(force||revision!==next.revision){data=next;revision=next.revision;const keep=$("domain").value;$("domain").replaceChildren();
 for(const [v,label] of [["","全部领域"],["__unclassified","待分类"],...data.domains.map(d=>[d.name,d.name+" · "+d.count])]){const o=el("option",label,$("domain"));o.value=v}
 if([...$("domain").options].some(o=>o.value===keep))$("domain").value=keep;
 $("stats").replaceChildren();for(const [count,label] of [[data.domains.length,"已登记领域"],[data.nodes.filter(n=>!n.historical).length,"当前知识记录"],[data.edges.length,"版本引用"]]){const s=el("span","",$("stats"));el("b",String(count),s);el("span",label,s)}
 render();const n=data.nodes.find(n=>n.uid===selected);if(n)details(n);
 }
 }catch(e){if(ticket===generation)$("sync").textContent="连接失败，显示上次快照："+e.message}finally{busy=false}
}
$("namespace").onchange=()=>{generation++;previewGeneration++;revision="";selected="";data={nodes:[],edges:[],domains:[]};$("previewPanel").hidden=true;$("preview").removeAttribute("src");$("detailTitle").textContent="选择一条知识";$("detail").textContent="点击节点查看依据。";$("stats").replaceChildren();render();$("routes").href="/?namespace="+namespace();history.replaceState(null,"","?namespace="+namespace());refresh(true)};
$("routes").href="/?namespace="+namespace();
$("closePreview").onclick=()=>{previewGeneration++;$("previewPanel").hidden=true;$("preview").removeAttribute("src")};
$("refresh").onclick=()=>refresh(true);$("search").oninput=render;$("domain").onchange=render;$("kind").onchange=render;
setInterval(()=>{if(!document.hidden)refresh()},3000);document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh()});refresh();
