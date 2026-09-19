const fs = require('fs');
const cp = require('child_process');
const repo = '/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder';
const mode = process.argv[2];
const apply = process.argv[3] === 'apply';
if (!['local', 'remote'].includes(mode)) throw new Error('Expected local or remote');
const batch = mode === 'local' ? 4 : 5;
const data = JSON.parse(fs.readFileSync(repo + '/docs/recovery/2026-09-04-branch-cleanup-batch' + batch + '.json', 'utf8'));
function run(bin, args, input) { return cp.execFileSync(bin, args, {cwd:repo,encoding:'utf8',input,maxBuffer:64*1024*1024,timeout:120000}); }
function git(args, input) { return run('git', args, input).trim(); }
if (git(['rev-parse','origin/main']) !== data.main) throw new Error('Main changed');
const history = new Map(git(['log',data.main,'--format=%H %T']).split('\n').map(s=>s.split(' ')));
const refs = new Map(git(['for-each-ref','--format=%(refname) %(objectname) %(tree)']).split('\n').map(s=>{const [r,sha,tree]=s.split(' ');return [r,{sha,tree}];}));
const pinnedNow = () => new Set([...git(['worktree','list','--porcelain']).matchAll(/^branch refs\/heads\/(.+)$/gm)].map(m=>m[1]));
let pinned = pinnedNow();
let live, open;
if (mode === 'remote') {
  live = new Map(git(['ls-remote','--heads','origin']).split('\n').map(s=>{const [sha,ref]=s.split(/\s+/);return [ref,sha];}));
  if (live.get('refs/heads/main') !== data.main) throw new Error('Live main changed');
  open = new Set(JSON.parse(run('gh',['pr','list','--state','open','--limit','1000','--json','headRefName'])).map(p=>p.headRefName));
}
const patch = (a,b) => git(['diff','--no-ext-diff','--no-color','--no-renames','--binary','--full-index','--unified=3',a,b]);
const normalize = s => s.split('\n').filter(l=>!l.startsWith('index ')&&!l.startsWith('@@ ')).join('\n');
const verified=[], held=[];
for (const b of data.branches) {
  const name = b.ref.replace(mode==='local' ? /^refs\/heads\// : /^refs\/remotes\/origin\//,'');
  let reason = null;
  if(name === 'main' || name === 'HEAD' || pinned.has(name)) reason='Current worktree/protected';
  else if(refs.get(b.ref)?.sha !== b.sha || refs.get(b.ref)?.tree !== b.tree) reason='Ref or tree changed';
  else if(mode==='remote' && (live.get('refs/heads/'+name)!==b.sha || open.has(name))) reason='Remote moved or open PR';
  if(!reason) {
    if(b.evidence==='ANCESTOR') {
      if(history.get(b.sha)!==b.tree) reason='Historical content mismatch';
    } else {
      const base=git(['merge-base',data.main,b.sha]);
      if(base!==b.base) reason='Merge base changed';
      else {
        const paths=run('git',['diff','--name-only','-z',base,b.sha]).split('\0').filter(Boolean);
        const equal=paths.length===0 || git(['diff','--no-ext-diff',b.sha,data.main,'--',...paths])==='';
        if(equal) b.finalEvidence='All changed-path contents equal current main';
        else if(b.aggregateMatch && history.has(b.aggregateMatch) && normalize(patch(base,b.sha))===normalize(patch(b.aggregateMatch+'^1',b.aggregateMatch))) b.finalEvidence='Whitespace-preserving aggregate patch equal main integration';
        else reason='Stricter whitespace-preserving content proof did not match; held';
      }
    }
  }
  if(reason) held.push({ref:b.ref,sha:b.sha,reason}); else verified.push({...b,name});
}
// Recheck ownership at the mutation boundary, after potentially slow content work.
pinned=pinnedNow();
for(let i=verified.length-1;i>=0;i--) if(pinned.has(verified[i].name)) {const b=verified.splice(i,1)[0];held.push({ref:b.ref,sha:b.sha,reason:'New worktree ownership during audit'});}
console.log(JSON.stringify({batch,mode,apply,candidates:data.branches.length,verified:verified.length,held}));
if(!apply) process.exit(0);
const zero='0'.repeat(40);
const tx=['start'];
for(const b of verified) {
  const recovery='refs/recovery/2026-09-04/'+mode+'/'+b.name;
  if(refs.has(recovery)) {if(refs.get(recovery).sha!==b.sha) throw new Error('Recovery collision');}
  else tx.push('create '+recovery+' '+b.sha);
  if(mode==='local') tx.push('delete '+b.ref+' '+b.sha);
}
tx.push('prepare','commit','');
if(verified.length) console.log(git(['update-ref','--stdin'],tx.join('\n')));
if(mode==='remote' && verified.length) {
  const args=['push','--atomic',...verified.map(b=>'--force-with-lease=refs/heads/'+b.name+':'+b.sha),'origin',...verified.map(b=>':refs/heads/'+b.name)];
  console.log(run('git',args));
  const after = new Set(git(['ls-remote','--heads','origin']).split('\n').map(s=>s.split(/\s+/)[1]));
  for(const b of verified) if(after.has('refs/heads/'+b.name)) throw new Error('Remote deletion verification failed '+b.name);
} else if(mode==='local') {
  const after=new Set(git(['for-each-ref','--format=%(refname)','refs/heads']).split('\n'));
  for(const b of verified) if(after.has(b.ref)) throw new Error('Local deletion verification failed '+b.ref);
}
console.log(JSON.stringify({batch,completed:true,deleted:verified.length,deletedRefs:verified.map(b=>({ref:b.ref,sha:b.sha,evidence:b.finalEvidence||b.evidence})),held}));
