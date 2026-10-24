import json,sys,time,urllib.request
repo,sha=sys.argv[1],sys.argv[2]
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers={'Accept':'application/vnd.github+json'})) as r: return json.load(r)
while True:
    try:
        runs=get(f'https://api.github.com/repos/cjber/{repo}/actions/workflows/ci.yml/runs?branch=main&event=push&per_page=10')['workflow_runs']
        r=[x for x in runs if x['head_sha'].startswith(sha)]
        if r and r[0]['status']=='completed': print(repo,sha,r[0]['conclusion'],r[0]['id'],flush=True); break
    except Exception: pass
    time.sleep(40)
