"""Synthetic Maharashtra data: 3 schemes (different column names, messy district names) + 1 outcome file."""
import numpy as np, pandas as pd, random, os
H = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(H, "raw")
rng = np.random.default_rng(7); random.seed(7)
D = [("Ahmednagar",19.09,74.74,45,"Ahmadnagar|Ahilyanagar"),("Akola",20.71,77.00,18,""),("Amravati",20.93,77.75,28,""),
("Aurangabad",19.88,75.34,37,"Chhatrapati Sambhajinagar|Sambhajinagar"),("Beed",18.99,75.76,26,"Bid"),("Bhandara",21.17,79.65,12,""),
("Buldhana",20.53,76.18,26,"Buldana"),("Chandrapur",19.96,79.30,22,""),("Dhule",20.90,74.77,20,""),("Gadchiroli",20.18,80.00,10,""),
("Gondia",21.46,80.19,13,"Gondiya"),("Hingoli",19.72,77.15,12,""),("Jalgaon",21.01,75.56,42,""),("Jalna",19.84,75.88,20,""),
("Kolhapur",16.70,74.24,38,""),("Latur",18.40,76.58,24,""),("Mumbai City",18.96,72.83,31,""),("Mumbai Suburban",19.18,72.95,93,"Mumbai Sub.|Mumbai Subn"),
("Nagpur",21.15,79.09,46,""),("Nanded",19.16,77.32,33,""),("Nandurbar",21.37,74.24,16,""),("Nashik",20.00,73.79,61,"Nasik"),
("Osmanabad",18.18,76.04,17,"Dharashiv"),("Palghar",19.70,72.77,30,""),("Parbhani",19.27,76.77,18,""),("Pune",18.52,73.86,94,""),
("Raigad",18.52,73.18,26,"Raigarh"),("Ratnagiri",16.99,73.30,16,""),("Sangli",16.85,74.58,28,""),("Satara",17.68,74.00,30,""),
("Sindhudurg",16.35,73.75,8,""),("Solapur",17.66,75.91,43,"Sholapur"),("Thane",19.22,73.00,111,"Thana"),("Wardha",20.75,78.60,13,""),
("Washim",20.11,77.13,11,""),("Yavatmal",20.39,78.12,27,"Yeotmal")]
TRIBAL = {"Gadchiroli","Nandurbar","Palghar","Dhule","Yavatmal"}
URBAN = {"Mumbai City":0.0,"Mumbai Suburban":0.0,"Thane":0.25,"Pune":0.45,"Nagpur":0.35,"Nashik":0.5}
SCH = {"mgnrega":("MGNREGA",1.2,["district_name","fin_year","sanctioned_cr","released_cr","expenditure_cr","households"]),
       "pmayg":("PMAY-G",0.8,["District","Year","Allocated","Released","Spent","Houses"]),
       "jjm":("JJM",1.0,["dist","fy","alloc","rel","exp","connections"])}
BAD = {("Gadchiroli","PMAY-G"),("Nandurbar","JJM"),("Beed","MGNREGA"),("Yavatmal","JJM"),("Nanded","PMAY-G")}  # planted low utilisation
OVER = {"Solapur","Jalgaon","Nashik"}  # planted: heavy multi-scheme funding, poor outcomes

def mess(n, al):
    s = random.choice([n]*3 + (al.split("|") if al else [])); r = random.random()
    if r < .2: s = s.upper()
    elif r < .35: s = s.lower()
    elif r < .5: s += " Dist."
    elif r < .6: s += " District"
    elif r < .8 and len(s) > 4:
        i = random.randrange(1, len(s)-1); s = s[:i] + s[i+1:]
    return s

def main():
    os.makedirs(RAW, exist_ok=True)
    rows = []
    for i, (n, la, lo, p, al) in enumerate(D):
        rural = URBAN.get(n, round(rng.uniform(.55, .9), 2)); tr = round(rng.uniform(.3, .6), 2) if n in TRIBAL else round(rng.uniform(.02, .15), 2)
        rows.append(dict(id=f"MH{i+1:02d}", name=n, aliases=al, lat=la, lon=lo, population_lakh=p, rural_share=rural, tribal_share=tr))
    pd.DataFrame(rows).to_csv(os.path.join(H, "districts_master.csv"), index=False)
    M = {r["name"]: r for r in rows}; spent_tot = {n: 0.0 for n in M}
    for key, (scheme, rate, cols) in SCH.items():
        out = []
        for n, la, lo, p, al in D:
            for y in range(2019, 2024):
                a = p*rate*1.06**(y-2019)*rng.uniform(.8, 1.2)*(2 if n in OVER else 1)
                bad = (n, scheme) in BAD
                rel = a*(0.55 if bad else rng.uniform(.82, .98)); sp = rel*(0.45 if bad else rng.uniform(.78, .97))
                spent_tot[n] += sp
                yr = f"{y}-{str(y+1)[2:]}" if key == "mgnrega" else (f"FY{y}" if key == "jjm" else y)
                out.append([mess(n, al), yr, round(a, 2), round(rel, 2), round(sp, 2), int(a*rng.uniform(900, 1400))])
        pd.DataFrame(out, columns=cols).to_csv(os.path.join(RAW, f"{key}.csv"), index=False)
    pc = pd.Series({n: spent_tot[n]/M[n]["population_lakh"] for n in M}); z = (pc-pc.mean())/pc.std()
    o = []
    for n, la, lo, p, al in D:
        v = 62-25*M[n]["tribal_share"]+6*(1-M[n]["rural_share"])+rng.normal(0, 2)-(14 if n in OVER else 0)
        o.append([mess(n, al), 2023, "Development index (0-100)", round(float(np.clip(v, 20, 90)), 1)])
    pd.DataFrame(o, columns=["district", "year", "indicator", "value"]).to_csv(os.path.join(RAW, "outcome.csv"), index=False)

if __name__ == "__main__": main()
