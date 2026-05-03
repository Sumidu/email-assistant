(function(){
"use strict";

// ─── State ────────────────────────────────────────────────────────────────
let currentEmail=null,currentResponse="",currentFolder=null,currentAccountId=null;
let emailOffset=0;const PAGE_SIZE=60;
let allEmailsLocal=[];
let taskPollInterval=null,searchTimer=null,accountsCache=[];
let autoSyncTimer=null,lastAutoSyncAt={};
let discoveredFolders=[];  // from IMAP discovery
let calendarEvents=[];
let calendarWeekStart=null;

// ─── Theme ────────────────────────────────────────────────────────────────
const html=document.documentElement,themeToggle=document.getElementById("theme-toggle");
function applyTheme(t){html.setAttribute("data-theme",t);themeToggle.textContent=t==="dark"?"☀":"☾";localStorage.setItem("mail-theme",t);}
applyTheme(localStorage.getItem("mail-theme")||"light");
themeToggle.addEventListener("click",()=>applyTheme(html.getAttribute("data-theme")==="dark"?"light":"dark"));

// ─── Layout controls ─────────────────────────────────────────────────────
const appShell=document.getElementById("app");
function applyFoldersCollapsed(collapsed){
  appShell.classList.toggle("folders-collapsed",collapsed);
  appShell.classList.toggle("folders-open",!collapsed);
  localStorage.setItem("mail-folders-collapsed",collapsed?"1":"0");
}
applyFoldersCollapsed(localStorage.getItem("mail-folders-collapsed")==="1"||window.innerWidth<950);
document.getElementById("folders-collapse").addEventListener("click",()=>applyFoldersCollapsed(true));
document.getElementById("folders-rail").addEventListener("click",()=>applyFoldersCollapsed(false));

// ─── Modal helpers ────────────────────────────────────────────────────────
function openModal(id){document.getElementById(id).classList.add("open");}
function closeModal(id){document.getElementById(id).classList.remove("open");}
document.querySelectorAll(".modal-close,[data-close]").forEach(el=>{
  el.addEventListener("click",()=>closeModal(el.dataset.close||el.closest(".modal-overlay").id));
});
document.querySelectorAll(".modal-overlay").forEach(o=>{
  o.addEventListener("click",e=>{if(e.target===o)o.classList.remove("open");});
});
document.addEventListener("keydown",e=>{
  if(e.key==="Escape")document.querySelectorAll(".modal-overlay.open").forEach(m=>m.classList.remove("open"));
});

// ─── Tab nav ──────────────────────────────────────────────────────────────
let settingsActiveTab="tab-accounts";
function switchTab(tabId){
  settingsActiveTab=tabId;
  document.querySelectorAll(".tab-btn").forEach(b=>b.classList.toggle("active",b.dataset.tab===tabId));
  document.querySelectorAll(".tab-pane").forEach(p=>p.classList.toggle("active",p.id===tabId));
  if(tabId==="tab-logs")loadDebugLog();
}
document.querySelectorAll(".tab-btn").forEach(btn=>btn.addEventListener("click",()=>{
  switchTab(btn.dataset.tab);
  settingsFooterMode(btn.dataset.tab==="tab-logs"?"logs":"list");
}));

function settingsFooterMode(mode){
  const back=document.getElementById("btn-acct-back");
  const save=document.getElementById("btn-save-settings");
  back.style.display=mode==="edit"||mode==="new"?"":"none";
  save.style.display=mode==="logs"?"none":"";
  save.textContent=mode==="new"?"Add Account":mode==="edit"?"Save Account":"Save";
}

// ─── Status ───────────────────────────────────────────────────────────────
const statusDot=document.getElementById("status-dot"),statusMsg=document.getElementById("status-msg"),statusModel=document.getElementById("status-model");
const activeLlmSelect=document.getElementById("active-llm-select");
activeLlmSelect.className="status-select";
function setStatus(msg,state="idle"){
  statusMsg.textContent=msg;
  statusDot.className="sb-dot"+(state==="busy"?" amber":state==="ok"?" green":state==="err"?" red":"");
}

async function refreshFinishedToday(){
  try{
    const data=await fetch("/api/stats/today").then(r=>r.json());
    const n=data.finished_today||0;
    document.getElementById("finished-today-count").textContent=`${n} finished today`;
  }catch{}
}

// ─── Floating tooltip ─────────────────────────────────────────────────────
const floatingTooltip=document.createElement("div");
floatingTooltip.id="floating-tooltip";
document.body.appendChild(floatingTooltip);

function positionFloatingTooltip(anchor){
  const tip=floatingTooltip;
  const r=anchor.getBoundingClientRect();
  const margin=10;
  const maxLeft=window.innerWidth-tip.offsetWidth-margin;
  let left=Math.min(Math.max(margin,r.left+r.width/2-tip.offsetWidth*.35),maxLeft);
  let top=r.bottom+8;
  if(top+tip.offsetHeight+margin>window.innerHeight)top=r.top-tip.offsetHeight-8;
  tip.style.left=`${Math.max(margin,left)}px`;
  tip.style.top=`${Math.max(margin,top)}px`;
}

function showFloatingTooltip(anchor){
  const text=anchor.dataset.tip||anchor.getAttribute("title")||"";
  if(!text)return;
  floatingTooltip.textContent=text;
  floatingTooltip.classList.add("open");
  positionFloatingTooltip(anchor);
}

function hideFloatingTooltip(){
  floatingTooltip.classList.remove("open");
}

document.addEventListener("mouseover",e=>{
  const anchor=e.target.closest?.(".acct-info-btn[data-tip]");
  if(anchor)showFloatingTooltip(anchor);
});
document.addEventListener("mouseout",e=>{
  const anchor=e.target.closest?.(".acct-info-btn[data-tip]");
  if(anchor&&!anchor.contains(e.relatedTarget))hideFloatingTooltip();
});
document.addEventListener("scroll",hideFloatingTooltip,true);
window.addEventListener("resize",hideFloatingTooltip);

// ─── Progress drawer ──────────────────────────────────────────────────────
const progressDrawer=document.getElementById("progress-drawer");
const progressLog=document.getElementById("progress-log");
const pdBar=document.getElementById("pd-bar");
let progressMinimized=localStorage.getItem("progress-minimized")==="1";
document.getElementById("pd-close").addEventListener("click",()=>progressDrawer.classList.remove("open"));
document.getElementById("pd-minimize").addEventListener("click",()=>{
  progressMinimized=!progressMinimized;
  localStorage.setItem("progress-minimized",progressMinimized?"1":"0");
  progressDrawer.classList.toggle("minimized",progressMinimized);
});

function showProgress(lines,progressPct){
  progressDrawer.classList.add("open");
  progressDrawer.classList.toggle("minimized",progressMinimized);
  progressDrawer.dataset.latest=lines[lines.length-1]||"Task running";
  progressLog.innerHTML=lines.map((l,i)=>`<div class="pl-line${i===lines.length-1?" latest":""}">${escHtml(l)}</div>`).join("");
  progressLog.scrollTop=progressLog.scrollHeight;
  pdBar.style.width=progressPct+"%";
}
function hideProgress(){progressDrawer.classList.remove("open");pdBar.style.width="0%";}

// ─── Task polling ─────────────────────────────────────────────────────────
let totalExpected=0,taskPollTicks=0,kbLiveRefreshBusy=false;
function isKnowledgeTask(label){return String(label||"").toLowerCase().includes("knowledge");}
function startTaskPoll(label,expectedSteps,onDone){
  totalExpected=expectedSteps||0;
  taskPollTicks=0;
  setStatus(label+"…","busy");
  progressLog.innerHTML="";
  progressDrawer.classList.add("open");
  progressDrawer.classList.toggle("minimized",progressMinimized);
  clearInterval(taskPollInterval);
  taskPollInterval=setInterval(async()=>{
    taskPollTicks++;
    const s=await fetch("/api/task_status").then(r=>r.json());
    const lines=s.progress||[];
    const pct=totalExpected>0?Math.min(99,Math.round(lines.length/totalExpected*100)):0;
    if(lines.length)showProgress(lines,pct);
    if(s.message)setStatus(s.message,"busy");
    if(isKnowledgeTask(label)&&taskPollTicks%4===0)refreshKnowledgeIndicators();
    if(!s.running){
      clearInterval(taskPollInterval);taskPollInterval=null;
      const ok=s.result&&s.result.success!==false;
      setStatus(ok?"Done — "+label:"Error: "+(s.result?.error||"?"),ok?"ok":"err");
      showProgress(lines,100);
      setTimeout(hideProgress,4000);
      if(isKnowledgeTask(label))await refreshKnowledgeIndicators();
      if(onDone)onDone(s.result);
    }
  },800);
}

// ─── Folder helpers ───────────────────────────────────────────────────────
const FOLDER_ICONS={inbox:"📬",sent:"📤",finished:"✓",done:"✓",drafts:"📝",trash:"🗑",deleted:"🗑",junk:"⚠",spam:"⚠",archive:"🗄",starred:"★",flagged:"⚑"};
function folderIcon(n){const k=n.toLowerCase();for(const[key,ico]of Object.entries(FOLDER_ICONS))if(k.includes(key))return ico;return"📁";}
function folderDisplayName(n){return n.replace(/^(inbox[./])/i,"").trim()||n;}

// ─── Load folders ─────────────────────────────────────────────────────────
const folderListEl=document.getElementById("folder-list"),maillistTitle=document.getElementById("maillist-title");
const emailCount=document.getElementById("email-count"),emailListEl=document.getElementById("email-list"),loadMoreBtn=document.getElementById("load-more");
const searchInput=document.getElementById("search-input");

async function loadFolders(){
  try{
    const[folders,accounts]=await Promise.all([
      fetch("/api/folders").then(r=>r.json()),
      fetch("/api/accounts").then(r=>r.json()),
    ]);
    accountsCache=accounts;
    setupAutoSyncTimer();
    if(!accounts.length){
      folderListEl.innerHTML='<div style="color:var(--dim);padding:14px;font-size:10px;text-align:center;line-height:1.8;">No accounts.<br>Open Settings to add one.</div>';
      return;
    }
    const byAccount={};
    for(const f of folders){const aid=f.account_id||"default";if(!byAccount[aid])byAccount[aid]=[];byAccount[aid].push(f);}
    let h="";
    for(const acct of accounts){
      const aid=acct.id,acctFolders=byAccount[aid]||[];
      h+=`<div class="acct-header"><span class="acct-dot"></span><span class="acct-name">${escHtml(acct.name)}</span><span class="acct-info-btn" data-account-info="${escHtml(aid)}" data-tip="Loading account info...">i</span><button class="acct-sync-btn" data-account-id="${escHtml(aid)}" title="Sync ${escHtml(acct.name)}">&#8635;</button></div>`;
      if(!acctFolders.length)h+=`<div style="padding:5px 22px;color:var(--dim);font-size:10px;">No emails — sync first</div>`;
      else for(const f of acctFolders)h+=`<div class="folder-item" data-folder="${escHtml(f.folder)}" data-account-id="${escHtml(aid)}"><span class="f-ico">${folderIcon(f.folder)}</span><span class="f-name">${escHtml(folderDisplayName(f.folder))}</span><span class="f-count">${f.count}</span></div>`;
    }
    folderListEl.innerHTML=h;
    folderListEl.querySelectorAll(".folder-item").forEach(el=>el.addEventListener("click",()=>selectFolder(el.dataset.folder,el.dataset.accountId,el)));
    folderListEl.querySelectorAll("[data-account-info]").forEach(loadAccountInfoTip);
    folderListEl.querySelectorAll(".acct-sync-btn").forEach(btn=>btn.addEventListener("click",e=>{e.stopPropagation();syncAccount(btn.dataset.accountId);}));
    if(currentFolder&&currentAccountId){
      const match=folderListEl.querySelector(`.folder-item[data-folder="${CSS.escape(currentFolder)}"][data-account-id="${CSS.escape(currentAccountId)}"]`);
      if(match)match.classList.add("selected");
    }else{const first=folderListEl.querySelector(".folder-item");if(first)first.click();}
  }catch(err){setStatus("Error loading folders: "+err.message,"err");}
}

function selectFolder(folder,accountId,el){
  document.querySelectorAll(".folder-item").forEach(x=>x.classList.remove("selected"));
  if(el)el.classList.add("selected");
  currentFolder=folder;currentAccountId=accountId;emailOffset=0;
  maillistTitle.textContent=folderDisplayName(folder).toUpperCase();
  searchInput.value="";loadEmailList();
}

function syncAccount(accountId){
  if(taskPollInterval){setStatus("A task is already running","err");return;}
  const acct=accountsCache.find(a=>a.id===accountId);
  const label=acct?"Sync "+acct.name:"Sync";
  const folders=(acct?.imap?.sync_folders||[]).length||(acct?2:2);
  fetch("/api/sync",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({account_id:accountId})})
    .then(()=>startTaskPoll(label,folders*3,()=>loadFolders()))
    .catch(err=>setStatus("Sync error: "+err.message,"err"));
}

function setupAutoSyncTimer(){
  clearInterval(autoSyncTimer);
  autoSyncTimer=setInterval(()=>{
    if(taskPollInterval)return;
    const now=Date.now();
    const acct=(accountsCache||[]).find(a=>{
      if(!a.imap?.auto_sync)return false;
      const mins=Math.max(1,parseInt(a.imap.sync_interval_minutes)||5);
      return now-(lastAutoSyncAt[a.id]||0)>=mins*60000;
    });
    if(!acct)return;
    lastAutoSyncAt[acct.id]=now;
    setStatus(`Auto-sync: ${acct.name}`,"busy");
    syncAccount(acct.id);
  },60000);
}

// ─── Email list ───────────────────────────────────────────────────────────
async function loadEmailList(append=false,{preserveSelection=false}={}){
  if(!currentFolder)return;
  try{
    const selectedId=preserveSelection?currentEmail?.id:null;
    const q=searchInput.value.trim();
    const qs=new URLSearchParams({
      limit:String(PAGE_SIZE),
      offset:String(emailOffset),
      folder:currentFolder,
      account_id:currentAccountId||"",
    });
    if(q)qs.set("q",q);
    const emails=await fetch(`/api/emails?${qs.toString()}`).then(r=>r.json());
    if(!append)allEmailsLocal=emails;else allEmailsLocal=allEmailsLocal.concat(emails);
    const hasMore=emails.length>=PAGE_SIZE;
    emailCount.textContent=q
      ?`${allEmailsLocal.length}${hasMore?"+":""} found`
      :(allEmailsLocal.length>=PAGE_SIZE?allEmailsLocal.length+"+":""+allEmailsLocal.length);
    renderEmailList(emails,append);
    loadMoreBtn.style.display=emails.length>=PAGE_SIZE?"block":"none";
    if(selectedId){
      const row=emailListEl.querySelector(`.email-item[data-id="${CSS.escape(selectedId)}"]`);
      if(row)row.classList.add("selected");
    }
    return emails;
  }catch(err){setStatus("Error: "+err.message,"err");}
}

function renderEmailList(emails,append=false){
  if(!append){
    if(!emails.length){emailListEl.innerHTML='<div style="color:var(--dim);padding:24px;text-align:center;font-size:10.5px;">No messages.</div>';return;}
    emailListEl.innerHTML="";
  }
  emails.forEach(e=>{
    const div=document.createElement("div");div.className="email-item";div.dataset.id=e.id;
    const matches=e.knowledge_matches||[];
    const badgeTitle=matches.length?`Knowledge: ${matches.map(m=>m.email||m.name).join(", ")}`:"";
    const primaryKb=matches[0]?.file||"";
    const badge=matches.length?`<button class="ei-kb-badge" data-kb-file="${escHtml(primaryKb)}" title="${escHtml(badgeTitle)}">&#9670; KB</button>`:"";
    const isFinished=(e.folder||currentFolder)==="Finished";
    const action=isFinished
      ?`<button class="ei-finish-btn unfinish" data-unfinish-id="${escHtml(e.id)}" title="Unarchive">&#8634;</button>`
      :`<button class="ei-finish-btn" data-finish-id="${escHtml(e.id)}" title="Done">&#10003;</button>`;
    div.innerHTML=`<div class="ei-main"><div class="ei-from"><span>${escHtml(extractName(e.sender||""))}</span>${badge}</div><div class="ei-subj">${escHtml(e.subject||"(no subject)")}</div><div class="ei-meta"><span>${escHtml(formatDate(e.date))}</span></div></div>${action}`;
    div.addEventListener("click",()=>openEmail(e.id,div));
    div.querySelector("[data-kb-file]")?.addEventListener("click",ev=>{ev.stopPropagation();openKnowledge(ev.currentTarget.dataset.kbFile);});
    div.querySelector("[data-finish-id]")?.addEventListener("click",ev=>{ev.stopPropagation();markEmailDone(e.id,{fromList:true});});
    div.querySelector("[data-unfinish-id]")?.addEventListener("click",ev=>{ev.stopPropagation();unarchiveEmail(e.id,{fromList:true});});
    emailListEl.appendChild(div);
  });
}

searchInput.addEventListener("input",()=>{
  clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>{
    emailOffset=0;
    loadEmailList();
  },220);
});

// ─── Open email ───────────────────────────────────────────────────────────
const emailSubject=document.getElementById("email-subject"),emailMeta=document.getElementById("email-meta");
const emailBody=document.getElementById("email-body"),responseText=document.getElementById("response-text");
const markDoneBtn=document.getElementById("btn-mark-done");
const generateContactKbBtn=document.getElementById("btn-generate-contact-kb");
const emailFindTodosBtn=document.getElementById("btn-email-find-todos");

async function openEmail(id,el){
  document.querySelectorAll(".email-item").forEach(x=>x.classList.remove("selected"));
  if(el)el.classList.add("selected");
  emailBody.textContent="Loading…";emailBody.className="";
  markDoneBtn.style.display="none";
  generateContactKbBtn.style.display="none";
  emailFindTodosBtn.style.display="none";
  responseText.textContent="Click Generate or chat on the right";responseText.className="placeholder";
  currentResponse="";activeCtxFiles=new Set();renderCtxTags();
  chatHistory=[];renderChatMessages();
  try{
    const data=await fetch(`/api/email/${encodeURIComponent(id)}`).then(r=>r.json());
    if(data.error){emailBody.textContent="Error: "+data.error;return;}
    currentEmail=data;
    markDoneBtn.style.display=data.folder==="Finished"||data.done_at?"none":"";
    generateContactKbBtn.style.display="";
    emailFindTodosBtn.style.display="";
    loadSuggestedContext(data);
    emailSubject.textContent=data.subject||"(no subject)";emailSubject.style.color="";
    emailMeta.innerHTML=`<strong>From:</strong> ${escHtml(extractName(data.sender||""))} &lt;${escHtml(extractEmail(data.sender||""))}&gt;&nbsp;&nbsp;<strong>Date:</strong> ${escHtml(data.date||"")}<br><strong>To:</strong> ${formatRecipients(data.recipients)}`;
    const html=(data.body_html||"").trim();
    const text=(data.body_text||"").trim();
    if(html){
      emailBody.className="html-view";
      const shadow=emailBody.attachShadow?null:null; // no shadow DOM, just iframe-less render
      emailBody.innerHTML=sanitizeEmailHtml(html);
      prepareExternalEmailLinks(emailBody);
    }else{
      emailBody.className="plain";emailBody.textContent=text||"[No body]";
    }
  }catch(err){emailBody.textContent="Error: "+err.message;setStatus("Error fetching email","err");}
}

function clearCurrentEmailView(){
  currentEmail=null;currentResponse="";
  markDoneBtn.style.display="none";
  emailFindTodosBtn.style.display="none";
  emailSubject.textContent="No message selected";emailSubject.style.color="var(--dim)";
  emailMeta.innerHTML="";
  emailBody.textContent="Select a message";emailBody.className="placeholder";
  responseText.textContent="Click Generate or chat on the right";responseText.className="placeholder";
  chatHistory=[];renderChatMessages();
  activeCtxFiles=new Set();renderCtxTags();
}

function adjacentEmailId(emailId){
  const row=emailListEl.querySelector(`.email-item[data-id="${CSS.escape(emailId)}"]`);
  if(!row)return null;
  return row.nextElementSibling?.dataset.id||row.previousElementSibling?.dataset.id||null;
}

async function refreshAfterEmailMove(emailId,nextId=null){
  allEmailsLocal=allEmailsLocal.filter(e=>e.id!==emailId);
  await loadFolders();
  if(currentFolder)await loadEmailList();
  if(nextId){
    const nextRow=emailListEl.querySelector(`.email-item[data-id="${CSS.escape(nextId)}"]`);
    if(nextRow)await openEmail(nextId,nextRow);
    else clearCurrentEmailView();
  }else if(currentEmail?.id===emailId)clearCurrentEmailView();
}

async function markEmailDone(emailId=currentEmail?.id,{fromList=false}={}){
  if(!emailId)return;
  const nextId=adjacentEmailId(emailId);
  try{
    const res=await fetch(`/api/email/${encodeURIComponent(emailId)}/done`,{method:"POST"}).then(r=>r.json());
    if(!res.success){setStatus("Done failed: "+(res.error||"?"),"err");return;}
    setStatus("Moved to local Finished folder","ok");
    refreshFinishedToday();
    await refreshAfterEmailMove(emailId,nextId);
  }catch(err){setStatus("Done failed: "+err.message,"err");}
}

async function unarchiveEmail(emailId=currentEmail?.id,{fromList=false}={}){
  if(!emailId)return;
  try{
    const res=await fetch(`/api/email/${encodeURIComponent(emailId)}/done`,{method:"DELETE"}).then(r=>r.json());
    if(!res.success){setStatus("Unarchive failed: "+(res.error||"?"),"err");return;}
    setStatus("Restored to "+(res.folder||"original folder"),"ok");
    refreshFinishedToday();
    if(currentEmail?.id===emailId)clearCurrentEmailView();
    await refreshAfterEmailMove(emailId);
  }catch(err){setStatus("Unarchive failed: "+err.message,"err");}
}

markDoneBtn.addEventListener("click",()=>markEmailDone());

generateContactKbBtn.addEventListener("click",async()=>{
  if(!currentEmail)return;
  if(taskPollInterval){setStatus("A task is already running","err");return;}
  try{
    generateContactKbBtn.disabled=true;
    const res=await fetch(`/api/email/${encodeURIComponent(currentEmail.id)}/build_contact_knowledge`,{method:"POST"}).then(async r=>({ok:r.ok,data:await r.json()}));
    if(!res.ok){
      setStatus("Knowledge build failed: "+(res.data.error||"?"),"err");
      generateContactKbBtn.disabled=false;
      return;
    }
    const label=res.data.contact?.email||"contact";
    startTaskPoll("Knowledge: "+label,4,async()=>{
      generateContactKbBtn.disabled=false;
      await loadEmailList();
      if(currentEmail)loadSuggestedContext(currentEmail);
    });
  }catch(err){
    generateContactKbBtn.disabled=false;
    setStatus("Knowledge build failed: "+err.message,"err");
  }
});

function sanitizeEmailHtml(raw){
  // Strip scripts, on* handlers, external tracking pixels; keep layout/text
  let h=raw
    .replace(/<script[\s\S]*?<\/script>/gi,"")
    .replace(/<style[\s\S]*?<\/style>/gi,"")
    .replace(/\son\w+\s*=\s*(['"])[^'"]*\1/gi,"")
    .replace(/\son\w+\s*=\s*[^\s>]+/gi,"")
    .replace(/<img[^>]+src=['"]https?:\/\/[^'"]*track[^'"]*['"][^>]*>/gi,"")
    .replace(/javascript:/gi,"");
  return h;
}

function prepareExternalEmailLinks(container){
  container.querySelectorAll("a[href]").forEach(link=>{
    const rawHref=(link.getAttribute("href")||"").trim();
    if(!rawHref)return;
    let url;
    try{
      url=new URL(rawHref,window.location.href);
    }catch(_err){
      link.removeAttribute("href");
      return;
    }
    if(!["http:","https:"].includes(url.protocol)){
      link.removeAttribute("href");
      return;
    }
    link.href=url.href;
    link.target="";
    link.rel="noopener noreferrer";
    link.title=link.title||"Open in default browser";
    link.addEventListener("click",async e=>{
      e.preventDefault();
      e.stopPropagation();
      try{
        const res=await fetch("/api/open_external",{
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({url:url.href}),
        }).then(r=>r.json());
        if(!res.success)setStatus("Could not open link: "+(res.error||"?"),"err");
      }catch(err){
        setStatus("Could not open link: "+err.message,"err");
      }
    });
  });
}

function renderMarkdownText(markdown){
  const source=String(markdown||"");
  const fenceRe=/```(?:markdown|md)\s*\n([\s\S]*?)```/gi;
  const fences=[...source.matchAll(fenceRe)];
  let prepared;
  if(fences.length>1){
    const headings=fences.map(m=>(m[1].match(/^\s{0,3}#{1,6}\s+(.+)$/m)||[])[1]?.trim().toLowerCase()).filter(Boolean);
    if(headings.length===fences.length&&headings.every(h=>h===headings[0])){
      const first=fences[0],last=fences[fences.length-1];
      prepared=source.slice(0,first.index)+first[1].trim()+"\n"+source.slice(last.index+last[0].length);
    }
  }
  if(!prepared)prepared=source.replace(fenceRe,(match,inner)=>inner.trim()+"\n");
  return typeof marked!=="undefined"?sanitizeEmailHtml(marked.parse(prepared)):escHtml(prepared);
}

// ─── Draft + Chat ─────────────────────────────────────────────────────────
const kbTagsEl=document.getElementById("kb-tags");
const chatMessagesEl=document.getElementById("chat-messages");
const chatInput=document.getElementById("chat-input");
let chatHistory=[];   // [{role,content}] sent to backend
let activeCtxFiles=new Set(); // all selected KB filenames (pre-populated + manual)

function renderCtxTags(){
  if(!activeCtxFiles.size){kbTagsEl.style.display="none";return;}
  kbTagsEl.innerHTML=[...activeCtxFiles].map(f=>{
    const label=f.replace(/^_/,"").replace(".md","").replace(/_/g," ");
    return `<span class="kb-tag-active">${escHtml(label)}<button data-f="${escHtml(f)}" title="Remove">&#215;</button></span>`;
  }).join("");
  kbTagsEl.style.display="flex";
  kbTagsEl.querySelectorAll("button[data-f]").forEach(btn=>{
    btn.addEventListener("click",()=>{activeCtxFiles.delete(btn.dataset.f);renderCtxTags();});
  });
}

async function loadSuggestedContext(email){
  let recipients=[];
  try{recipients=JSON.parse(email.recipients||"[]");}catch(e){}
  try{
    const files=await fetch("/api/suggested_context",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sender:email.sender||"",recipients})}).then(r=>r.json());
    activeCtxFiles=new Set(files);
    renderCtxTags();
  }catch(e){}
}

async function refreshKnowledgeIndicators(){
  if(kbLiveRefreshBusy)return;
  kbLiveRefreshBusy=true;
  try{
    if(currentFolder)await loadEmailList(false,{preserveSelection:true});
    if(currentEmail)await loadSuggestedContext(currentEmail);
  }finally{
    kbLiveRefreshBusy=false;
  }
}

// ─── Context picker ───────────────────────────────────────────────────────
let allKbFiles=[];
async function openCtxModal(){
  if(!currentEmail){setStatus("Select an email first","err");return;}
  // Fetch all KB files if not cached (refresh on open)
  try{ allKbFiles=await fetch("/api/knowledge_files").then(r=>r.json()); }
  catch(e){ setStatus("Could not load KB files","err");return; }

  // Score relevance: extract capitalised words from current email
  const emailText=`${currentEmail.subject||""} ${(currentEmail.body_text||"").slice(0,1500)}`;
  const candidates=new Set((emailText.match(/\b[A-Z][a-zA-Z]{2,}\b/g)||[]).map(w=>w.toLowerCase()));
  const stopwords=new Set(["the","this","that","from","dear","kind","best","with","your","please","thank","also","have","will","just","been","more","some","they"]);
  candidates.forEach(w=>{if(stopwords.has(w))candidates.delete(w);});

  function score(f){
    const nameLower=f.name.toLowerCase().replace(".md","").replace(/_/g," ");
    const head=(f.content||"").slice(0,400).toLowerCase();
    let s=0;
    candidates.forEach(c=>{if(nameLower.includes(c)||head.includes(c))s++;});
    if(f.pinned)s+=0.1; // slight boost for pinned
    return s;
  }
  const sorted=[...allKbFiles].sort((a,b)=>score(b)-score(a));

  const list=document.getElementById("ctx-file-list");
  list.innerHTML="";
  sorted.forEach(f=>{
    const s=score(f);
    const item=document.createElement("div");
    item.className="ctx-item"+(activeCtxFiles.has(f.name)?" selected":"");
    item.innerHTML=`<input type="checkbox" ${activeCtxFiles.has(f.name)?"checked":""}><span class="ctx-item-name">${escHtml(f.name.replace(".md","").replace(/_/g," "))}</span>${s>0?`<span class="ctx-item-badge">match</span>`:""}`;
    const cb=item.querySelector("input");
    cb.addEventListener("change",()=>{
      if(cb.checked){activeCtxFiles.add(f.name);item.classList.add("selected");}
      else{activeCtxFiles.delete(f.name);item.classList.remove("selected");}
    });
    list.appendChild(item);
  });

  document.getElementById("ctx-modal").classList.add("open");
}
document.getElementById("btn-add-ctx").addEventListener("click",openCtxModal);
document.getElementById("btn-ctx-done").addEventListener("click",()=>{
  document.getElementById("ctx-modal").classList.remove("open");
  renderCtxTags();
});

function renderChatMessages(){
  chatMessagesEl.innerHTML="";
  if(!chatHistory.length){
    chatMessagesEl.innerHTML='<div style="color:var(--dim);font-size:10.5px;padding:18px 0;text-align:center;">Ask something or click Generate to start.</div>';
    return;
  }
  chatHistory.forEach(m=>{
    const div=document.createElement("div");
    div.className="cm "+(m.role==="user"?"user":"assistant");
    const body=m.role==="user"?escHtml(m.content):(typeof marked!=="undefined"?marked.parse(m.content):escHtml(m.content));
    div.innerHTML=`<div class="cm-role">${m.role==="user"?"You":"Assistant"}</div><div class="cm-body">${body}</div>`;
    chatMessagesEl.appendChild(div);
  });
  chatMessagesEl.scrollTop=chatMessagesEl.scrollHeight;
}

function addChatMessage(role,content){
  chatHistory.push({role,content});
  renderChatMessages();
}

function appendThinking(text){
  const div=document.createElement("div");
  div.className="cm thinking";
  div.innerHTML=`<div class="cm-role">Thinking</div><div class="cm-body">${escHtml(text)}</div>`;
  chatMessagesEl.appendChild(div);
  chatMessagesEl.scrollTop=chatMessagesEl.scrollHeight;
}

function offerKbSave(kbSave){
  const div=document.createElement("div");
  div.className="cm assistant";
  div.innerHTML=`<div class="cm-role">Assistant</div>
    <div class="kb-proposal">
      <div class="kb-proposal-name">&#9670; Save to knowledge base: ${escHtml(kbSave.filename)}.md</div>
      <pre style="font-size:10px;color:var(--muted);max-height:80px;overflow:auto;margin:0;">${escHtml(kbSave.content.slice(0,300))}${kbSave.content.length>300?"…":""}</pre>
      <div class="kb-proposal-actions">
        <button class="rbtn primary" id="kb-save-yes">Save</button>
        <button class="rbtn" id="kb-save-no">Dismiss</button>
      </div>
    </div>`;
  chatMessagesEl.appendChild(div);
  chatMessagesEl.scrollTop=chatMessagesEl.scrollHeight;
  div.querySelector("#kb-save-yes").addEventListener("click",async()=>{
    await fetch("/api/knowledge_files",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({filename:kbSave.filename,content:kbSave.content,source:"chat_save"})});
    div.querySelector(".kb-proposal-actions").innerHTML='<span style="color:var(--green);font-size:10px;">&#10003; Saved</span>';
    setStatus("Saved to knowledge base: "+kbSave.filename+".md","ok");
  });
  div.querySelector("#kb-save-no").addEventListener("click",()=>div.querySelector(".kb-proposal-actions").innerHTML='<span style="color:var(--dim);font-size:10px;">Dismissed</span>');
}

async function sendChat(userText){
  if(!currentEmail){setStatus("Select an email first","err");return;}
  if(!userText.trim())return;
  addChatMessage("user",userText);
  chatInput.value="";chatInput.style.height="auto";
  setStatus("Thinking…","busy");
  // show pending indicator
  const pending=document.createElement("div");
  pending.className="cm assistant";
  pending.innerHTML='<div class="cm-role">Assistant</div><div class="cm-body" style="color:var(--amber);">…</div>';
  chatMessagesEl.appendChild(pending);chatMessagesEl.scrollTop=chatMessagesEl.scrollHeight;
  try{
    const data=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({email:currentEmail,messages:chatHistory,kb_files:[...activeCtxFiles]})}).then(r=>r.json());
    chatMessagesEl.removeChild(pending);
    // Update draft panel if draft was provided
    if(data.draft){
      currentResponse=data.draft;
      responseText.textContent=currentResponse;responseText.className="";
    }
    // Show chat reply
    if(data.chat) addChatMessage("assistant",data.chat);
    // KB save proposal
    if(data.kb_save) offerKbSave(data.kb_save);
    setStatus("Done","ok");
  }catch(err){
    chatMessagesEl.removeChild(pending);
    addChatMessage("assistant","[Error: "+err.message+"]");
    setStatus("Error: "+err.message,"err");
  }
}

const copyToast=document.getElementById("copy-toast");
async function copyTextRobust(text){
  try{
    await navigator.clipboard.writeText(text);
    return true;
  }catch{}
  const ta=document.createElement("textarea");
  ta.value=text;
  ta.setAttribute("readonly","");
  ta.style.position="fixed";
  ta.style.left="-9999px";
  ta.style.top="0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  let ok=false;
  try{ok=document.execCommand("copy");}catch{ok=false;}
  ta.remove();
  return ok;
}

function copyResponse(){
  if(!currentResponse||responseText.classList.contains("placeholder"))return Promise.resolve(false);
  return copyTextRobust(currentResponse).then(ok=>{
    if(!ok)throw new Error("Clipboard permission denied");
    copyToast.classList.add("show");setTimeout(()=>copyToast.classList.remove("show"),1800);
    return true;
  });
}

async function copyResponseAndDone(){
  const copied=await copyResponse();
  if(copied)await markEmailDone();
}

function proposeResponse(){
  sendChat("Please draft a reply to this email.");
}


// ─── Knowledge modal ──────────────────────────────────────────────────────
let kbFiles=[];
let kbEditingFile=null; // filename being edited, null = new
let kbLlmFilter="all";
let kbSearchQuery="";
let kbMergeSelection=new Set();

const kbViewMode=document.getElementById("kb-view-mode");
const kbEditMode=document.getElementById("kb-edit-mode");
const kbEditFilename=document.getElementById("kb-edit-filename");
const kbEditAliases=document.getElementById("kb-edit-aliases");
const kbEditPatterns=document.getElementById("kb-edit-patterns");
const kbEditContent=document.getElementById("kb-edit-content");
const kbFilelist=document.getElementById("kb-filelist");
const kbSearchInput=document.getElementById("kb-search");
const kbMergeBtn=document.getElementById("kb-merge-btn");
const kbLlmFilterEl=document.getElementById("kb-llm-filter");

async function openKnowledge(preferredFileName=null){
  openModal("kb-modal");
  enterKbViewMode();
  if(preferredFileName)kbLlmFilter="all";
  await reloadKbFiles(preferredFileName);
}

async function reloadKbFiles(preferredFileName=null){
  try{
    kbFiles=await fetch("/api/knowledge_files").then(r=>r.json());
    renderKbFilters();
    renderKbList(preferredFileName);
  }catch{kbFilelist.innerHTML='<div style="color:var(--red);padding:12px;font-size:10.5px;">Error loading files.</div>';}
}

function kbMetaLabel(f){
  const m=f.metadata||{};
  if((m.aliases||[]).length)return `Aliases ${m.aliases.join(", ")}`;
  if((m.match_patterns||[]).length)return `Matches ${m.match_patterns.join(", ")}`;
  if(m.llm_name||m.model)return `${m.llm_name||m.llm_id||"Unknown"}${m.model?" / "+m.model:""}`;
  if(m.source==="manual")return"Manual";
  return"Unknown";
}

function parseMatchPatterns(value){
  return String(value||"").split(/[,\n]+/).map(x=>x.trim().toLowerCase()).filter(Boolean);
}

function parseAliases(value){
  return String(value||"").split(/[,\n]+/).map(x=>x.trim().toLowerCase()).filter(x=>x&&x.includes("@"));
}

function renderKbFilters(){
  const seen=new Map();
  kbFiles.forEach(f=>{
    const id=f.metadata?.llm_id||"";
    if(id)seen.set(id,kbMetaLabel(f));
  });
  kbLlmFilterEl.innerHTML='<option value="all">All knowledge</option><option value="unknown">Unknown/manual</option>'+
    [...seen.entries()].map(([id,label])=>`<option value="${escHtml(id)}">${escHtml(label)}</option>`).join("");
  if(![...kbLlmFilterEl.options].some(o=>o.value===kbLlmFilter))kbLlmFilter="all";
  kbLlmFilterEl.value=kbLlmFilter;
}

function filteredKbFiles(){
  let files=kbFiles;
  if(kbLlmFilter==="unknown")files=files.filter(f=>!f.metadata?.llm_id);
  else if(kbLlmFilter!=="all")files=files.filter(f=>f.metadata?.llm_id===kbLlmFilter);
  const q=kbSearchQuery.trim().toLowerCase();
  if(!q)return files;
  return files.filter(f=>{
    const meta=f.metadata||{};
    return [
      f.name,
      f.content,
      kbMetaLabel(f),
      ...(meta.aliases||[]),
      ...(meta.match_patterns||[]),
    ].join("\n").toLowerCase().includes(q);
  });
}

function updateKbMergeButton(){
  kbMergeBtn.disabled=kbMergeSelection.size!==2;
}

function renderKbList(preferredFileName=null){
  const visible=filteredKbFiles();
  if(!visible.length){kbFilelist.innerHTML='<div style="padding:12px;color:var(--dim);font-size:10.5px;">No files match this filter.</div>';updateKbMergeButton();return;}
  const pinned=visible.filter(f=>f.pinned),unpinned=visible.filter(f=>!f.pinned);
  let h="";
  if(pinned.length){
    h+=`<div class="kb-pin-legend">&#9670; Always included</div>`;
    h+=pinned.map((f,i)=>kbFileItemHtml(f,kbFiles.indexOf(f))).join("");
  }
  if(unpinned.length){
    if(pinned.length)h+=`<div class="kb-pin-legend" style="margin-top:4px;">Other files</div>`;
    h+=unpinned.map(f=>kbFileItemHtml(f,kbFiles.indexOf(f))).join("");
  }
  kbFilelist.innerHTML=h;
  kbFilelist.querySelectorAll(".kb-file-item").forEach(el=>{
    el.addEventListener("click",e=>{
      if(e.target.classList.contains("kf-del")||e.target.classList.contains("kf-pin")||e.target.classList.contains("kf-select"))return;
      selectKbFile(parseInt(el.dataset.idx),el);
    });
  });
  kbFilelist.querySelectorAll(".kf-select").forEach(chk=>chk.addEventListener("change",e=>{
    e.stopPropagation();
    if(chk.checked)kbMergeSelection.add(chk.dataset.name);
    else kbMergeSelection.delete(chk.dataset.name);
    updateKbMergeButton();
  }));
  kbFilelist.querySelectorAll(".kf-del").forEach(btn=>btn.addEventListener("click",e=>{e.stopPropagation();deleteKbFile(btn.dataset.name);}));
  kbFilelist.querySelectorAll(".kf-pin").forEach(btn=>btn.addEventListener("click",e=>{e.stopPropagation();togglePin(btn.dataset.name);}));
  updateKbMergeButton();
  const target=preferredFileName?kbFilelist.querySelector(`.kb-file-item[data-name="${CSS.escape(preferredFileName)}"]`):null;
  const first=target||kbFilelist.querySelector(".kb-file-item");if(first)first.click();
}

function kbFileItemHtml(f,idx){
  return `<div class="kb-file-item${f.pinned?" pinned":""}" data-idx="${idx}" data-name="${escHtml(f.name)}">
    <input class="kf-select" type="checkbox" data-name="${escHtml(f.name)}" ${kbMergeSelection.has(f.name)?"checked":""} title="Select for merge">
    <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"><span>${escHtml(f.name)}</span><small>${escHtml(kbMetaLabel(f))}</small></span>
    <button class="kf-pin" data-name="${escHtml(f.name)}" title="${f.pinned?"Unpin (remove from all prompts)":"Pin (always include in prompts)"}">${f.pinned?"&#9670;":"&#9671;"}</button>
    <button class="kf-del" data-name="${escHtml(f.name)}" title="Delete">&#215;</button>
  </div>`;
}

async function togglePin(name){
  const f=kbFiles.find(x=>x.name===name);if(!f)return;
  const pinned=kbFiles.filter(x=>x.pinned).map(x=>x.name);
  const newPinned=f.pinned?pinned.filter(n=>n!==name):[...pinned,name];
  await fetch("/api/knowledge_pins",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(newPinned)});
  await reloadKbFiles();
  setStatus(f.pinned?"Unpinned — file no longer auto-included":"Pinned — always included in prompts","ok");
}

function selectKbFile(idx,el){
  kbFilelist.querySelectorAll(".kb-file-item").forEach(x=>x.classList.remove("active"));
  if(el)el.classList.add("active");
  enterKbViewMode(kbFiles[idx]);
}

const kbViewToolbar=document.getElementById("kb-view-toolbar");
const kbViewFilenameEl=document.getElementById("kb-view-filename");
const kbPinBtn=document.getElementById("kb-pin-btn");
let kbSelectedFile=null;

function enterKbViewMode(file){
  kbViewMode.style.display="";kbEditMode.style.display="none";
  kbSelectedFile=file||null;
  if(file){
    kbViewMode.classList.add("rendered");
    kbViewMode.innerHTML=renderMarkdownText(file.content);
    kbViewMode.style.color="";
    kbViewFilenameEl.textContent=`${file.name} · ${kbMetaLabel(file)}`;kbViewToolbar.style.display="flex";
    kbPinBtn.innerHTML=file.pinned?"&#9670; Pinned":"&#9671; Pin";
    kbPinBtn.style.color=file.pinned?"var(--amber)":"";
    kbPinBtn.style.borderColor=file.pinned?"var(--amber)":"";
    kbPinBtn.title=file.pinned?"Always included — click to unpin":"Click to always include in prompts";
  }else{
    kbViewMode.classList.remove("rendered");
    kbViewMode.textContent="Select a file.";kbViewMode.style.color="var(--dim)";
    kbViewToolbar.style.display="none";
  }
}

function enterKbEditMode(file){
  kbViewMode.style.display="none";kbEditMode.style.display="flex";
  if(file){
    kbEditFilename.value=file.name.replace(/\.md$/,"");
    kbEditFilename.disabled=false;
    kbEditAliases.value=(file.metadata?.aliases||[]).join(", ");
    kbEditPatterns.value=(file.metadata?.match_patterns||[]).join(", ");
    kbEditContent.value=file.content;
    kbEditingFile=file.name;
  }else{
    kbEditFilename.value="";kbEditFilename.disabled=false;
    kbEditAliases.value="";
    kbEditPatterns.value="";
    kbEditContent.value="";kbEditingFile=null;
  }
  kbEditContent.focus();
}

document.getElementById("kb-new-btn").addEventListener("click",()=>enterKbEditMode(null));
document.getElementById("kb-purge-btn").addEventListener("click",async()=>{
  if(!confirm("Delete all auto-generated contact profiles? Manual entries and style guide are kept."))return;
  const r=await fetch("/api/purge_contacts",{method:"POST"}).then(x=>x.json());
  await reloadKbFiles();enterKbViewMode(null);
  setStatus(`Purged ${r.count} contact profile(s)`,"ok");
});
document.getElementById("kb-edit-btn").addEventListener("click",()=>{if(kbSelectedFile)enterKbEditMode(kbSelectedFile);});
document.getElementById("kb-delete-btn").addEventListener("click",()=>{if(kbSelectedFile)deleteKbFile(kbSelectedFile.name);});
document.getElementById("kb-pin-btn").addEventListener("click",()=>{if(kbSelectedFile)togglePin(kbSelectedFile.name);});
kbSearchInput.addEventListener("input",()=>{kbSearchQuery=kbSearchInput.value;renderKbList(kbSelectedFile?.name||null);});
kbLlmFilterEl.addEventListener("change",()=>{kbLlmFilter=kbLlmFilterEl.value;renderKbList(kbSelectedFile?.name||null);});
kbMergeBtn.addEventListener("click",async()=>{
  const selected=[...kbMergeSelection];
  if(selected.length!==2)return;
  const target=(kbSelectedFile&&kbMergeSelection.has(kbSelectedFile.name))?kbSelectedFile.name:selected[0];
  const source=selected.find(name=>name!==target);
  if(!confirm(`Merge "${source}" into "${target}"?\n\nThe source entry will be removed locally and added as an alias/merged section on the target entry.`))return;
  try{
    const r=await fetch("/api/knowledge_files/merge",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({target,source})}).then(x=>x.json());
    if(!r.success){setStatus("Merge failed: "+(r.error||"?"),"err");return;}
    kbMergeSelection=new Set();
    await reloadKbFiles(r.target);
    setStatus(`Merged ${r.removed} into ${r.target}`,"ok");
  }catch(err){setStatus("Merge failed: "+err.message,"err");}
});
document.getElementById("kb-delete-filtered-btn").addEventListener("click",async()=>{
  if(kbLlmFilter==="all"){setStatus("Choose an LLM filter first","err");return;}
  if(kbLlmFilter==="unknown"){setStatus("Bulk delete is available for generated LLM entries only","err");return;}
  const label=kbLlmFilterEl.options[kbLlmFilterEl.selectedIndex]?.text||kbLlmFilter;
  const count=filteredKbFiles().length;
  if(!count){setStatus("No matching knowledge files","err");return;}
  if(!confirm(`Delete ${count} knowledge file(s) generated by ${label}?`))return;
  const r=await fetch(`/api/knowledge_files/by_llm/${encodeURIComponent(kbLlmFilter)}`,{method:"DELETE"}).then(x=>x.json());
  await reloadKbFiles();enterKbViewMode(null);
  setStatus(`Deleted ${r.count} knowledge file(s)`,"ok");
});
document.getElementById("kb-cancel-edit").addEventListener("click",()=>{
  enterKbViewMode(kbFiles.length?kbFiles[0]:null);
  const first=kbFilelist.querySelector(".kb-file-item");if(first)first.click();
});
document.getElementById("kb-save-edit").addEventListener("click",async()=>{
  const filename=kbEditingFile||(kbEditFilename.value.trim()||"untitled");
  const newFilename=kbEditFilename.value.trim()||filename;
  const content=kbEditContent.value;
  const aliases=parseAliases(kbEditAliases.value);
  const match_patterns=parseMatchPatterns(kbEditPatterns.value);
  try{
    if(kbEditingFile){
      await fetch(`/api/knowledge_files/${encodeURIComponent(kbEditingFile)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({filename:newFilename,content,aliases,match_patterns})});
    }else{
      await fetch("/api/knowledge_files",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({filename,content,aliases,match_patterns})});
    }
    await reloadKbFiles();
    setStatus("Knowledge file saved","ok");
  }catch(err){setStatus("Save error: "+err.message,"err");}
});

async function deleteKbFile(name){
  if(!confirm(`Delete "${name}"?`))return;
  try{
    await fetch(`/api/knowledge_files/${encodeURIComponent(name)}`,{method:"DELETE"});
    await reloadKbFiles();
    enterKbViewMode(null);
    setStatus("Deleted "+name,"ok");
  }catch(err){setStatus("Delete error: "+err.message,"err");}
}

// ─── Settings ─────────────────────────────────────────────────────────────
const saveMsgEl=document.getElementById("settings-save-msg");
let settingsConfig=null;
let llmDrafts=[];
let selectedLlmId=null;
let llmHealth={};
let promptDrafts={};
let quickTemplateDrafts=[];

const PROMPT_FIELDS={
  response_system:"cfg-prompt-response",
  knowledge_style_system:"cfg-prompt-style-system",
  knowledge_style_user:"cfg-prompt-style-user",
  knowledge_contact_system:"cfg-prompt-contact-system",
  knowledge_contact_user:"cfg-prompt-contact-user",
  todo_extraction_system:"cfg-prompt-todo-system",
};

const LM_PRESETS={
  lmstudio:{name:"LM Studio",base_url:"http://localhost:1234",model:"local-model",api_key:""},
  litellm: {name:"LiteLLM",base_url:"http://localhost:4000",model:"gpt-4o",api_key:""},
  openai:  {name:"OpenAI",base_url:"https://api.openai.com",model:"gpt-4o",api_key:""},
  anthropic:{name:"Anthropic via LiteLLM",base_url:"https://api.anthropic.com",model:"claude-opus-4-5",api_key:""},
  ollama:  {name:"Ollama",base_url:"http://localhost:11434",model:"llama3",api_key:""},
};
document.getElementById("cfg-lm-preset").addEventListener("change",function(){
  const p=LM_PRESETS[this.value];
  if(!p)return;
  document.getElementById("cfg-lm-name").value=p.name;
  document.getElementById("cfg-lm-url").value=p.base_url;
  document.getElementById("cfg-lm-model").value=p.model;
  document.getElementById("cfg-lm-apikey").value=p.api_key;
  saveCurrentLlmDraft();
});

function llmIdFromName(name){
  const slug=(name||"llm").toLowerCase().replace(/[^\w]+/g,"_").replace(/^_+|_+$/g,"")||"llm";
  let id=slug,i=2;
  const ids=new Set(llmDrafts.map(l=>l.id));
  while(ids.has(id)){id=slug+"_"+i;i++;}
  return id;
}

function currentLlmDraft(){
  return llmDrafts.find(l=>l.id===selectedLlmId)||llmDrafts[0]||null;
}

function saveCurrentLlmDraft(rerender=true){
  const llm=currentLlmDraft();
  if(!llm)return;
  llm.name=document.getElementById("cfg-lm-name").value.trim()||"LLM";
  llm.base_url=document.getElementById("cfg-lm-url").value.trim()||"http://localhost:1234";
  llm.model=document.getElementById("cfg-lm-model").value.trim()||"local-model";
  llm.api_key=document.getElementById("cfg-lm-apikey").value.trim().replace(/^•+$/,"••••••••");
  if(rerender)renderLlmSelectors(false);
}

function populateLlmForm(llm){
  if(!llm)return;
  selectedLlmId=llm.id;
  document.getElementById("cfg-lm-name").value=llm.name||"";
  document.getElementById("cfg-lm-url").value=llm.base_url||"";
  document.getElementById("cfg-lm-model").value=llm.model||"";
  document.getElementById("cfg-lm-apikey").value=llm.api_key||"";
  document.getElementById("cfg-lm-preset").value="";
  renderLlmSelectors(false);
}

function renderLlmSelectors(keepSelection=true){
  const list=document.getElementById("cfg-llm-list");
  const def=document.getElementById("cfg-default-llm");
  const activeId=selectedLlmId||(llmDrafts[0]?.id||"");
  const options=llmDrafts.map(l=>`<option value="${escHtml(l.id)}">${escHtml(l.name||l.id)}</option>`).join("");
  list.innerHTML=options;def.innerHTML=options;
  list.value=activeId;
  def.value=settingsConfig?.default_llm_id||llmDrafts[0]?.id||"";
  if(!keepSelection)list.value=activeId;
  document.getElementById("btn-llm-delete").disabled=llmDrafts.length<=1;
  renderLlmHealthList();
}

function healthClass(ok){
  return ok===true?"ok":ok===false?"err":"unknown";
}

function renderLlmHealthList(){
  const list=document.getElementById("llm-health-list");
  if(!list)return;
  list.innerHTML=`<div class="llm-health-row">${llmDrafts.map(l=>{
    const h=llmHealth[l.id];
    const cls=healthClass(h?.ok);
    const title=h?.error?` title="${escHtml(h.error)}"`:"";
    return `<span class="llm-health-pill"${title}><span class="llm-health-dot ${cls}"></span>${escHtml(l.name||l.id)}</span>`;
  }).join("")}</div>`;
}

function populatePromptSettings(prompts){
  promptDrafts={...(prompts||{})};
  Object.entries(PROMPT_FIELDS).forEach(([key,id])=>{
    const el=document.getElementById(id);
    if(el)el.value=promptDrafts[key]||"";
  });
}

function collectPromptSettings(){
  Object.entries(PROMPT_FIELDS).forEach(([key,id])=>{
    const el=document.getElementById(id);
    if(el)promptDrafts[key]=el.value;
  });
  return promptDrafts;
}

function normalizeQuickTemplates(templates){
  const clean=(templates||[]).map(t=>({
    emoji:String(t.emoji||"").trim().slice(0,8),
    message:String(t.message||"").trim(),
  })).filter(t=>t.emoji&&t.message);
  return clean.length?clean:[
    {emoji:"👍",message:"Please write a concise reply confirming or accepting what was proposed."},
    {emoji:"👎",message:"Please write a concise reply declining or rejecting what was proposed."},
  ];
}

function renderQuickTemplateButtons(){
  const wrap=document.getElementById("quick-template-buttons");
  if(!wrap)return;
  const templates=normalizeQuickTemplates(quickTemplateDrafts);
  wrap.innerHTML=templates.map((t,i)=>`<button class="quick-template-btn" data-template-index="${i}" title="${escHtml(t.message)}">${escHtml(t.emoji)}</button>`).join("");
  wrap.querySelectorAll("[data-template-index]").forEach(btn=>{
    btn.addEventListener("click",()=>sendChat(templates[parseInt(btn.dataset.templateIndex)].message));
  });
}

function renderQuickTemplateEditor(){
  const c=document.getElementById("quick-template-editor");
  if(!c)return;
  if(!quickTemplateDrafts.length)quickTemplateDrafts=normalizeQuickTemplates([]);
  c.innerHTML=quickTemplateDrafts.map((t,i)=>`
    <div class="quick-template-row" data-template-row="${i}">
      <input class="qt-emoji" type="text" maxlength="8" value="${escHtml(t.emoji)}" aria-label="Template emoji" autocomplete="off"/>
      <textarea class="qt-message" rows="3" aria-label="Template message" spellcheck="false">${escHtml(t.message)}</textarea>
      <button class="icon-btn del qt-delete" type="button" title="Delete template">&#10005;</button>
    </div>`).join("");
  c.querySelectorAll(".quick-template-row").forEach(row=>{
    const idx=parseInt(row.dataset.templateRow);
    row.querySelector(".qt-emoji").addEventListener("input",e=>{quickTemplateDrafts[idx].emoji=e.target.value;renderQuickTemplateButtons();});
    row.querySelector(".qt-message").addEventListener("input",e=>{quickTemplateDrafts[idx].message=e.target.value;renderQuickTemplateButtons();});
    row.querySelector(".qt-delete").addEventListener("click",()=>{
      quickTemplateDrafts.splice(idx,1);
      renderQuickTemplateEditor();
      renderQuickTemplateButtons();
    });
  });
}

function populateQuickTemplates(templates){
  quickTemplateDrafts=normalizeQuickTemplates(templates);
  renderQuickTemplateEditor();
  renderQuickTemplateButtons();
}

function collectQuickTemplates(){
  return normalizeQuickTemplates(quickTemplateDrafts);
}

function updateActiveHealthDot(){
  const dot=document.getElementById("active-llm-health");
  const h=llmHealth[activeLlmSelect.value];
  dot.className="llm-health-dot "+healthClass(h?.ok);
  dot.title=h?.ok===true?"LLM reachable":h?.ok===false?("LLM unavailable"+(h.error?": "+h.error:"")):"LLM status unknown";
}

async function loadLlmHealth(){
  try{
    const data=await fetch("/api/llm/status").then(r=>r.json());
    llmHealth={};
    (data.llms||[]).forEach(h=>{llmHealth[h.id]=h;});
    updateActiveHealthDot();
    renderLlmHealthList();
  }catch(e){
    updateActiveHealthDot();
  }
}

function initLlmSettings(cfg){
  settingsConfig=cfg;
  llmDrafts=(cfg.llms&&cfg.llms.length?cfg.llms:[cfg.lm_studio||{}]).map((l,i)=>({
    id:l.id||("llm_"+(i+1)),
    name:l.name||l.model||"LLM",
    base_url:l.base_url||"http://localhost:1234",
    model:l.model||"local-model",
    api_key:l.api_key||"",
  }));
  selectedLlmId=cfg.app?.active_llm_id||cfg.default_llm_id||llmDrafts[0]?.id;
  renderLlmSelectors();
  populateLlmForm(currentLlmDraft());
  populatePromptSettings(cfg.prompts||{});
  populateQuickTemplates(cfg.quick_templates||[]);
}

async function loadActiveLlmPicker(){
  try{
    const data=await fetch("/api/llm/active").then(r=>r.json());
    activeLlmSelect.innerHTML=(data.llms||[]).map(l=>`<option value="${escHtml(l.id)}">${escHtml(l.name||l.id)}</option>`).join("");
    activeLlmSelect.value=data.active_llm_id||data.default_llm_id||"";
    const active=(data.llms||[]).find(l=>l.id===activeLlmSelect.value);
    statusModel.textContent=active?"LLM:":"LLM";
    statusModel.style.color="var(--muted)";
    updateActiveHealthDot();
    loadLlmHealth();
  }catch(err){
    statusModel.textContent="LLM unavailable";
    statusModel.style.color="var(--red)";
  }
}

activeLlmSelect.addEventListener("change",async()=>{
  try{
    const res=await fetch("/api/llm/active",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({active_llm_id:activeLlmSelect.value})}).then(r=>r.json());
    if(res.success){
      const label=activeLlmSelect.options[activeLlmSelect.selectedIndex]?.text||"LLM";
      updateActiveHealthDot();
      setStatus("Active LLM: "+label,"ok");
    }else setStatus("LLM switch failed: "+(res.error||"?"),"err");
  }catch(err){setStatus("LLM switch failed: "+err.message,"err");}
});

document.getElementById("cfg-llm-list").addEventListener("change",function(){
  const nextId=this.value;
  saveCurrentLlmDraft(false);
  selectedLlmId=nextId;
  populateLlmForm(currentLlmDraft());
});
document.getElementById("cfg-default-llm").addEventListener("change",function(){
  if(settingsConfig)settingsConfig.default_llm_id=this.value;
});
["cfg-lm-name","cfg-lm-url","cfg-lm-model","cfg-lm-apikey"].forEach(id=>{
  document.getElementById(id).addEventListener("input",saveCurrentLlmDraft);
});
document.getElementById("btn-reset-prompts").addEventListener("click",async()=>{
  if(!confirm("Reset all advanced prompts to the current defaults? Unsaved prompt edits will be replaced."))return;
  try{
    const defaults=await fetch("/api/prompt_defaults").then(r=>r.json());
    populatePromptSettings(defaults);
    setStatus("Prompts reset to defaults — click Save to persist","ok");
  }catch(err){setStatus("Prompt reset failed: "+err.message,"err");}
});
document.getElementById("btn-add-template").addEventListener("click",()=>{
  quickTemplateDrafts.push({emoji:"✨",message:""});
  renderQuickTemplateEditor();
  renderQuickTemplateButtons();
});
document.getElementById("btn-reset-templates").addEventListener("click",async()=>{
  if(!confirm("Reset quick templates to the defaults? Unsaved template edits will be replaced."))return;
  try{
    const defaults=await fetch("/api/quick_template_defaults").then(r=>r.json());
    populateQuickTemplates(defaults);
    setStatus("Quick templates reset — click Save to persist","ok");
  }catch(err){setStatus("Template reset failed: "+err.message,"err");}
});
document.getElementById("btn-llm-add").addEventListener("click",()=>{
  saveCurrentLlmDraft();
  const llm={id:llmIdFromName("New LLM"),name:"New LLM",base_url:"http://localhost:1234",model:"local-model",api_key:""};
  llmDrafts.push(llm);selectedLlmId=llm.id;
  populateLlmForm(llm);
});
document.getElementById("btn-llm-delete").addEventListener("click",()=>{
  if(llmDrafts.length<=1)return;
  const llm=currentLlmDraft();
  if(!llm||!confirm(`Delete LLM "${llm.name}"?`))return;
  llmDrafts=llmDrafts.filter(l=>l.id!==llm.id);
  if(settingsConfig?.default_llm_id===llm.id)settingsConfig.default_llm_id=llmDrafts[0].id;
  selectedLlmId=llmDrafts[0].id;
  populateLlmForm(llmDrafts[0]);
});

async function loadSettings(){
  try{
    const cfg=await fetch("/api/config").then(r=>r.json());
    initLlmSettings(cfg);
  }catch{}
  try{
    const accounts=await fetch("/api/accounts").then(r=>r.json());
    accountsCache=accounts;renderAccountsList(accounts);
  }catch{}
}

async function loadQuickTemplates(){
  try{
    const cfg=await fetch("/api/config").then(r=>r.json());
    populateQuickTemplates(cfg.quick_templates||[]);
  }catch{
    populateQuickTemplates([]);
  }
}

function renderAccountsList(accounts){
  const c=document.getElementById("acct-list-container");
  if(!accounts.length){c.innerHTML='<div style="color:var(--dim);font-size:11px;padding:8px 0;">No accounts configured yet.</div>';return;}
  c.innerHTML=accounts.map(a=>`
    <div class="acct-list-item">
      <div class="acct-list-info"><div class="acct-list-name">${escHtml(a.name)} ${providerBadge(a.imap?.detected_provider)} <span class="acct-info-btn" data-account-info="${escHtml(a.id)}" data-tip="Loading account info...">i</span></div><div class="acct-list-user">${escHtml(a.imap?.username||"")}</div></div>
      <div class="acct-list-actions">
        <button class="icon-btn" data-edit-id="${escHtml(a.id)}">Edit</button>
        <button class="icon-btn del" data-del-id="${escHtml(a.id)}" data-del-name="${escHtml(a.name)}">&#10005;</button>
      </div>
    </div>`).join("");
  c.querySelectorAll("[data-edit-id]").forEach(btn=>btn.addEventListener("click",()=>openEditAccount(btn.dataset.editId)));
  c.querySelectorAll("[data-del-id]").forEach(btn=>btn.addEventListener("click",()=>deleteAccount(btn.dataset.delId,btn.dataset.delName)));
  c.querySelectorAll("[data-account-info]").forEach(loadAccountInfoTip);
}

function formatBytes(n){
  n=Number(n)||0;
  if(n<1024)return n+" B";
  const units=["KB","MB","GB"];
  let v=n/1024,i=0;
  while(v>=1024&&i<units.length-1){v/=1024;i++;}
  return `${v>=10?v.toFixed(1):v.toFixed(2)} ${units[i]}`;
}

function providerFromOverride(value){
  if(value==="outlook")return {id:"outlook",name:"Microsoft / Exchange / Outlook",confidence:"manual"};
  if(value==="google")return {id:"google",name:"Google / Gmail",confidence:"manual"};
  if(value==="generic")return {id:"generic",name:"Generic IMAP",confidence:"manual"};
  return null;
}

function detectProviderFromFields(server,username,override){
  const manual=providerFromOverride(override);
  if(manual)return manual;
  const s=String(server||"").trim().toLowerCase();
  const u=String(username||"").trim().toLowerCase();
  const domain=u.includes("@")?u.split("@").pop():"";
  const hay=[s,domain].join(" ");
  const outlook=["outlook.office365.com","imap-mail.outlook.com","imap.outlook.com","office365.com","outlook.com","hotmail.com","live.com","msn.com"];
  if(outlook.some(x=>hay.includes(x)))return {id:"outlook",name:"Microsoft / Exchange / Outlook",confidence:s.includes("outlook.office365.com")||domain.includes("outlook.com")?"high":"medium"};
  if(hay.includes("gmail.com")||hay.includes("googlemail.com"))return {id:"google",name:"Google / Gmail",confidence:"high"};
  if(hay.includes("icloud.com")||domain==="me.com"||domain==="mac.com")return {id:"icloud",name:"Apple iCloud",confidence:"high"};
  return {id:"generic",name:"Generic IMAP",confidence:"low"};
}

function providerBadge(provider){
  const p=provider||{};
  if(!p.id||p.id==="generic")return "";
  return `<span class="provider-badge provider-${escHtml(p.id)}" title="${escHtml(p.reason||p.name||"Detected provider")}">${escHtml(p.name||p.id)}</span>`;
}

function updateProviderHint(){
  const hint=document.getElementById("cfg-provider-hint");
  if(!hint)return;
  const p=detectProviderFromFields(
    document.getElementById("cfg-imap-server")?.value,
    document.getElementById("cfg-imap-username")?.value,
    document.getElementById("cfg-provider-override")?.value
  );
  hint.textContent=`Provider: ${p.name}${p.confidence&&p.confidence!=="low"?` (${p.confidence})`:""}`;
  hint.className="field-hint provider-hint "+(p.id==="outlook"?"is-outlook":p.id==="generic"?"":"is-known");
}

async function loadAccountInfoTip(el){
  try{
    const id=el.dataset.accountInfo;
    const data=await fetch(`/api/accounts/${encodeURIComponent(id)}/stats`).then(r=>r.json());
    const acct=accountsCache.find(a=>a.id===id);
    const folders=(data.folders||[]).slice(0,4).map(f=>`${f.folder}: ${f.count}`).join("\n");
    const states=(data.sync_state||[]).filter(s=>s.last_sync_at).slice(0,2).map(s=>`${s.folder}: ${new Date(s.last_sync_at).toLocaleString()}`).join("\n");
    el.dataset.tip=[
      acct?.name||id,
      `${data.email_count||0} local emails`,
      `Approx. account data: ${formatBytes(data.approx_account_bytes)}`,
      `Database file: ${formatBytes(data.database_file_bytes)}`,
      acct?.imap?.detected_provider?.name?`Detected provider: ${acct.imap.detected_provider.name} (${acct.imap.detected_provider.confidence||"unknown"} confidence)`:"",
      acct?.imap?.provider_override&&acct.imap.provider_override!=="auto"?`Provider override: ${acct.imap.provider_override}`:"Provider override: auto",
      acct?.imap?.calendar_enabled?`Calendar: enabled (${acct.imap.calendar_method||"ics"})`:"Calendar: off",
      acct?.imap?.sync_mode?`Mode: ${acct.imap.sync_mode}`:"",
      acct?.imap?.auto_sync?`Auto-sync: every ${acct.imap.sync_interval_minutes||5} min`:"Auto-sync: off",
      folders?`\nFolders:\n${folders}`:"",
      states?`\nLast sync:\n${states}`:"",
    ].filter(Boolean).join("\n");
  }catch{
    el.dataset.tip="Could not load account info.";
  }
}

function _populateAccountForm(acct){
  document.getElementById("cfg-acct-id").value=acct?.id||"";
  document.getElementById("cfg-acct-name").value=acct?.name||"";
  document.getElementById("cfg-imap-server").value=acct?.imap?.server||"";
  document.getElementById("cfg-imap-port").value=acct?.imap?.port||993;
  document.getElementById("cfg-imap-username").value=acct?.imap?.username||"";
  document.getElementById("cfg-imap-password").value=acct?.imap?.password||"";
  document.getElementById("cfg-provider-override").value=acct?.imap?.provider_override||"auto";
  document.getElementById("cfg-calendar-url").value=acct?.imap?.calendar_url||"";
  document.getElementById("cfg-calendar-enabled").checked=!!acct?.imap?.calendar_enabled;
  document.getElementById("cfg-imap-limit").value=acct?.imap?.fetch_limit||300;
  document.getElementById("cfg-sync-mode").value=acct?.imap?.sync_mode||"recent";
  document.getElementById("cfg-sync-since").value=acct?.imap?.sync_since||"";
  document.getElementById("cfg-body-storage").value=acct?.imap?.body_storage||"text_html";
  document.getElementById("cfg-auto-sync").checked=!!acct?.imap?.auto_sync;
  document.getElementById("cfg-sync-interval").value=acct?.imap?.sync_interval_minutes||5;
  updateProviderHint();
  // Render saved sync_folders if any
  const saved=acct?.imap?.sync_folders||[];
  if(saved.length){discoveredFolders=saved;renderFolderPicker(saved,true);}
  else{discoveredFolders=[];document.getElementById("folder-picker-list").style.display="none";document.getElementById("folder-picker-status").textContent="";}
}

function openEditAccount(accountId){
  const acct=accountsCache.find(a=>a.id===accountId);if(!acct)return;
  _populateAccountForm(acct);
  document.getElementById("acct-edit-label").textContent="Edit Account";
  switchTab("tab-acct-edit");settingsFooterMode("edit");
}

function openNewAccount(){
  _populateAccountForm(null);
  document.getElementById("acct-edit-label").textContent="New Account";
  switchTab("tab-acct-edit");settingsFooterMode("new");
}

async function deleteAccount(accountId,name){
  if(!confirm(`Delete account "${name}"? Synced emails remain in the database.`))return;
  try{
    await fetch(`/api/accounts/${encodeURIComponent(accountId)}`,{method:"DELETE"});
    await loadSettings();loadFolders();setStatus(`Account "${name}" removed`,"ok");
  }catch(err){setStatus("Delete error: "+err.message,"err");}
}

// ─── Folder discovery ─────────────────────────────────────────────────────
function renderFolderPicker(folders,isSaved){
  const list=document.getElementById("folder-picker-list");
  list.style.display="block";
  list.innerHTML=folders.map(f=>`
    <div class="fp-item">
      <input type="checkbox" class="fp-check" data-name="${escHtml(f.name)}" ${f.checked||isSaved?"checked":""}>
      <span class="fp-name">${escHtml(f.name)}</span>
      <select class="fp-role-sel" data-name="${escHtml(f.name)}">
        <option value="inbox" ${f.role==="inbox"?"selected":""}>Inbox</option>
        <option value="sent" ${f.role==="sent"?"selected":""}>Sent</option>
        <option value="other" ${f.role==="other"?"selected":""}>Other</option>
      </select>
    </div>`).join("");
  // Add role css
  list.querySelectorAll(".fp-role-sel").forEach(sel=>{
    function applyRole(){
      const fp=sel.closest(".fp-item").querySelector(".fp-name");
      const span=sel.closest(".fp-item");
      // style handled by CSS class on the select option text — just keep data
    }
    applyRole();sel.addEventListener("change",applyRole);
  });
}

function getSelectedFolders(){
  const list=document.getElementById("folder-picker-list");
  if(list.style.display==="none")return null; // not set, use defaults
  const result=[];
  list.querySelectorAll(".fp-item").forEach(item=>{
    const chk=item.querySelector(".fp-check");
    const role=item.querySelector(".fp-role-sel")?.value||"other";
    if(chk?.checked)result.push({name:chk.dataset.name,role});
  });
  return result;
}

document.getElementById("btn-discover-folders").addEventListener("click",async()=>{
  const status=document.getElementById("folder-picker-status");
  status.textContent="Connecting…";status.style.color="var(--muted)";
  const accountId=document.getElementById("cfg-acct-id").value.trim();
  const payload={
    account_id:accountId||undefined,
    server:document.getElementById("cfg-imap-server").value.trim(),
    port:parseInt(document.getElementById("cfg-imap-port").value)||993,
    username:document.getElementById("cfg-imap-username").value.trim(),
    password:document.getElementById("cfg-imap-password").value,
    inbox_folder:"INBOX",sent_folder:"Sent Items",
  };
  try{
    const res=await fetch("/api/imap_folders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}).then(r=>r.json());
    if(res.success){
      discoveredFolders=res.folders;
      renderFolderPicker(res.folders,false);
      status.textContent=`Found ${res.folders.length} folders.`;status.style.color="var(--green)";
    }else{
      status.textContent="Error: "+res.error;status.style.color="var(--red)";
    }
  }catch(err){status.textContent="Connection failed: "+err.message;status.style.color="var(--red)";}
});

["cfg-imap-server","cfg-imap-username","cfg-provider-override"].forEach(id=>{
  document.getElementById(id)?.addEventListener("input",updateProviderHint);
  document.getElementById(id)?.addEventListener("change",updateProviderHint);
});

// ─── Save settings ────────────────────────────────────────────────────────
async function saveSettings(){
  const activeTab=settingsActiveTab;
  if(activeTab==="tab-acct-edit"){
    const accountId=document.getElementById("cfg-acct-id").value.trim();
    const selectedFolders=getSelectedFolders();
    const payload={
      name:document.getElementById("cfg-acct-name").value.trim(),
      imap:{
        server:document.getElementById("cfg-imap-server").value.trim(),
        port:parseInt(document.getElementById("cfg-imap-port").value)||993,
        username:document.getElementById("cfg-imap-username").value.trim(),
        password:document.getElementById("cfg-imap-password").value,
        provider_override:document.getElementById("cfg-provider-override").value||"auto",
        calendar_url:document.getElementById("cfg-calendar-url").value.trim(),
        calendar_enabled:document.getElementById("cfg-calendar-enabled").checked,
        fetch_limit:parseInt(document.getElementById("cfg-imap-limit").value)||300,
        sync_mode:document.getElementById("cfg-sync-mode").value,
        sync_since:document.getElementById("cfg-sync-since").value,
        body_storage:document.getElementById("cfg-body-storage").value,
        auto_sync:document.getElementById("cfg-auto-sync").checked,
        sync_interval_minutes:parseInt(document.getElementById("cfg-sync-interval").value)||5,
      },
    };
    if(!payload.name){setStatus("Display name required","err");return;}
    // Add folder selection
    if(selectedFolders&&selectedFolders.length){
      payload.imap.sync_folders=selectedFolders;
      // Keep inbox_folder / sent_folder for backward compat
      const inbox=selectedFolders.find(f=>f.role==="inbox");
      const sent=selectedFolders.find(f=>f.role==="sent");
      if(inbox)payload.imap.inbox_folder=inbox.name;
      if(sent)payload.imap.sent_folder=sent.name;
    }
    try{
      let res;
      if(accountId)res=await fetch(`/api/accounts/${encodeURIComponent(accountId)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}).then(r=>r.json());
      else res=await fetch("/api/accounts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}).then(r=>r.json());
      if(res.success){
        saveMsgEl.style.display="block";setTimeout(()=>saveMsgEl.style.display="none",2500);
        setStatus("Account saved","ok");await loadSettings();loadFolders();setupAutoSyncTimer();
        switchTab("tab-accounts");settingsFooterMode("list");
      }else setStatus("Error: "+(res.error||"?"),"err");
    }catch(err){setStatus("Save error: "+err.message,"err");}
    return;
  }
  // LLM providers / Whisper
  saveCurrentLlmDraft();
  const defaultId=document.getElementById("cfg-default-llm").value||llmDrafts[0]?.id;
  const payload={
    llms:llmDrafts,
    default_llm_id:defaultId,
    app:{active_llm_id:activeLlmSelect.value||defaultId},
    prompts:collectPromptSettings(),
    quick_templates:collectQuickTemplates(),
  };
  try{
    const res=await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}).then(r=>r.json());
    if(res.success){saveMsgEl.style.display="block";setTimeout(()=>saveMsgEl.style.display="none",2500);setStatus("Settings saved","ok");await loadActiveLlmPicker();}
    else setStatus("Error: "+(res.error||"?"),"err");
  }catch(err){setStatus("Save error: "+err.message,"err");}
}

// ─── Utilities ────────────────────────────────────────────────────────────
function extractName(s){const m=s.match(/^(.+?)\s*</);if(m&&m[1].trim())return m[1].replace(/^"|"$/g,"").trim();return s.replace(/<[^>]+>/g,"").trim()||s;}
function extractEmail(s){const m=s.match(/<([^>]+)>/);return m?m[1]:s;}
function formatRecipients(recs){
  if(!recs)return"";let arr=recs;
  try{if(typeof recs==="string")arr=JSON.parse(recs);}catch{return escHtml(recs);}
  if(!Array.isArray(arr))return"";
  return arr.slice(0,3).map(r=>escHtml(r.name||r.email||"")).join(", ");
}
function formatDate(s){
  if(!s)return"";
  try{const d=new Date(s),now=new Date();
    if(d.toDateString()===now.toDateString())return d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
    if((now-d)/86400000<7)return d.toLocaleDateString([],{weekday:"short"});
    return d.toLocaleDateString([],{month:"short",day:"numeric"});
  }catch{return s.substring(0,10);}
}
function escHtml(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

// ─── Event wiring ─────────────────────────────────────────────────────────
document.getElementById("btn-sync").addEventListener("click",()=>{
  if(taskPollInterval){setStatus("A task is already running","err");return;}
  const n=accountsCache.length*3;
  fetch("/api/sync",{method:"POST"}).then(()=>startTaskPoll("Sync All",n,()=>loadFolders())).catch(err=>setStatus("Sync error: "+err.message,"err"));
});
document.getElementById("btn-build-kb").addEventListener("click",async()=>{
  if(taskPollInterval){setStatus("A task is already running","err");return;}
  try{
    const stats=await fetch("/api/knowledge_stats").then(r=>r.json());
    const total=stats.total_messages||0,newMessages=stats.new_messages||0;
    const msg=[
      "Update the full local knowledge base?",
      "",
      `This will scan ${total} local message${total===1?"":"s"} and parse ${newMessages} new/unprocessed message${newMessages===1?"":"s"} for writing style and contact profiles.`,
      "This can take a while and will use the active LLM.",
    ].join("\n");
    if(!confirm(msg))return;
    fetch("/api/build_knowledge",{method:"POST"}).then(()=>startTaskPoll("Knowledge base update",42,()=>{})).catch(err=>setStatus("Error: "+err.message,"err"));
  }catch(err){setStatus("Knowledge update failed: "+err.message,"err");}
});
document.getElementById("btn-view-kb").addEventListener("click",openKnowledge);
document.getElementById("btn-calendar").addEventListener("click",openCalendar);
document.getElementById("btn-find-todos").addEventListener("click",openTodosModal);
document.getElementById("btn-settings").addEventListener("click",()=>{loadSettings();openModal("settings-modal");settingsFooterMode("list");switchTab("tab-accounts");});
emailFindTodosBtn.addEventListener("click",ev=>{
  ev.stopPropagation();
  if(!currentEmail?.id){setStatus("Select an email first","err");return;}
  openTodosModal({emailId:currentEmail.id,forceOpen:true,autoStart:true});
});

// ─── Todo finder ──────────────────────────────────────────────────────────
let todoPendingPayload=null,todoPreviewTimer=null,todoJobTimer=null,todoLatestCount=0,todoSingleEmailId="";

function openTodosModal(options={}){
  todoSingleEmailId=options.emailId||"";
  const today=new Date();
  const weekBack=new Date(today);
  weekBack.setDate(weekBack.getDate()-7);
  const searchEl=document.getElementById("todo-search");
  const startEl=document.getElementById("todo-start-date");
  const endEl=document.getElementById("todo-end-date");
  searchEl.value=todoSingleEmailId?"":searchInput.value.trim();
  startEl.value=todoSingleEmailId?"":formatDateInput(weekBack);
  endEl.value=todoSingleEmailId?"":formatDateInput(today);
  searchEl.disabled=!!todoSingleEmailId;
  startEl.disabled=!!todoSingleEmailId;
  endEl.disabled=!!todoSingleEmailId;
  document.getElementById("todos-results").innerHTML=todoSingleEmailId
    ?'<div class="todo-empty">This run is scoped to the selected email.</div>'
    :'<div class="todo-empty">Matching emails are counted automatically.</div>';
  document.getElementById("todo-live-count").textContent="Counting…";
  updateTodoProgress({current:0,total:0,current_email:null,status:"idle"});
  document.getElementById("btn-start-todo-llm").hidden=true;
  document.getElementById("btn-start-todo-llm").disabled=false;
  document.getElementById("btn-export-todos").hidden=true;
  document.getElementById("btn-create-ews-todos").hidden=true;
  todoPendingPayload=null;
  const popover=document.getElementById("todo-popover");
  const shouldOpen=options.forceOpen||!popover.open;
  if(shouldOpen){
    if(!popover.open){
      if(popover.showModal)popover.showModal();
      else if(popover.show)popover.show();
      else popover.setAttribute("open","");
    }
    refreshTodoPreview().then(()=>{
      if(options.autoStart)startTodoLlm({skipConfirm:true});
    });
  }else{
    todoSingleEmailId="";
    searchEl.disabled=false;
    startEl.disabled=false;
    endEl.disabled=false;
    if(popover.close)popover.close();
    else popover.removeAttribute("open");
  }
}

function formatDateInput(date){
  const y=date.getFullYear();
  const m=String(date.getMonth()+1).padStart(2,"0");
  const d=String(date.getDate()).padStart(2,"0");
  return `${y}-${m}-${d}`;
}

function renderTodoResults(data){
  const box=document.getElementById("todos-results");
  const todos=data.todos||[];
  document.getElementById("btn-export-todos").hidden=!todos.length;
  document.getElementById("btn-create-ews-todos").hidden=!todos.length;
  if(!todos.length){
    box.innerHTML=`<div class="todo-empty">No actionable todos found in ${data.analyzed||0} analyzed emails.</div>`;
    return;
  }
  box.innerHTML=`
    <div class="todo-summary">${todos.length} editable candidates from ${data.analyzed||0} analyzed emails${data.matched>data.analyzed?` (${data.matched} matched locally)`: ""}</div>
    <div class="todo-list">
      ${todos.map((todo,idx)=>`
        <label class="todo-item" data-source-id="${escAttr((todo.source_ids||[])[0]||"")}">
          <input type="checkbox" checked data-todo-index="${idx}"/>
          <span class="todo-edit">
            <input class="todo-title" type="text" value="${escAttr(todo.title||"Todo")}" placeholder="Title"/>
            <input class="todo-due" type="date" value="${escAttr(normalizeTodoDate(todo.due_date||todo.due||""))}" title="${escAttr(todo.due_date||todo.due||"")}" aria-label="Due date"/>
            <textarea class="todo-description" placeholder="Description">${escHtml(descriptionWithRawDue(todo.description||todo.details||"",todo.due_date||todo.due||""))}</textarea>
            <input class="todo-tags" type="text" value="${escAttr((todo.tags||[]).join(", "))}" placeholder="Tags"/>
            <input class="todo-location" type="text" value="${escAttr(todo.location||"")}" placeholder="Location"/>
          </span>
        </label>
      `).join("")}
    </div>`;
  box.querySelectorAll(".todo-item").forEach(item=>{
    item.addEventListener("click",ev=>{
      if(ev.target.matches("input,textarea"))return;
      const id=item.dataset.sourceId;
      if(id)showTodoSourceEmail(id,item);
    });
    item.addEventListener("focusin",()=>{
      const id=item.dataset.sourceId;
      if(id)showTodoSourceEmail(id,item);
    });
  });
}

function escAttr(s){return escHtml(String(s??"")).replace(/"/g,"&quot;");}

function normalizeTodoDate(value){
  const text=String(value||"").trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(text)?text:"";
}

function descriptionWithRawDue(description,due){
  const desc=String(description||"").trim();
  const text=String(due||"").trim();
  if(!text||normalizeTodoDate(text))return desc;
  return [desc,`Due: ${text}`].filter(Boolean).join("\n");
}

async function showTodoSourceEmail(emailId,itemEl=null){
  try{
    document.querySelectorAll(".todo-item.active").forEach(el=>el.classList.remove("active"));
    itemEl?.classList.add("active");
    document.getElementById("todo-current-email").innerHTML='<div class="todo-empty">Loading source email…</div>';
    const mail=await fetch(`/api/email/${encodeURIComponent(emailId)}`).then(r=>r.json());
    if(mail.error)throw new Error(mail.error);
    const progressText=document.getElementById("todo-progress-count").textContent.split("/");
    updateTodoProgress({
      current:Number(progressText[0]?.trim())||0,
      total:Number(progressText[1]?.trim())||0,
      current_email:{
        subject:mail.subject||"(no subject)",
        sender:mail.sender||"",
        date:mail.date||"",
        body:(mail.body_text||"").trim(),
      },
    });
  }catch(err){
    document.getElementById("todo-current-email").innerHTML=`<div class="todo-empty">Could not load source email: ${escHtml(err.message)}</div>`;
  }
}

function todoFilterPayload(){
  return {
    account_id:currentAccountId||"",
    folder:currentFolder||"INBOX",
    search:document.getElementById("todo-search").value.trim(),
    start_date:document.getElementById("todo-start-date").value,
    end_date:document.getElementById("todo-end-date").value,
    email_id:todoSingleEmailId,
  };
}

async function refreshTodoPreview(){
  const llmBtn=document.getElementById("btn-start-todo-llm");
  const box=document.getElementById("todos-results");
  const payload=todoFilterPayload();
  llmBtn.hidden=true;
  document.getElementById("btn-export-todos").hidden=true;
  document.getElementById("btn-create-ews-todos").hidden=true;
  todoPendingPayload=null;
  try{
    document.getElementById("todo-live-count").textContent="Counting…";
    const preview=await fetch("/api/todos/preview",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload),
    }).then(async r=>({ok:r.ok,data:await r.json()}));
    if(!preview.ok){
      box.innerHTML=`<div class="todo-empty">Todo search failed: ${escHtml(preview.data.error||"?")}</div>`;
      return;
    }
    todoLatestCount=preview.data.analyzed||0;
    const capped=preview.data.matched>preview.data.analyzed?` of ${preview.data.matched} matched, capped at ${preview.data.limit}`:"";
    document.getElementById("todo-live-count").textContent=todoSingleEmailId?`${preview.data.analyzed} selected email`:`${preview.data.analyzed} emails selected${capped}`;
    if(!preview.data.matched){
      box.innerHTML='<div class="todo-empty">No emails match these filters.</div>';
      return;
    }
    const message=todoSingleEmailId
      ?`${preview.data.analyzed} selected email will be scanned by the LLM.`
      :`${preview.data.analyzed} local emails will be scanned individually by the LLM${preview.data.matched>preview.data.analyzed?` (${preview.data.matched} matched locally, capped at ${preview.data.limit})`: ""}.`;
    todoPendingPayload=payload;
    llmBtn.hidden=false;
    box.innerHTML=`<div class="todo-empty">${escHtml(message)}<br>Adjust the filters or press Convert using LLM to continue.</div>`;
  }catch(err){
    box.innerHTML=`<div class="todo-empty">Todo search failed: ${escHtml(err.message)}</div>`;
    document.getElementById("todo-live-count").textContent="Count unavailable";
  }
}

["todo-search","todo-start-date","todo-end-date"].forEach(id=>{
  document.getElementById(id).addEventListener("input",()=>{
    clearTimeout(todoPreviewTimer);
    todoPreviewTimer=setTimeout(refreshTodoPreview,250);
  });
});

async function startTodoLlm({skipConfirm=false}={}){
  const btn=document.getElementById("btn-start-todo-llm");
  const box=document.getElementById("todos-results");
  const payload=todoPendingPayload;
  if(!payload){
    box.innerHTML='<div class="todo-empty">Wait for the live email count first.</div>';
    btn.hidden=true;
    return;
  }
  const count=todoLatestCount||0;
  const msg=`Scan ${count} local email${count===1?"":"s"} with the active LLM?\n\nEach email will be sent as a separate request. Emails without a concrete action should produce no todo.`;
  if(!skipConfirm&&!confirm(msg))return;
  btn.disabled=true;
  try{
    box.innerHTML='<div class="todo-empty">Starting todo extraction…</div>';
    updateTodoProgress({current:0,total:count,current_email:null,status:"queued"});
    const started=await fetch("/api/todos/start",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload),
    }).then(async r=>({ok:r.ok,data:await r.json()}));
    if(!started.ok){
      box.innerHTML=`<div class="todo-empty">Todo search failed: ${escHtml(started.data.error||"?")}</div>`;
      return;
    }
    pollTodoJob(started.data.job_id);
  }catch(err){
    box.innerHTML=`<div class="todo-empty">Todo search failed: ${escHtml(err.message)}</div>`;
  }finally{
    btn.disabled=false;
  }
}

document.getElementById("btn-start-todo-llm").addEventListener("click",()=>startTodoLlm());

function updateTodoProgress(job){
  const total=job.total||0,current=job.current||0;
  document.getElementById("todo-progress-count").textContent=`${current} / ${total}`;
  document.getElementById("todo-progress-fill").style.width=total?`${Math.round(current/total*100)}%`:"0%";
  const box=document.getElementById("todo-current-email");
  const mail=job.current_email;
  if(!mail){
    box.innerHTML='<div class="todo-empty">Convert with the LLM to process the filtered emails.</div>';
    return;
  }
  box.innerHTML=`
    <div class="todo-current-card">
      <strong>${escHtml(mail.subject||"(no subject)")}</strong>
      <small>${escHtml(mail.sender||"")}<br>${escHtml(mail.date||"")}</small>
      <pre>${escHtml(mail.body||"[No body text]")}</pre>
    </div>`;
}

function pollTodoJob(jobId){
  clearInterval(todoJobTimer);
  todoJobTimer=setInterval(async()=>{
    try{
      const job=await fetch(`/api/todos/status/${encodeURIComponent(jobId)}`).then(r=>r.json());
      if(job.error)throw new Error(job.error);
      updateTodoProgress(job);
      if(job.status==="done"){
        clearInterval(todoJobTimer);
        renderTodoResults({todos:job.todos||[],matched:job.matched||0,analyzed:job.total||0});
        setStatus("Todo extraction done","ok");
      }else if(job.status==="error"){
        clearInterval(todoJobTimer);
        document.getElementById("todos-results").innerHTML=`<div class="todo-empty">Todo search failed: ${escHtml(job.error||"?")}</div>`;
        setStatus("Todo extraction failed","err");
      }else{
        document.getElementById("todos-results").innerHTML=`<div class="todo-empty">Scanning emails… ${job.current||0} / ${job.total||0}</div>`;
      }
    }catch(err){
      clearInterval(todoJobTimer);
      document.getElementById("todos-results").innerHTML=`<div class="todo-empty">Todo search failed: ${escHtml(err.message)}</div>`;
    }
  },900);
}

function selectedTodosForExport(){
  return [...document.querySelectorAll(".todo-item")].filter(item=>item.querySelector("input[type=checkbox]")?.checked).map(item=>{
    const tags=(item.querySelector(".todo-tags")?.value||"").split(",").map(s=>s.trim()).filter(Boolean);
    return {
      title:item.querySelector(".todo-title")?.value.trim()||"",
      due_date:item.querySelector(".todo-due")?.value.trim()||"",
      description:item.querySelector(".todo-description")?.value.trim()||"",
      tags,
      location:item.querySelector(".todo-location")?.value.trim()||"",
    };
  }).filter(todo=>todo.title);
}

document.getElementById("btn-export-todos").addEventListener("click",async()=>{
  const todos=selectedTodosForExport();
  if(!todos.length){setStatus("No selected todos to export","err");return;}
  try{
    const res=await fetch("/api/todos/export_ics",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({todos}),
    });
    if(!res.ok)throw new Error("Export failed");
    const blob=await res.blob();
    const url=URL.createObjectURL(blob);
    const a=document.createElement("a");
    a.href=url;a.download="email-assistant-todos.ics";
    document.body.appendChild(a);a.click();a.remove();
    URL.revokeObjectURL(url);
    setStatus("Exported todos as .ics","ok");
  }catch(err){setStatus("Todo export failed: "+err.message,"err");}
});

document.getElementById("btn-create-ews-todos").addEventListener("click",async()=>{
  const todos=selectedTodosForExport();
  if(!todos.length){setStatus("No selected todos to create","err");return;}
  if(!currentAccountId){
    setStatus("Select an account before creating Exchange tasks","err");
    document.getElementById("todo-current-email").innerHTML='<div class="todo-empty">Select an account/folder on the left before creating Exchange tasks.</div>';
    return;
  }
  const msg=`Create ${todos.length} task${todos.length===1?"":"s"} in the Exchange account via EWS?\n\nThis writes to the remote account's Tasks folder.`;
  if(!confirm(msg))return;
  const btn=document.getElementById("btn-create-ews-todos");
  btn.disabled=true;
  try{
    setStatus("Creating Exchange tasks…","busy");
    const result=await fetch("/api/todos/export_ews",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({account_id:currentAccountId||"",todos}),
    }).then(async r=>({ok:r.ok,data:await r.json()}));
    if(!result.ok||!result.data.success)throw new Error(result.data.error||"Exchange task creation failed");
    const created=result.data.created||todos.length;
    setStatus(`Created ${created} Exchange task${created===1?"":"s"}`,"ok");
    document.getElementById("todo-current-email").innerHTML=`
      <div class="todo-current-card">
        <strong>Exchange Tasks Created</strong>
        <small>${created} task${created===1?"":"s"} written to the selected account's Exchange Tasks folder via EWS.${result.data.url?`<br>${escHtml(result.data.url)}`:""}<br>Refresh Outlook / Tasks if they do not appear immediately.</small>
        <button class="rbtn todo-action" type="button" id="btn-close-todo-success">Close</button>
      </div>`;
    document.getElementById("btn-close-todo-success")?.addEventListener("click",closeTodoPopover);
  }catch(err){
    setStatus("Exchange tasks failed: "+err.message,"err");
    document.getElementById("todo-current-email").innerHTML=`<div class="todo-empty">Exchange task creation failed: ${escHtml(err.message)}</div>`;
  }finally{
    btn.disabled=false;
  }
});

function closeTodoPopover(){
  const popover=document.getElementById("todo-popover");
  clearInterval(todoJobTimer);
  todoSingleEmailId="";
  ["todo-search","todo-start-date","todo-end-date"].forEach(id=>document.getElementById(id).disabled=false);
  if(popover.close)popover.close();
  else popover.removeAttribute("open");
}
document.getElementById("todo-popover-close").addEventListener("click",closeTodoPopover);
document.getElementById("todo-popover").addEventListener("click",e=>{
  if(e.target.id==="todo-popover")closeTodoPopover();
});
document.addEventListener("click",e=>{
  const wrap=document.getElementById("todo-finder-wrap");
  const popover=document.getElementById("todo-popover");
  if(popover.open&&!wrap.contains(e.target)&&!popover.contains(e.target))closeTodoPopover();
});

// ─── Calendar modal ───────────────────────────────────────────────────────
function calendarWindow(){
  const start=calendarWeekStart||startOfWeek(new Date());
  const end=new Date(start);end.setDate(start.getDate()+7);
  return {start,end};
}

function startOfWeek(date){
  const d=new Date(date);
  d.setHours(0,0,0,0);
  const day=(d.getDay()+6)%7;
  d.setDate(d.getDate()-day);
  return d;
}

function formatCalendarDate(d){
  return d.toLocaleDateString([],{weekday:"short",month:"short",day:"numeric"});
}

function formatCalendarEventTime(ev){
  const s=new Date(ev.start_iso),e=new Date(ev.end_iso);
  if(ev.all_day)return"All day";
  return `${s.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}–${e.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}`;
}

async function openCalendar(){
  if(!calendarWeekStart)calendarWeekStart=startOfWeek(new Date());
  openModal("calendar-modal");
  await loadCalendarAccounts();
  await loadCalendarEvents();
}

async function loadCalendarAccounts(){
  const sel=document.getElementById("calendar-account-filter");
  const accounts=await fetch("/api/calendar/accounts").then(r=>r.json());
  sel.innerHTML='<option value="">All calendar accounts</option>'+accounts.map(a=>{
    const label=`${a.name} · ${a.provider?.name||"Calendar"}`;
    return `<option value="${escHtml(a.id)}">${escHtml(label)}</option>`;
  }).join("");
  if(!accounts.length)sel.innerHTML='<option value="">No calendar accounts configured</option>';
}

async function loadCalendarEvents(){
  const {start,end}=calendarWindow();
  const accountId=document.getElementById("calendar-account-filter").value;
  const qs=new URLSearchParams({start:start.toISOString(),end:end.toISOString()});
  if(accountId)qs.set("account_id",accountId);
  calendarEvents=await fetch(`/api/calendar/events?${qs.toString()}`).then(r=>r.json());
  const labelEnd=new Date(end);labelEnd.setDate(labelEnd.getDate()-1);
  document.getElementById("calendar-window-label").textContent=`${formatCalendarDate(start)} – ${formatCalendarDate(labelEnd)}`;
  renderCalendarEvents();
}

function renderCalendarEvents(){
  const wrap=document.getElementById("calendar-days");
  const detail=document.getElementById("calendar-detail");
  if(!Array.isArray(calendarEvents)||!calendarEvents.length){
    wrap.innerHTML='<div style="color:var(--dim);font-size:11px;padding:12px;">No calendar events in this week. Sync the calendar or move to another week.</div>';
    detail.textContent="Calendar data is stored locally and is available to the LLM after sync.";
    return;
  }
  const {start}=calendarWindow();
  const weekDays=Array.from({length:7},(_,i)=>{const d=new Date(start);d.setDate(start.getDate()+i);return d;});
  const hours=Array.from({length:12},(_,i)=>i+7);
  const dayCols=weekDays.map(()=>[]);
  const allDayCols=weekDays.map(()=>[]);
  for(const ev of calendarEvents){
    const d=new Date(ev.start_iso);
    const eventDay=new Date(d);
    eventDay.setHours(0,0,0,0);
    const idx=Math.floor((eventDay-start)/86400000);
    if(ev.all_day){
      const allDayEnd=new Date(ev.end_iso);
      allDayEnd.setHours(0,0,0,0);
      if(allDayEnd<=eventDay)allDayEnd.setDate(eventDay.getDate()+1);
      for(let i=0;i<7;i++){
        const dayStart=weekDays[i];
        const dayEnd=new Date(dayStart);dayEnd.setDate(dayStart.getDate()+1);
        if(eventDay<dayEnd&&allDayEnd>dayStart)allDayCols[i].push(ev);
      }
    }else{
      if(idx<0||idx>6)continue;
      dayCols[idx].push(ev);
    }
  }
  const now=new Date();
  const nowMinutes=now.getHours()*60+now.getMinutes();
  const todayKey=now.toDateString();
  const showNow=now>=weekDays[0]&&now<new Date(weekDays[6].getTime()+86400000)&&now.getHours()>=7&&now.getHours()<19;
  const nowTop=((nowMinutes-7*60)/60)*48;
  wrap.innerHTML=`
    <div class="calendar-week">
      <div class="calendar-week-header">
        <div class="cal-time-head"></div>
        ${weekDays.map(d=>`<div class="cal-day-head ${d.toDateString()===todayKey?"today":""}">${escHtml(d.toLocaleDateString([],{weekday:"short"}))}<strong>${d.getDate()}</strong></div>`).join("")}
      </div>
      <div class="calendar-all-day-row">
        <div class="cal-all-day-label">all-day</div>
        ${allDayCols.map((events,idx)=>`<div class="cal-all-day-cell ${weekDays[idx].toDateString()===todayKey?"today":""}">${events.map(ev=>`<button class="cal-all-day" data-event-id="${escHtml(ev.uid)}" data-event-start="${escHtml(ev.start_iso)}">${escHtml(ev.title||"(busy)")}</button>`).join("")}</div>`).join("")}
      </div>
      <div class="calendar-grid">
        <div class="cal-time-col">${hours.map(h=>`<div class="cal-time-slot">${String(h).padStart(2,"0")}:00</div>`).join("")}</div>
        ${dayCols.map((events,idx)=>`<div class="cal-day-col ${weekDays[idx].toDateString()===todayKey?"today":""}" data-day="${idx}">${layoutDayEvents(events).map((item)=>eventBlockHtml(item)).join("")}</div>`).join("")}
        ${showNow?`<div class="cal-now-line" style="top:${nowTop}px"></div>`:""}
      </div>
    </div>`;
  wrap.querySelectorAll(".cal-event-block,.cal-all-day").forEach(btn=>btn.addEventListener("click",()=>{
    wrap.querySelectorAll(".cal-event-block,.cal-all-day").forEach(x=>x.classList.remove("active"));
    btn.classList.add("active");
    const ev=calendarEvents.find(x=>x.uid===btn.dataset.eventId&&x.start_iso===btn.dataset.eventStart);
    if(!ev)return;
    detail.innerHTML=calendarDetailHtml(ev);
  }));
  wrap.querySelector(".cal-event-block,.cal-all-day")?.click();
}

function eventMinutes(ev){
  const start=new Date(ev.start_iso),end=new Date(ev.end_iso);
  return {
    startMin:start.getHours()*60+start.getMinutes(),
    endMin:end.getHours()*60+end.getMinutes(),
  };
}

function layoutDayEvents(events){
  const sorted=[...events].sort((a,b)=>new Date(a.start_iso)-new Date(b.start_iso)||new Date(a.end_iso)-new Date(b.end_iso));
  const laidOut=[];
  let cluster=[];
  let clusterEnd=-1;
  const flush=()=>{
    if(!cluster.length)return;
    const columns=[];
    const clusterItems=cluster.map(ev=>{
      const mins=eventMinutes(ev);
      let column=columns.findIndex(end=>end<=mins.startMin);
      if(column<0){column=columns.length;columns.push(mins.endMin);}
      else columns[column]=mins.endMin;
      return {ev,column};
    });
    const total=Math.max(1,columns.length);
    clusterItems.forEach(item=>laidOut.push({...item,total}));
    cluster=[];
    clusterEnd=-1;
  };
  for(const ev of sorted){
    const mins=eventMinutes(ev);
    if(cluster.length&&mins.startMin>=clusterEnd)flush();
    cluster.push(ev);
    clusterEnd=Math.max(clusterEnd,mins.endMin);
  }
  flush();
  return laidOut;
}

function eventBlockHtml(item){
  const ev=item.ev||item;
  const {startMin,endMin}=eventMinutes(ev);
  if(endMin<=7*60||startMin>=19*60)return "";
  const visibleStart=Math.max(startMin,7*60);
  const visibleEnd=Math.min(endMin,19*60);
  const top=((visibleStart-7*60)/60)*48;
  const height=Math.max(22,((visibleEnd-visibleStart)/60)*48);
  const total=item.total||1;
  const column=item.column||0;
  const gap=4;
  const width=`calc(${100/total}% - ${gap}px)`;
  const left=`calc(${(100/total)*column}% + ${gap/2}px)`;
  const classes=["cal-event-block"];
  if(height<34)classes.push("compact");
  if(total>1)classes.push("overlapping");
  if(total>2)classes.push("narrow");
  return `<button class="${classes.join(" ")}" style="--event-height:${height}px;top:${top}px;height:var(--event-height);left:${left};width:${width};right:auto;" data-event-id="${escHtml(ev.uid)}" data-event-start="${escHtml(ev.start_iso)}">
    <span class="cal-event-title">${escHtml(ev.title||"(busy)")}</span>
    <span class="cal-event-time">${escHtml(formatCalendarEventTime(ev))}</span>
  </button>`;
}

function calendarDetailHtml(ev){
  const title=escHtml(ev.title||"(busy)");
  const time=escHtml(formatCalendarEventTime(ev));
  const dateRange=escHtml(`${new Date(ev.start_iso).toLocaleDateString([],{weekday:"short",year:"numeric",month:"short",day:"numeric"})} · ${new Date(ev.start_iso).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})} – ${new Date(ev.end_iso).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}`);
  const busyMatch=(ev.description||"").match(/^Free\/busy:\s*(.+)$/i);
  const busyStatus=ev.free_busy||(busyMatch?busyMatch[1]:"");
  const visibleDescription=busyMatch?"":(ev.description||"");
  const location=ev.location?`<span class="cal-detail-pill">${escHtml(ev.location)}</span>`:"";
  const account=ev.account_id?`<span class="cal-detail-pill">${escHtml(ev.account_id)}</span>`:"";
  const status=busyStatus?`<span class="cal-detail-pill">${escHtml(busyStatus)}</span>`:"";
  const description=visibleDescription?`<div class="cal-detail-description">${escHtml(visibleDescription)}</div>`:"";
  return `<div class="cal-detail-card">
    <div class="cal-detail-main">
      <div class="cal-detail-title">${title}</div>
      <div class="cal-detail-time">${time}</div>
      <div class="cal-detail-date">${dateRange}</div>
    </div>
    <div class="cal-detail-meta">${location}${account}${status}</div>
    ${description}
  </div>`;
}

document.getElementById("calendar-account-filter").addEventListener("change",loadCalendarEvents);
document.getElementById("btn-calendar-prev").addEventListener("click",()=>{calendarWeekStart=calendarWeekStart||startOfWeek(new Date());calendarWeekStart.setDate(calendarWeekStart.getDate()-7);loadCalendarEvents();});
document.getElementById("btn-calendar-next").addEventListener("click",()=>{calendarWeekStart=calendarWeekStart||startOfWeek(new Date());calendarWeekStart.setDate(calendarWeekStart.getDate()+7);loadCalendarEvents();});
document.getElementById("btn-calendar-today").addEventListener("click",()=>{calendarWeekStart=startOfWeek(new Date());loadCalendarEvents();});
document.getElementById("btn-calendar-sync").addEventListener("click",()=>{
  if(taskPollInterval){setStatus("A task is already running","err");return;}
  const accountId=document.getElementById("calendar-account-filter").value;
  fetch("/api/calendar/sync",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({account_id:accountId||undefined})})
    .then(()=>startTaskPoll("Calendar sync",4,()=>loadCalendarEvents()))
    .catch(err=>setStatus("Calendar sync error: "+err.message,"err"));
});

// ─── Debug log modal ──────────────────────────────────────────────────────
let debugEntries=[];
let debugSummary=null;
let debugReadIds=new Set(JSON.parse(localStorage.getItem("mail-log-read-ids")||"[]"));

function saveDebugReadIds(){
  localStorage.setItem("mail-log-read-ids",JSON.stringify([...debugReadIds].slice(-300)));
}

function logEntryId(entry){
  let h=0;
  for(let i=0;i<entry.length;i++)h=((h<<5)-h+entry.charCodeAt(i))|0;
  return String(h);
}

function parseLogEntry(entry){
  if(typeof entry==="object"&&entry){
    const ts=entry.timestamp||"";
    const date=ts?new Date(ts.replace(" ","T")):null;
    return {
      header:entry.header||"",
      ts,
      kind:entry.kind||"log",
      model:entry.model||"",
      date,
      inputTokens:Number(entry.input_tokens)||0,
      outputTokens:Number(entry.output_tokens)||0,
      totalTokens:Number(entry.total_tokens)||0,
      text:entry.text||"",
    };
  }
  const header=(entry.split("\n")[0]||"").trim();
  const match=header.match(/^\[(.*?)\]\s+kind=([^\s]+)\s+model=(.*)$/);
  const ts=match?.[1]||"";
  const kind=match?.[2]||"log";
  const model=(match?.[3]||"").trim();
  const date=ts?new Date(ts.replace(" ","T")):null;
  return {header,ts,kind,model,date,inputTokens:0,outputTokens:0,totalTokens:0,text:entry};
}

function formatLogTime(date){
  if(!date||Number.isNaN(date.getTime()))return"Unknown time";
  const now=new Date();
  const diffMs=Math.max(0,now-date);
  const sec=Math.floor(diffMs/1000);
  const min=Math.floor(sec/60);
  const hour=Math.floor(min/60);
  const clock=date.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});
  const sameDay=date.toDateString()===now.toDateString();
  const yesterday=new Date(now);yesterday.setDate(now.getDate()-1);
  const isYesterday=date.toDateString()===yesterday.toDateString();
  if(sec<60)return `${sec||1} second${sec===1?"":"s"} ago`;
  if(min<5)return `${min} minute${min===1?"":"s"} ${sec%60}s ago`;
  if(min<120)return `${min} minute${min===1?"":"s"} ago`;
  if(sameDay)return hour<12?`${hour}h${min%60?String(min%60).padStart(2,"0")+"m":""} ago`:`today ${clock}`;
  if(isYesterday)return `yesterday ${clock}`;
  return date.toLocaleString([],{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"});
}

function formatTokenCount(n){
  n=Number(n)||0;
  if(n>=1000000)return `${(n/1000000).toFixed(2)}M`;
  if(n>=1000)return `${(n/1000).toFixed(n>=10000?0:1)}k`;
  return String(n);
}

function renderLogSummary(){
  const el=document.getElementById("log-token-summary");
  if(!el)return;
  const s=debugSummary||{};
  const cards=[
    ["Last 24 hours",s.last_24h],
    ["Last 7 days",s.last_7d],
  ];
  el.className="log-summary";
  el.innerHTML=cards.map(([label,row])=>{
    row=row||{entries:0,input_tokens:0,output_tokens:0,total_tokens:0};
    return `<div class="log-summary-card"><strong>${escHtml(label)}</strong><span>${row.entries||0} calls · ${formatTokenCount(row.total_tokens)} total tokens</span><span>In ${formatTokenCount(row.input_tokens)} · Out ${formatTokenCount(row.output_tokens)}</span></div>`;
  }).join("");
}

function renderDebugEntries(){
  const list=document.getElementById("debug-entry-list");
  const detail=document.getElementById("debug-entry-detail");
  list.innerHTML="";
  renderLogSummary();
  if(!debugEntries.length){detail.textContent="No log entries yet.";return;}
  function selectItem(item,entry,id,markRead){
    const meta=parseLogEntry(entry);
    list.querySelectorAll(".log-entry-item").forEach(d=>d.classList.remove("active"));
    item.classList.add("active");
    if(markRead){
      item.classList.remove("unread");
      debugReadIds.add(id);saveDebugReadIds();
    }
    detail.textContent=[
      `Estimated tokens: input ${meta.inputTokens} · output ${meta.outputTokens} · total ${meta.totalTokens}`,
      "",
      meta.text||String(entry||""),
    ].join("\n");
  }
  debugEntries.forEach((entry,i)=>{
    const meta=parseLogEntry(entry);
    const id=logEntryId(meta.text||JSON.stringify(entry));
    const unread=!debugReadIds.has(id);
    const title=[meta.kind,meta.model].filter(Boolean).join(" · ")||meta.header||`Entry ${i+1}`;
    const item=document.createElement("div");
    item.className="log-entry-item"+(unread?" unread":"");
    item.innerHTML=`
      <span class="unread-dot"></span>
      <span class="log-entry-main">
        <span class="log-entry-time">${escHtml(formatLogTime(meta.date))}</span>
        <span class="log-entry-title">${escHtml(title)}</span>
        <span class="log-entry-tokens">In ${escHtml(formatTokenCount(meta.inputTokens))} · Out ${escHtml(formatTokenCount(meta.outputTokens))}</span>
      </span>
      <span class="log-entry-tooltip">${escHtml((meta.header||title)+`\nInput tokens: ${meta.inputTokens}\nOutput tokens: ${meta.outputTokens}\nTotal tokens: ${meta.totalTokens}`)}</span>`;
    item.addEventListener("click",()=>selectItem(item,entry,id,true));
    list.appendChild(item);
  });
  if(list.firstChild){
    const firstMeta=parseLogEntry(debugEntries[0]);
    selectItem(list.firstChild,debugEntries[0],logEntryId(firstMeta.text||JSON.stringify(debugEntries[0])),false);
  }
}

async function loadDebugLog(){
  try{
    const data=await fetch("/api/llm_log").then(r=>r.json());
    debugEntries=data.entries||[];
    debugSummary=data.summary||null;
    renderDebugEntries();
  }catch(e){document.getElementById("debug-entry-detail").textContent="Error loading log: "+e.message;}
}
document.getElementById("btn-debug-refresh").addEventListener("click",loadDebugLog);
document.getElementById("btn-debug-mark-read").addEventListener("click",()=>{
  debugEntries.forEach(entry=>{
    const meta=parseLogEntry(entry);
    debugReadIds.add(logEntryId(meta.text||JSON.stringify(entry)));
  });
  saveDebugReadIds();
  renderDebugEntries();
});
document.getElementById("btn-save-settings").addEventListener("click",saveSettings);
document.getElementById("add-account-btn").addEventListener("click",openNewAccount);
document.getElementById("btn-acct-back").addEventListener("click",()=>{switchTab("tab-accounts");settingsFooterMode("list");});
document.getElementById("btn-propose").addEventListener("click",proposeResponse);
document.getElementById("btn-copy").addEventListener("click",copyResponse);
document.getElementById("btn-copy-done").addEventListener("click",copyResponseAndDone);
document.getElementById("btn-chat-send").addEventListener("click",()=>sendChat(chatInput.value));
chatInput.addEventListener("keydown",e=>{
  if(e.key==="Enter"&&(e.ctrlKey||e.metaKey)){e.preventDefault();sendChat(chatInput.value);}
});
chatInput.addEventListener("input",()=>{chatInput.style.height="auto";chatInput.style.height=Math.min(chatInput.scrollHeight,200)+"px";});

// ─── Column resizer ───────────────────────────────────────────────────────
(()=>{
  const resizer=document.getElementById("row-resizer");
  const emailPanel=document.getElementById("email-panel");
  const responsePanel=document.getElementById("response-panel");
  const panel=document.getElementById("panels");
  const saved=parseFloat(localStorage.getItem("mail-preview-split")||"");
  if(saved>0&&saved<100){
    emailPanel.style.flex=`0 0 ${saved}%`;
    responsePanel.style.flex="1 1 auto";
  }
  let active=false,startY=0,startH=0;
  resizer.addEventListener("mousedown",e=>{
    active=true;startY=e.clientY;startH=emailPanel.getBoundingClientRect().height;
    resizer.classList.add("dragging");
    document.body.style.cursor="row-resize";document.body.style.userSelect="none";
    e.preventDefault();
  });
  document.addEventListener("mousemove",e=>{
    if(!active)return;
    const dy=e.clientY-startY;
    const panelH=panel.getBoundingClientRect().height;
    const newH=Math.max(96,Math.min(startH+dy,panelH-150));
    const pct=Math.round(newH/panelH*1000)/10;
    emailPanel.style.flex=`0 0 ${pct}%`;
    responsePanel.style.flex="1 1 auto";
    localStorage.setItem("mail-preview-split",String(pct));
  });
  document.addEventListener("mouseup",()=>{
    if(!active)return;active=false;
    resizer.classList.remove("dragging");
    document.body.style.cursor="";document.body.style.userSelect="";
  });
})();

(()=>{
  const resizer=document.getElementById("col-resizer");
  const draftCol=document.getElementById("draft-col");
  const panel=document.getElementById("response-panel");
  let active=false,startX=0,startW=0;
  resizer.addEventListener("mousedown",e=>{
    active=true;startX=e.clientX;startW=draftCol.getBoundingClientRect().width;
    resizer.classList.add("dragging");
    document.body.style.cursor="col-resize";document.body.style.userSelect="none";
    e.preventDefault();
  });
  document.addEventListener("mousemove",e=>{
    if(!active)return;
    const dx=e.clientX-startX;
    const panelW=panel.getBoundingClientRect().width;
    const newW=Math.max(200,Math.min(startW+dx,panelW-200-5));
    draftCol.style.flex="none";draftCol.style.width=newW+"px";
  });
  document.addEventListener("mouseup",()=>{
    if(!active)return;active=false;
    resizer.classList.remove("dragging");
    document.body.style.cursor="";document.body.style.userSelect="";
  });
})();

loadMoreBtn.addEventListener("click",()=>{emailOffset+=PAGE_SIZE;loadEmailList(true);});

// ─── Init ─────────────────────────────────────────────────────────────────
loadFolders();
setStatus("Ready","idle");
refreshFinishedToday();
loadActiveLlmPicker();
loadQuickTemplates();

})();
