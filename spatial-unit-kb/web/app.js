"use strict";
const $ = id => document.getElementById(id);
const labels = {start:"开始",middle:"推进",end:"阶段总结",planned:"计划中",running:"报告执行中",completed:"报告已完成",failed:"报告失败",paused:"暂停",abandoned:"未采用 / 放弃"};
const fields = {title:"节点名称",stage:"阶段",status:"状态",goal:"目标",method:"方法",rationale:"思路与依据",parameters:"参数",knowledge:"知识依据",datasets:"数据",artifacts:"产物",change_reason:"变更原因",summary:"阶段记录",open_questions:"未决问题"};
let graph = {nodes:[],edges:[]}, selected=null, zoom=1, width=900, height=500, generation=0, previewGeneration=0, compareGeneration=0;
function el(tag, text, cls){const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;}
function notice(text,error=false){$("notice").textContent=text;$("notice").className=error?"notice error":"notice";}
async function api(path, params={}){const query=new URLSearchParams({...params,namespace:$("namespace").value});const r=await fetch("/api/"+path+"?"+query);const data=await r.json();if(!r.ok)throw Error(data.error||"请求失败");return data;}
function refText(ref){const all=graph.nodes.flatMap(n=>Object.values(n.citations).flat());const match=all.find(x=>x.id===ref.id&&x.version===ref.version);return (match?match.title+" · ":"")+ref.id+"@"+ref.version;}
function format(value){if(Array.isArray(value)&&value.every(x=>x&&x.id))return value.length?value.map(refText).join("\n"):"无";if(typeof value==="string")return labels[value]||value;return JSON.stringify(value,null,2);}
function delta(node,parent){if(!parent)return [];const a=parent.data,b=node.data,out=[];if(a.method!==b.method)out.push(["方法变更",""]);if(JSON.stringify(a.parameters)!==JSON.stringify(b.parameters))out.push(["参数调整","param"]);if(b.knowledge.some(r=>!a.knowledge.some(x=>x.id===r.id&&x.version===r.version)))out.push(["新增知识",""]);if(b.datasets.some(r=>!a.datasets.some(x=>x.id===r.id&&x.version===r.version)))out.push(["新增数据","data"]);return out;}
function renderCounts(){const values=[["节点",graph.nodes.length],["分支点",graph.nodes.filter(n=>graph.edges.filter(e=>e.from===n.id).length>1).length],["总结",graph.nodes.filter(n=>n.data.stage==="end").length]];$("counts").replaceChildren(...values.map(([name,count])=>{const d=el("div",undefined,"stat");d.append(el("b",String(count)),el("span",name));return d;}));}
function renderGraph(){
 const world=$("world");world.replaceChildren();$("empty").hidden=!!graph.nodes.length;
 if(!graph.nodes.length){$("empty").textContent=$("namespace").value==="real"?"尚无真实实验路线。\n请让 Agent 登记路线节点；不会自动用演示记录填充。":"尚无演示路线。\n在项目目录运行 python scripts/route_demo.py";width=900;height=500;applyZoom();return;}
 const depth={},lanes={},pos={};
 for(const n of graph.nodes){depth[n.id]=n.data.parents.length?Math.max(...n.data.parents.map(p=>depth[p.id]??0))+1:0;const d=depth[n.id];if(!lanes[d])lanes[d]=[];lanes[d].push(n);}
 for(const [level,nodes] of Object.entries(lanes)){world.append(Object.assign(el("div","STEP "+String(Number(level)+1).padStart(2,"0"),"stage-label"),{style:"left:"+(30+Number(level)*300)+"px"}));nodes.forEach((n,i)=>pos[n.id]={x:30+Number(level)*300,y:50+i*225});}
 width=Math.max(...Object.values(pos).map(p=>p.x))+285;height=Math.max(490,...Object.values(pos).map(p=>p.y+210));
 const ns="http://www.w3.org/2000/svg",svg=document.createElementNS(ns,"svg");svg.setAttribute("width",width);svg.setAttribute("height",height);
 const defs=document.createElementNS(ns,"defs"),marker=document.createElementNS(ns,"marker");marker.setAttribute("id","arrow");marker.setAttribute("viewBox","0 0 10 10");marker.setAttribute("refX","9");marker.setAttribute("refY","5");marker.setAttribute("markerWidth","6");marker.setAttribute("markerHeight","6");marker.setAttribute("orient","auto");const tri=document.createElementNS(ns,"path");tri.setAttribute("d","M 0 0 L 10 5 L 0 10 z");tri.setAttribute("fill","#a6bbb0");marker.append(tri);defs.append(marker);svg.append(defs);
 for(const edge of graph.edges){const a=pos[edge.from],b=pos[edge.to];if(!a||!b)continue;const path=document.createElementNS(ns,"path");path.setAttribute("d",`M ${a.x+250} ${a.y+82} C ${a.x+280} ${a.y+82}, ${b.x-30} ${b.y+82}, ${b.x-8} ${b.y+82}`);path.setAttribute("fill","none");path.setAttribute("stroke","#a6bbb0");path.setAttribute("stroke-width","1.7");path.setAttribute("marker-end","url(#arrow)");svg.append(path);}
 world.append(svg);
 const q=$("search").value.trim().toLowerCase();
 for(const node of graph.nodes){const d=node.data,box=el("button",undefined,"route-node"+(selected===node.id?" selected":""));box.style.left=pos[node.id].x+"px";box.style.top=pos[node.id].y+"px";box.dataset.id=node.id;
 if(q&&!JSON.stringify(node).toLowerCase().includes(q))box.classList.add("dim");
 const top=el("div",undefined,"node-top");top.append(el("span",labels[d.stage]),el("span",node.id));box.append(top,el("strong",d.title),el("div",d.goal,"goal"));
 const badges=el("div",undefined,"badges");badges.append(el("span",labels[d.status],"badge status"));
 const seen=new Set();for(const p of d.parents){for(const [label,cls] of delta(node,graph.nodes.find(x=>x.id===p.id))){if(!seen.has(label)){badges.append(el("span",label,"badge "+cls));seen.add(label);}}}box.append(badges);box.onclick=()=>selectNode(node.id);world.append(box);
 }
 applyZoom();
}
function applyZoom(){$("world").style.width=width+"px";$("world").style.height=height+"px";$("world").style.transform="scale("+zoom+")";$("extent").style.width=width*zoom+"px";$("extent").style.height=height*zoom+"px";$("scale").textContent=Math.round(zoom*100)+"%";}
function section(title,text){const d=el("section",undefined,"detail-section");d.append(el("h4",title),el("p",text));return d;}
async function showReference(ref){
 const ticket=++previewGeneration;
 try{const trace=await api("trace",{id:ref.id,version:ref.version});if(ticket!==previewGeneration)return;
 const d=$("sourceFiles");d.replaceChildren();if(!trace.files.length){d.append(el("p","没有可预览的文件"));return;}
 for(const f of trace.files){const b=el("button",f.title+" · "+f.source_id+"@"+f.version);b.onclick=()=>previewFile(f);d.append(b);}previewFile(trace.files[0]);
 }catch(e){if(ticket===previewGeneration)notice("来源核验失败："+e.message,true);}
}
function previewFile(file){$("previewPanel").hidden=false;$("previewTitle").textContent=file.title+" · "+file.source_id+"@"+file.version;
 const url="/api/file?"+new URLSearchParams({namespace:$("namespace").value,id:file.source_id,version:file.version});
 $("preview").src=url;$("openFile").href=url;$("previewPanel").scrollIntoView({behavior:"smooth",block:"nearest"});}
function selectNode(id){
 selected=id;previewGeneration++;$("previewPanel").hidden=true;$("preview").removeAttribute("src");const node=graph.nodes.find(n=>n.id===id);if(!node)return;const d=node.data;
 $("nodeId").textContent=id+"@"+node.version;const pane=$("detail");pane.replaceChildren(el("h3",d.title),el("span",labels[d.stage]+" · "+labels[d.status],"pill"),el("p","记录时间："+new Date(node.created_at).toLocaleString(),"mono"));
 pane.append(section("当前目标",d.goal),section("采用方法",d.method),section("思路与选择依据",d.rationale),section("为什么从上一步转向这里",d.change_reason));
 const params=section("当前参数","");const grid=el("div",undefined,"params");for(const [k,v]of Object.entries(d.parameters)){grid.append(el("span",k),el("span",format(v)));}if(!Object.keys(d.parameters).length)grid.append(el("span","无登记参数"));params.append(grid);pane.append(params);
 for(const [group,title] of [["knowledge","参考了谁 / 方法与思路"],["datasets","使用的数据"],["artifacts","关联产物"]]){const area=section(title,"");const items=node.citations[group];if(!items.length)area.append(el("p","未登记","muted"));for(const ref of items){const r=el("div",undefined,"ref");r.append(el("div",ref.title,"title"),el("div",ref.id+"@"+ref.version+" · "+ref.kind,"meta"));if(ref.attribution)r.append(el("div","来源 / 作者："+ref.attribution,"meta"));if(/^https?:\/\//i.test(ref.attribution)){const link=el("a","打开原网址");link.href=ref.attribution;link.target="_blank";link.rel="noopener noreferrer";r.append(link);}if(ref.basis)r.append(el("div","采用方式："+({direct:"直接采用",adapted:"改造",original:"原创新设计"}[ref.basis]||ref.basis),"meta"));r.append(Object.assign(el("button","核对来源并预览"),{onclick:()=>showReference(ref)}));area.append(r);}pane.append(area);}
 const sources=section("可打开的来源文件","");const list=el("div",undefined,"source-actions");list.id="sourceFiles";sources.append(list);pane.append(sources,section("阶段记录（由记录者报告）",d.summary),section("遗留问题",d.open_questions));
 if(d.parents.length){const branch=section("前序节点","");for(const p of d.parents){const b=el("button",p.id+" → 本节点");b.onclick=()=>{$("compareA").value=p.id;$("compareB").value=id;compare();};branch.append(b);}pane.append(branch);$("compareA").value=d.parents[0].id;}else $("compareA").value=id;
 $("compareB").value=id;renderGraph();if(d.parents.length)compare();else $("comparison").textContent="选择两个节点，对比目标、方法、参数和引用版本。";
}
async function compare(){if(!$("compareA").value||!$("compareB").value)return;const ticket=generation, comparisonTicket=++compareGeneration;try{const data=await api("compare",{first:$("compareA").value,second:$("compareB").value});if(ticket!==generation||comparisonTicket!==compareGeneration)return;const target=$("comparison");target.replaceChildren();const keys=Object.keys(data.changes);if(!keys.length){target.textContent="两个节点的登记内容没有差异。";return;}
 const table=el("table",undefined,"diff"),head=el("thead"),hr=el("tr");["变更项",data.first+" · 之前",data.second+" · 之后"].forEach(t=>hr.append(el("th",t)));head.append(hr);table.append(head);const body=el("tbody");
 for(const key of keys){if(key==="parameters"){for(const [p,v]of Object.entries(data.parameter_changes)){const row=el("tr");row.append(el("td","参数 · "+p),el("td",v.before_present?format(v.before):"未设置"),el("td",v.after_present?format(v.after):"已移除"));body.append(row);}}else{const row=el("tr");row.append(el("td",fields[key]||key),el("td",format(data.changes[key].before)),el("td",format(data.changes[key].after)));body.append(row);}}table.append(body);target.append(table);
 }catch(e){notice(e.message,true);}}
async function load(){const ticket=++generation;previewGeneration++;$("previewPanel").hidden=true;$("preview").removeAttribute("src");notice("正在读取本机记录…");try{
 const g=await api("graph");if(ticket!==generation)return;const chosen=$("experiment").value;
 $("experiment").replaceChildren(...g.experiments.map(id=>{const o=el("option",id);o.value=id;return o;}));if(g.experiments.includes(chosen))$("experiment").value=chosen;
 const experiment=$("experiment").value;graph={...g,nodes:g.nodes.filter(n=>n.data.experiment_id===experiment)};const ids=new Set(graph.nodes.map(n=>n.id));graph.edges=g.edges.filter(e=>ids.has(e.from)&&ids.has(e.to));
 for(const name of ["compareA","compareB"]){$(name).replaceChildren(...graph.nodes.map(n=>{const o=el("option",n.data.title+" · "+n.id);o.value=n.id;return o;}));}
 renderCounts();renderGraph();if(graph.nodes.length)selectNode(ids.has(selected)?selected:graph.nodes[0].id);else{$("detail").replaceChildren(el("div","暂无路线节点","placeholder"));$("nodeId").textContent="";$("comparison").textContent="登记至少两个节点后即可比较。";}
 notice($("namespace").value==="demo"?"当前是合成演示：所有节点和结果均为教学内容，不是真实研究。":"当前是真实项目记录：执行状态由记录者报告，未独立复算。");
 }catch(e){if(ticket===generation)notice(e.message,true);}}
$("namespace").onchange=()=>{selected=null;$("experiment").replaceChildren();load();};$("experiment").onchange=load;$("refresh").onclick=load;$("search").oninput=renderGraph;$("compare").onclick=compare;
$("zoomIn").onclick=()=>{zoom=Math.min(1.5,zoom+.1);applyZoom();};$("zoomOut").onclick=()=>{zoom=Math.max(.4,zoom-.1);applyZoom();};$("resetZoom").onclick=()=>{zoom=1;applyZoom();$("canvas").scrollTo(0,0);};$("closePreview").onclick=()=>{$("previewPanel").hidden=true;$("preview").removeAttribute("src");};
const initial=new URLSearchParams(location.search).get("namespace");if(initial==="demo")$("namespace").value="demo";load();

$("fitZoom").onclick=()=>{zoom=Math.min(1,Math.max(.4,($("canvas").clientWidth-15)/width));applyZoom();$("canvas").scrollTo(0,0);};

const knowledgeLink = document.getElementById("knowledgeLink");
function syncKnowledgeLink(){knowledgeLink.href="/knowledge?namespace="+document.getElementById("namespace").value}
document.getElementById("namespace").addEventListener("change",syncKnowledgeLink);syncKnowledgeLink();
