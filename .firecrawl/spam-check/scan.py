import json, glob, os
kw = json.load(open("keywords.json"))
lists = {"japanese":kw["japanese"], "french":kw["french"], "other":kw["otherGamblingSpamSignals"]}
idx_to_dom = {
 25:"bestdentistbrooklyn.com",26:"ladentalboutique.com",27:"dentist93036.com",28:"brooklyndentist.com",
 29:"dentalofficeinbrooklyn.com",30:"dentistinbrooklynheights.com",31:"jasonacurtisdmd.com",
 32:"newportdentalgroup.org",33:"westwindintegratedhealth.com",34:"allon4teeth.com",
 35:"implantdentistinbrooklyn.com",36:"emergencydentistbrooklyn.com",37:"lancastertotaldentistry.com",
 38:"palmdaletotaldentistry.com",39:"ovaldental.com"}
matches=[]
counts={}
for idx in sorted(idx_to_dom):
    dom=idx_to_dom[idx]
    f=f".firecrawl/spam-check/idx{idx}.json"
    web=[]
    if os.path.exists(f):
        try:
            d=json.load(open(f))
            web=d.get("data",{}).get("web",[]) or []
        except Exception:
            web=[]
    counts[idx]=(dom,len(web))
    for i,r in enumerate(web):
        pos=r.get("position", i+1)
        page=(pos-1)//10+1
        hay=" ".join([str(r.get("title","")),str(r.get("description","")),str(r.get("url",""))]).lower()
        for listname,terms in lists.items():
            for t in terms:
                if t.lower() in hay:
                    matches.append({"idx":idx,"domain":dom,"keyword":t,"list":listname,
                        "snippet":str(r.get("description","")).strip(),"url":r.get("url",""),"page":page})
print("=== RESULT COUNTS ===")
for idx in sorted(counts):
    print(f"idx{idx} {counts[idx][0]}: {counts[idx][1]} results")
print("\n=== MATCHES:", len(matches), "===")
for m in matches:
    print(json.dumps(m, ensure_ascii=False))
json.dump(matches, open(".firecrawl/spam-check/matches.json","w"), ensure_ascii=False, indent=2)
