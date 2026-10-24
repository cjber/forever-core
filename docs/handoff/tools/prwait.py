import json,sys,time,urllib.request
prs=[a.split('#') for a in sys.argv[1:]]
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers={'Accept':'application/vnd.github+json'})) as r: return json.load(r)
done={}
while len(done)<len(prs):
    for repo,n in prs:
        if (repo,n) in done: continue
        try:
            p=get(f'https://api.github.com/repos/cjber/{repo}/pulls/{n}')
            if p['state']!='open': done[(repo,n)]=p['state']; print(repo,n,'closed/merged',flush=True); continue
            sha=p['head']['sha']
            runs=get(f'https://api.github.com/repos/cjber/{repo}/commits/{sha}/check-runs?per_page=100')['check_runs']
            if len(runs)>=3 and all(r['status']=='completed' for r in runs):
                bad=[r['name'] for r in runs if r['conclusion'] not in ('success','skipped','neutral')]
                done[(repo,n)]=1; print(repo,n,sha,'FAIL '+','.join(bad) if bad else 'GREEN',flush=True)
        except Exception as e: pass
    time.sleep(45)
