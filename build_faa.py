#!/usr/bin/env python3
"""Build compact web data from the FAA National Wildlife Strike Database export.

Input : strikes.csv  (converted from wildlife.faa.gov/assets/database_excel.zip)
Output: out_faa/*.json

Design: every one of the ~352k records is shipped in a packed columnar form so the
site can filter and count exactly, client side. Free-text remarks and full detail
are shipped only for the "notable" subset (damage, injury, fatality, non-bird
species, or a recorded cost), which keeps the payload servable.
"""
import csv, json, os, sys, collections, re

SRC = "strikes.csv"
OUT = "out_faa"
os.makedirs(OUT, exist_ok=True)
csv.field_size_limit(10_000_000)

PHASES = ["Approach","Landing Roll","Take-off Run","Climb","Descent","Departure",
          "En Route","Taxi","Parked","Arrival","Local","Unknown"]

# Species in the FAA list that are not birds. Matched on whole words only, and
# vetoed by any bird word in the name -- otherwise "Killdeer" reads as a deer and
# "Western cattle egret" reads as cattle. Both are birds.
NONBIRD = re.compile(r"\b("
    r"deer|coyote|bat|bats|rabbit|jackrabbit|hare|skunk|opossum|raccoon|armadillo|"
    r"alligator|crocodile|turtle|tortoise|snake|iguana|lizard|fox|woodchuck|groundhog|"
    r"muskrat|beaver|otter|badger|bobcat|lynx|cat|cats|dog|dogs|pig|hog|boar|"
    r"cattle|cow|bull|horse|burro|donkey|mule|moose|elk|antelope|pronghorn|sheep|goat|"
    r"bear|mouse|mice|rat|rats|squirrel|chipmunk|gopher|marmot|prairie|"
    r"porcupine|weasel|mink|ferret|mongoose|wolf|coyotes|caribou|bison|llama|alpaca|"
    r"frog|toad|salamander|fish|mammal|mammals|reptile|reptiles|rodent|rodents|"
    r"flying-fox|peccary|javelina|nutria|vole|shrew|mole|hedgehog|monkey|cottontail|woodrat"
    r")\b", re.I)

# any of these in the name means it is a bird, whatever else matched
BIRDWORD = re.compile(r"\b("
    r"bird|birds|egret|heron|hawk|owl|gull|gulls|duck|ducks|goose|geese|swan|"
    r"warbler|swallow|plover|killdeer|sparrow|finch|falcon|eagle|kestrel|vulture|"
    r"pigeon|dove|crow|raven|starling|lark|blackbird|meadowlark|tern|pelican|"
    r"cormorant|ibis|crane|stork|sandpiper|woodpecker|flycatcher|thrush|robin|"
    r"wren|nighthawk|swift|kingfisher|quail|pheasant|turkey|grouse|coot|rail|"
    r"catbird|kingbird|cowbird|bunting|osprey|harrier|merlin|shrike|waxwing|"
    r"oriole|tanager|grebe|loon|puffin|auk|petrel|shearwater|albatross|"
    r"cuckoo|roadrunner|chickadee|nuthatch|titmouse|vireo|junco|towhee|"
    r"phoebe|pewee|dickcissel|bobolink|chuck-will|whip-poor-will|poorwill|"
    r"gnatcatcher|kinglet|pipit|longspur|dowitcher|godwit|curlew|willet|"
    r"yellowlegs|turnstone|dunlin|knot|avocet|stilt|oystercatcher|skimmer|"
    r"jaeger|kittiwake|anhinga|bittern|limpkin|gallinule|moorhen|"
    r"parakeet|parrot|myna|bulbul|weaver|hornbill|kite|caracara"
    r")\b", re.I)


def is_nonbird(name):
    n = name.lower()
    if BIRDWORD.search(n):
        return False
    return bool(NONBIRD.search(n))


def num(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main():
    airports, species, ops, aircraft = {}, {}, {}, {}
    by_year = collections.Counter()
    by_month = collections.Counter()
    by_phase = collections.Counter()
    by_tod = collections.Counter()
    by_dmglevel = collections.Counter()
    by_height = collections.Counter()
    by_year_dmg = collections.Counter()
    by_sp_month = collections.defaultdict(collections.Counter)
    by_sp_height = collections.defaultdict(list)

    packed = {k: [] for k in
              ("y", "m", "ap", "sp", "d", "ph", "h", "inj", "fat", "cost")}
    notable = []
    n = 0
    min_date, max_date = "9999", "0000"

    with open(SRC, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            n += 1
            yr = r["INCIDENT_YEAR"].strip()
            mo = r["INCIDENT_MONTH"].strip()
            dt = r["INCIDENT_DATE"].strip()
            if dt:
                min_date = min(min_date, dt)
                max_date = max(max_date, dt)

            code = (r["AIRPORT_ID"] or "").strip() or "UNKNOWN"
            aname = (r["AIRPORT"] or "").strip() or "Unknown"
            if code not in airports:
                airports[code] = {
                    "code": code, "name": aname, "state": (r["STATE"] or "").strip(),
                    "lat": num(r["LATITUDE"]), "lon": num(r["LONGITUDE"]),
                    "n": 0, "dmg": 0, "sp": collections.Counter(), "yrs": collections.Counter()}
            A = airports[code]
            A["n"] += 1
            if A["lat"] is None:
                A["lat"], A["lon"] = num(r["LATITUDE"]), num(r["LONGITUDE"])

            sname = (r["SPECIES"] or "").strip() or "Unknown"
            if sname not in species:
                species[sname] = {
                    "name": sname, "id": (r["SPECIES_ID"] or "").strip(),
                    "size": (r["SIZE"] or "").strip(), "n": 0, "dmg": 0,
                    "inj": 0, "fat": 0, "struck": 0,
                    "nonbird": is_nonbird(sname),
                    "ap": collections.Counter()}
            S = species[sname]
            S["n"] += 1
            S["ap"][code] += 1
            A["sp"][sname] += 1
            if yr:
                A["yrs"][yr] += 1

            dmg = 1 if (r["INDICATED_DAMAGE"] or "").strip() in ("1", "True", "TRUE") else 0
            inj = int(num(r["NR_INJURIES"]) or 0)
            fat = int(num(r["NR_FATALITIES"]) or 0)
            cost = (num(r["COST_REPAIRS_INFL_ADJ"]) or 0) + (num(r["COST_OTHER_INFL_ADJ"]) or 0)
            ht = num(r["HEIGHT"])
            phase = (r["PHASE_OF_FLIGHT"] or "").strip() or "Unknown"
            tod = (r["TIME_OF_DAY"] or "").strip() or "Unknown"
            lvl = (r["DAMAGE_LEVEL"] or "").strip()
            struck = int(num(r["NUM_STRUCK"]) or 0) if (r["NUM_STRUCK"] or "").strip().isdigit() else 0

            if dmg:
                A["dmg"] += 1
                S["dmg"] += 1
            S["inj"] += inj
            S["fat"] += fat
            S["struck"] += struck

            if yr:
                by_year[yr] += 1
                if dmg:
                    by_year_dmg[yr] += 1
            if mo:
                by_month[mo] += 1
                by_sp_month[sname][mo] += 1
            by_phase[phase] += 1
            by_tod[tod] += 1
            if lvl:
                by_dmglevel[lvl] += 1
            if ht is not None:
                band = int(ht // 500) * 500 if ht < 10000 else int(ht // 2500) * 2500
                by_height[band] += 1
                by_sp_height[sname].append(ht)

            packed["y"].append(int(yr) if yr.isdigit() else 0)
            packed["m"].append(int(mo) if mo.isdigit() else 0)
            packed["ap"].append(code)
            packed["sp"].append(sname)
            packed["d"].append(dmg)
            packed["ph"].append(phase)
            packed["h"].append(int(ht) if ht is not None else -1)
            packed["inj"].append(inj)
            packed["fat"].append(fat)
            packed["cost"].append(int(cost))

            is_notable = dmg or inj or fat or cost > 0 or species[sname]["nonbird"]
            if is_notable:
                notable.append({
                    "d": dt, "ap": code, "apn": aname, "st": (r["STATE"] or "").strip(),
                    "sp": sname, "ac": (r["AIRCRAFT"] or "").strip(),
                    "op": (r["OPERATOR"] or "").strip(),
                    "ph": phase, "h": int(ht) if ht is not None else None,
                    "dmg": dmg, "lvl": lvl, "inj": inj, "fat": fat,
                    "cost": int(cost),
                    "eff": (r["EFFECT"] or "").strip(),
                    "rem": (r["REMARKS"] or "").strip()[:600],
                    "num": (r["NUM_STRUCK"] or "").strip(),
                    "sent": (r["REMAINS_SENT"] or "").strip(),
                })

            if n % 100000 == 0:
                print("  ...", n, file=sys.stderr, flush=True)

    if n == 0:
        sys.exit("FAIL: no rows read from %s" % SRC)

    # ---- index maps for packed columns -------------------------------------
    ap_list = sorted(airports, key=lambda c: -airports[c]["n"])
    sp_list = sorted(species, key=lambda s: -species[s]["n"])
    ph_list = sorted(by_phase, key=lambda p: -by_phase[p])
    ap_ix = {c: i for i, c in enumerate(ap_list)}
    sp_ix = {s: i for i, s in enumerate(sp_list)}
    ph_ix = {p: i for i, p in enumerate(ph_list)}
    packed["ap"] = [ap_ix[c] for c in packed["ap"]]
    packed["sp"] = [sp_ix[s] for s in packed["sp"]]
    packed["ph"] = [ph_ix[p] for p in packed["ph"]]

    def median(v):
        if not v:
            return None
        v = sorted(v)
        return v[len(v) // 2]

    airports_out = []
    for c in ap_list:
        a = airports[c]
        if a["n"] < 1:
            continue
        airports_out.append({
            "c": c, "n": a["name"], "s": a["state"],
            "lat": round(a["lat"], 5) if a["lat"] else None,
            "lon": round(a["lon"], 5) if a["lon"] else None,
            "t": a["n"], "d": a["dmg"],
            "top": [[k, v] for k, v in a["sp"].most_common(8)],
        })

    species_out = []
    for s in sp_list:
        S = species[s]
        hts = by_sp_height.get(s, [])
        species_out.append({
            "n": s, "id": S["id"], "sz": S["size"], "t": S["n"], "d": S["dmg"],
            "inj": S["inj"], "fat": S["fat"], "nb": 1 if S["nonbird"] else 0,
            "mh": median(hts), "mx": int(max(hts)) if hts else None,
            "top": [[k, v] for k, v in S["ap"].most_common(6)],
            "mo": [by_sp_month[s].get(str(m), 0) for m in range(1, 13)],
        })

    meta = {
        "source": "FAA National Wildlife Strike Database",
        "source_url": "https://wildlife.faa.gov/",
        "download": "https://wildlife.faa.gov/assets/database_excel.zip",
        "records": n,
        "date_min": min_date, "date_max": max_date,
        "airports": len(airports_out), "species": len(species_out),
        "notable": len(notable),
        "with_coords": sum(1 for a in airports_out if a["lat"]),
        "damaging": sum(by_year_dmg.values()),
        "phases": ph_list, "airport_index": ap_list, "species_index": sp_list,
    }

    agg = {
        "year": dict(by_year), "year_dmg": dict(by_year_dmg),
        "month": dict(by_month), "phase": dict(by_phase),
        "tod": dict(by_tod), "dmglevel": dict(by_dmglevel),
        "height": dict(sorted(by_height.items())),
    }

    notable.sort(key=lambda r: r["d"], reverse=True)

    def dump(name, obj):
        p = os.path.join(OUT, name)
        with open(p, "w") as f:
            json.dump(obj, f, separators=(",", ":"))
        return os.path.getsize(p)

    sizes = {
        "meta.json": dump("meta.json", meta),
        "agg.json": dump("agg.json", agg),
        "airports.json": dump("airports.json", airports_out),
        "species.json": dump("species.json", species_out),
        "packed.json": dump("packed.json", packed),
        "notable.json": dump("notable.json", notable),
    }
    print("\nrows=%d  airports=%d  species=%d  notable=%d  damaging=%d"
          % (n, len(airports_out), len(species_out), len(notable), meta["damaging"]),
          file=sys.stderr)
    print("dates %s .. %s" % (min_date, max_date), file=sys.stderr)
    for k, v in sizes.items():
        print("  %-16s %8.1f MB" % (k, v / 1e6), file=sys.stderr)


if __name__ == "__main__":
    main()
