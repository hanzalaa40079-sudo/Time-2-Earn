
import os, re, json, tempfile, subprocess, secrets
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Time 2 Earn V2", page_icon="🎬", layout="wide")

DATA = Path("time2earn_v2_data")
DATA.mkdir(exist_ok=True)
TOKENS = DATA / "tokens.json"
GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v23.0")

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout[-6000:])
    return p.stdout

def download_video(url, outdir):
    out = str(Path(outdir) / "source.%(ext)s")
    run(["yt-dlp", "--no-playlist", "-f", "bv*+ba/b", "--merge-output-format", "mp4", "-o", out, url])
    files = list(Path(outdir).glob("source.*"))
    if not files: raise RuntimeError("Video download failed.")
    return str(files[0])

def transcribe(video, model_name):
    import whisper
    return whisper.load_model(model_name).transcribe(video, fp16=False)

def srt_time(sec):
    sec=max(0,float(sec)); h=int(sec//3600); sec-=h*3600; m=int(sec//60); sec-=m*60
    s=int(sec); ms=int(round((sec-s)*1000))
    if ms>=1000: s+=1; ms=0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def write_srt(segments,start,end,path):
    rows=[]; n=1
    for x in segments:
        a,b=float(x["start"]),float(x["end"])
        if b<=start or a>=end: continue
        aa,bb=max(a,start)-start,min(b,end)-start
        t=x["text"].strip()
        if t: rows += [str(n),f"{srt_time(aa)} --> {srt_time(bb)}",t,""]; n+=1
    Path(path).write_text("\n".join(rows),encoding="utf-8")

def make_clip(video,start,duration,srt,out):
    s=str(srt).replace("\\","/").replace(":","\\:").replace("'","\\'")
    vf=f"scale=1080:-2,crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2,subtitles='{s}'"
    run(["ffmpeg","-y","-ss",str(start),"-i",video,"-t",str(duration),"-vf",vf,
         "-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-b:a","128k",out])

def choose_clips(result,n,length):
    segs=result.get("segments",[])
    if not segs: return []
    keys=["how","why","best","top","mistake","secret","money","tip","important","never","truth","problem","solution","amazing","first","finally"]
    cand=[]
    for s in segs:
        txt=s["text"].lower()
        score=sum(txt.count(k) for k in keys)+min(len(txt)/80,2)
        cand.append((score,float(s["start"])))
    cand.sort(reverse=True)
    chosen=[]
    for score,t in cand:
        x=max(0,t-length*.30)
        if all(abs(x-y)>length*.75 for y in chosen): chosen.append(x)
        if len(chosen)>=n: break
    total=max(float(segs[-1]["end"]),1)
    for i in range(n):
        x=min(i*max(length*.9,total/n),max(0,total-length))
        if len(chosen)>=n: break
        if all(abs(x-y)>length*.5 for y in chosen): chosen.append(x)
    return sorted(chosen[:n])

def make_metadata(text, idx):
    clean=re.sub(r"\s+"," ",text).strip()
    words=clean.split()
    snippet=" ".join(words[:22])
    if not snippet: snippet=f"Must-watch moment #{idx}"
    title=(snippet[:82].rstrip(" ,.!?") + " #Shorts")
    # simple free keyword extraction
    stop=set("the and for with that this from have your you are was were but not what when where how why into about just they their then than very more".split())
    freq={}
    for w in re.findall(r"[A-Za-z][A-Za-z0-9']{3,}",clean.lower()):
        if w not in stop: freq[w]=freq.get(w,0)+1
    tags=[w for w,_ in sorted(freq.items(),key=lambda x:x[1],reverse=True)[:8]]
    hashtags=" ".join("#"+x for x in tags)+(" #Shorts #Time2Earn" if "#Shorts" not in hashtags else " #Time2Earn")
    desc=clean[:800] + "\n\n#Shorts #Time2Earn " + hashtags.replace("#Shorts ","")
    return title[:100],desc[:5000],tags[:10]

def save_tokens(d):
    TOKENS.write_text(json.dumps(d,indent=2),encoding="utf-8")
def load_tokens():
    try: return json.loads(TOKENS.read_text(encoding="utf-8"))
    except: return {}

# ---- YouTube OAuth ----
def youtube_auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    scopes=["https://www.googleapis.com/auth/youtube.upload"]
    secret=Path("client_secret.json")
    if not secret.exists(): raise RuntimeError("Put your Google OAuth desktop client file in this folder as client_secret.json.")
    flow=InstalledAppFlow.from_client_secrets_file(str(secret),scopes)
    creds=flow.run_local_server(port=0,open_browser=True)
    save_tokens({**load_tokens(),"youtube":json.loads(creds.to_json())})
    return "YouTube connected."

def youtube_upload(path,title,desc,tags,privacy):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    tok=load_tokens().get("youtube")
    if not tok: raise RuntimeError("Connect YouTube first.")
    creds=Credentials.from_authorized_user_info(tok,["https://www.googleapis.com/auth/youtube.upload"])
    yt=build("youtube","v3",credentials=creds)
    body={"snippet":{"title":title,"description":desc,"tags":tags,"categoryId":"22"},
          "status":{"privacyStatus":privacy,"selfDeclaredMadeForKids":False}}
    req=yt.videos().insert(part="snippet,status",body=body,
        media_body=MediaFileUpload(path,chunksize=-1,resumable=True))
    resp=None
    while resp is None:
        _,resp=req.next_chunk()
    return "https://www.youtube.com/watch?v="+resp["id"]

# ---- Facebook Page publishing ----
def fb_upload(path,title,desc):
    import requests
    tok=load_tokens().get("facebook",{})
    page_id=tok.get("page_id"); page_token=tok.get("page_access_token")
    if not page_id or not page_token:
        raise RuntimeError("Add a Facebook Page ID and Page Access Token in the sidebar first.")
    url=f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/videos"
    with open(path,"rb") as f:
        r=requests.post(url,data={"access_token":page_token,"title":title,"description":desc},
                        files={"source":("short.mp4",f,"video/mp4")},timeout=600)
    if r.status_code>=400: raise RuntimeError(r.text)
    data=r.json()
    return data.get("id",str(data))

st.title("🎬 Time 2 Earn V2")
st.caption("Free long-video → Shorts → captions → metadata → one-click publishing")

with st.sidebar:
    st.header("🔐 Connections")
    st.subheader("YouTube")
    if st.button("🔗 Connect YouTube"):
        try: st.success(youtube_auth())
        except Exception as e: st.error(str(e))
    yt_connected=bool(load_tokens().get("youtube"))
    st.write("Status:", "🟢 Connected" if yt_connected else "⚪ Not connected")
    st.caption("Requires your own Google OAuth client_secret.json.")

    st.subheader("Facebook Page")
    fb=load_tokens().get("facebook",{})
    page_id=st.text_input("Facebook Page ID",value=fb.get("page_id",""))
    page_token=st.text_input("Page Access Token",value=fb.get("page_access_token",""),type="password")
    if st.button("💾 Save Facebook connection"):
        save_tokens({**load_tokens(),"facebook":{"page_id":page_id.strip(),"page_access_token":page_token.strip()}})
        st.success("Facebook settings saved.")
    st.caption("Use a Page access token created through Meta's official OAuth flow. Never use your Facebook password.")

    st.subheader("Publishing")
    privacy=st.selectbox("YouTube privacy",["private","unlisted","public"],index=0)
    publish_yt=st.checkbox("Publish to YouTube",value=True)
    publish_fb=st.checkbox("Publish to Facebook Page",value=False)

url=st.text_input("🔗 Long video URL",placeholder="Paste a URL supported by yt-dlp")
c1,c2,c3=st.columns(3)
with c1: count=st.slider("Shorts",1,10,3)
with c2: length=st.slider("Length (sec)",15,60,45)
with c3: model=st.selectbox("Whisper model",["tiny","base","small"],1)

if st.button("🚀 Generate Shorts",type="primary"):
    if not url.strip(): st.error("Paste a video URL."); st.stop()
    job=Path(tempfile.mkdtemp(prefix="time2earn_v2_"))
    try:
        with st.status("Working…",expanded=True) as status:
            st.write("Downloading…"); video=download_video(url.strip(),job)
            st.write("Transcribing…"); result=transcribe(video,model)
            starts=choose_clips(result,count,length)
            if not starts: raise RuntimeError("No speech/transcript was found.")
            items=[]
            for i,start in enumerate(starts,1):
                dur=min(length,max(1,float(result["segments"][-1]["end"])-start))
                srt=job/f"{i}.srt"; out=job/f"Time2Earn_V2_{i}.mp4"
                write_srt(result["segments"],start,start+dur,srt)
                make_clip(video,start,dur,srt,out)
                nearby=" ".join(x["text"] for x in result["segments"] if float(x["start"])<start+dur and float(x["end"])>start)
                title,desc,tags=make_metadata(nearby,i)
                items.append({"path":str(out),"title":title,"description":desc,"tags":tags,"yt":"","fb":""})
            status.update(label="✅ Shorts generated!",state="complete")
        st.session_state["items"]=items
    except Exception as e: st.error(str(e))

items=st.session_state.get("items",[])
if items:
    st.subheader("🎞️ Generated Shorts")
    for i,item in enumerate(items):
        st.markdown(f"### Short {i+1}")
        col1,col2=st.columns([1.2,1])
        with col1: st.video(item["path"])
        with col2:
            item["title"]=st.text_input("Title",item["title"],key=f"title{i}")
            item["description"]=st.text_area("Description",item["description"],key=f"desc{i}",height=180)
            item["tags"]=st.text_input("Tags",", ".join(item["tags"]),key=f"tags{i}").split(",")
            st.download_button("⬇️ Download",Path(item["path"]).read_bytes(),Path(item["path"]).name,"video/mp4",key=f"dl{i}")
        st.session_state["items"]=items

    if st.button("📤 ONE-CLICK PUBLISH ALL",type="primary"):
        for i,item in enumerate(items,1):
            try:
                if publish_yt:
                    item["yt"]=youtube_upload(item["path"],item["title"],item["description"],[x.strip() for x in item["tags"] if x.strip()],privacy)
                    st.success(f"Short {i} → YouTube: {item['yt']}")
                if publish_fb:
                    item["fb"]=fb_upload(item["path"],item["title"],item["description"])
                    st.success(f"Short {i} → Facebook: {item['fb']}")
            except Exception as e:
                st.error(f"Short {i}: {e}")
        st.session_state["items"]=items

st.divider()
st.caption("Only process and republish videos you own or have permission to use. This app uses official OAuth/API authorization; it never needs your social-media password.")
