#!/usr/bin/env python3
import concurrent.futures, json, os, re, ssl, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin

SOURCE=Path("IPTV_Mundial_Jorge.m3u")
OUT=Path("IPTV_Mundial_Jorge_ESTABLE.m3u")
HISTORY=Path("stream_history.json")
REPORT=Path("estado_canales.txt")
TIMEOUT=8
WORKERS=80
UA="Mozilla/5.0 IPTV-Mundial-Jorge-Checker/1.0"

def parse():
    lines=SOURCE.read_text(encoding="utf-8",errors="ignore").splitlines()
    out=[]; info=None
    for line in lines:
        line=line.strip()
        if line.startswith("#EXTINF:"): info=line
        elif info and line and not line.startswith("#"):
            out.append((info,line)); info=None
    return out

def get(url, limit=131072):
    req=Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    ctx=ssl.create_default_context()
    with urlopen(req,timeout=TIMEOUT,context=ctx) as r:
        code=getattr(r,"status",200)
        ctype=(r.headers.get("Content-Type") or "").lower()
        data=r.read(limit)
        return code,ctype,data,r.geturl()

def check(item):
    info,url=item
    try:
        code,ctype,data,final=get(url)
        if not (200 <= code < 400) or not data: return url,False
        text=data[:8192].decode("utf-8","ignore")
        # HLS master/media playlist: require M3U and at least one URI/tag.
        if "#EXTM3U" in text:
            candidates=[x.strip() for x in text.splitlines() if x.strip() and not x.startswith("#")]
            if not candidates: return url,False
            # Probe one referenced playlist/segment when possible.
            target=urljoin(final,candidates[0])
            try:
                c2,t2,d2,_=get(target,65536)
                return url,(200 <= c2 < 400 and len(d2)>0)
            except Exception:
                # Master itself is valid; some CDNs reject generic segment probes.
                return url,True
        # Direct media streams accepted only when response looks like media.
        media=("video/" in ctype or "audio/" in ctype or
               "application/octet-stream" in ctype or data[:1]==b"G")
        return url,media
    except Exception:
        return url,False

def main():
    entries=parse()
    old={}
    if HISTORY.exists():
        try: old=json.loads(HISTORY.read_text(encoding="utf-8"))
        except Exception: old={}
    current={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs=[ex.submit(check,e) for e in entries]
        for i,f in enumerate(concurrent.futures.as_completed(futs),1):
            u,ok=f.result(); current[u]=ok
            if i%500==0: print(f"checked {i}/{len(entries)}")
    hist={}
    for _,u in entries:
        prev=old.get(u,[])
        if not isinstance(prev,list): prev=[]
        hist[u]=(prev+[bool(current.get(u,False))])[-3:]
    # Stable after at least 2 observations and >=2 successes in last 3.
    stable={u for u,h in hist.items() if len(h)>=2 and sum(h)>=2}
    body=["#EXTM3U"]
    for info,u in entries:
        if u in stable: body.extend([info,u])
    OUT.write_text("\n".join(body)+"\n",encoding="utf-8")
    HISTORY.write_text(json.dumps(hist,separators=(",",":")),encoding="utf-8")
    REPORT.write_text(
        f"Total fuente: {len(entries)}\n"
        f"Funcionaron esta ronda: {sum(current.values())}\n"
        f"Lista estable (>=2 exitos en ultimas 3 rondas): {len(stable)}\n"
        f"Generado UTC: {time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime())}\n",
        encoding="utf-8")
if __name__=="__main__": main()
