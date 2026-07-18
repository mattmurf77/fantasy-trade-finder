"""Generate golden vectors for backend/analytics_stats.py from scipy.

Run offline (scipy is NOT in requirements.txt); commit the JSON. The stats
module ships stdlib-only and is asserted against these vectors to 1e-9.
    python3 -m backend.tools.gen_stats_golden
"""
import json, os
from scipy import stats
from scipy import special

OUT = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "stats_golden.json")

def main():
    g = {}
    g["norm_cdf"] = [[x, float(stats.norm.cdf(x))] for x in
                     (-3.5,-2.0,-1.0,-0.5,0.0,0.5,1.0,1.96,2.5758,3.0)]
    g["norm_ppf"] = [[p, float(stats.norm.ppf(p))] for p in
                     (0.001,0.01,0.025,0.05,0.1,0.5,0.9,0.95,0.975,0.99,0.999)]
    g["betainc"] = [[a,b,x, float(special.betainc(a,b,x))] for (a,b,x) in
                    [(0.5,0.5,0.3),(2,3,0.4),(5,2,0.7),(10,10,0.5),(1.5,3.2,0.25),(50,50,0.51)]]
    g["gammainc_lower"] = [[s,x, float(special.gammainc(s,x))] for (s,x) in
                    [(0.5,0.3),(1.0,2.0),(2.5,1.0),(5.0,10.0),(3.0,3.0),(10.0,5.0)]]
    g["chi2_sf"] = [[x,k, float(stats.chi2.sf(x,k))] for (x,k) in
                    [(3.84,1),(5.99,2),(10.83,1),(0.5,3),(20.0,10),(1.0,1)]]
    g["t_sf_two_sided"] = [[t,df, float(2*stats.t.sf(abs(t),df))] for (t,df) in
                    [(2.0,10),(1.96,1000),(3.0,5),(0.5,20),(2.5,15.7)]]
    # composite tests
    tp = []
    for (x1,n1,x2,n2) in [(30,100,45,100),(10,50,12,48),(200,1000,230,1000)]:
        p1,p2 = x1/n1, x2/n2
        pp = (x1+x2)/(n1+n2)
        se = (pp*(1-pp)*(1/n1+1/n2))**0.5
        z = (p2-p1)/se
        pval = 2*stats.norm.sf(abs(z))
        tp.append([x1,n1,x2,n2, float(z), float(pval)])
    g["two_proportion_z"] = tp
    wl = []
    for (m1,v1,n1,m2,v2,n2) in [(10.0,4.0,30,11.0,5.0,28),(100.,400.,50,90.,360.,55)]:
        s1,s2 = v1/n1, v2/n2
        t = (m2-m1)/((s1+s2)**0.5)
        df = (s1+s2)**2/(s1**2/(n1-1)+s2**2/(n2-1))
        pval = 2*stats.t.sf(abs(t),df)
        wl.append([m1,v1,n1,m2,v2,n2, float(t), float(df), float(pval)])
    g["welch_t"] = wl
    srm = []
    for obs,w in [([510,490],[5000,5000]),([340,330,330],[3333,3333,3334]),([600,400],[5000,5000])]:
        tot=sum(obs); ws=sum(w)
        chi2=sum((o-tot*(wi/ws))**2/(tot*(wi/ws)) for o,wi in zip(obs,w))
        df=len(obs)-1
        p=float(stats.chi2.sf(chi2,df))
        srm.append([obs,w, float(chi2), df, p])
    g["srm"] = srm
    with open(OUT,"w") as f: json.dump(g,f,indent=1)
    print("wrote", os.path.abspath(OUT))

if __name__=="__main__": main()
