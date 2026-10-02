import os, random, time, uuid
from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room as sio_join, leave_room as sio_leave
from flask import request

app = Flask(__name__)
app.config["SECRET_KEY"] = "typing-race-dev"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DEFAULT_MAX, ABS_MAX, COUNTDOWN, GRACE = 4, 20, 3, 30
DURATIONS = {0, 15, 30, 60, 120}
TEXTS = {
 "easy": [
  "The sun rises over the hills and the town slowly wakes up. Birds sing, shops open, and children walk to school with their friends.",
  "I like to drink warm tea in the morning while I read a good book. It makes the day feel calm and bright.",
  "We went to the park after lunch and played games until the sky turned orange. It was a very good day.",
  "A small red boat floated on the quiet lake. The water was clear, and we could see fish swimming below us.",
  "My friends and I meet every weekend to cook food, share stories, and laugh about the funny things we did."],
 "medium": [
  "Learning to type quickly is a skill that rewards patience. Keep your eyes on the screen, relax your shoulders, and let your fingers find their rhythm without rushing.",
  "The library was nearly empty that evening, and the only sound was the soft hum of the lights above. She opened her notebook and began to write down everything she remembered.",
  "Every great project starts with a simple idea, but it takes steady effort, honest feedback, and a lot of small improvements to turn that idea into something real.",
  "Travelers often say that the journey matters more than the destination, because the unexpected conversations along the way are the memories that last the longest.",
  "A reliable routine can change your life: wake up early, practice a little every day, and track your progress so you can see how far you have come."],
 "hard": [
  "Although the weather forecast predicted heavy rain, the committee decided, after a lengthy discussion, to continue with the outdoor ceremony; consequently, everyone arrived with umbrellas, raincoats, and a surprising amount of enthusiasm.",
  "\"Precision matters,\" the engineer said quietly. \"A single misplaced character can break an entire system, so read carefully, test thoroughly, and never assume anything works.\"",
  "Innovation rarely happens in isolation; it grows from curiosity, collaboration, and the willingness to question established assumptions, even when those assumptions seem perfectly reasonable.",
  "The architecture of the ancient city was remarkably sophisticated: wide avenues, underground aqueducts, and towering temples that still astonish archaeologists centuries later.",
  "Whenever the network became unstable, the administrator checked the logs, restarted the services, and documented every step, because good documentation prevents repeated mistakes."],
 "expert": [
  "In 2024, the team shipped v3.2.1 (build #4096) with 17 critical fixes; latency dropped from 245ms to 98ms, while throughput rose by 38.5% across all 12 regions.",
  "if (user.age >= 18 && user.country !== \"XX\") { return `Welcome, ${user.name}!`; } else { throw new Error(\"Access denied: code 403\"); }",
  "Quantum entanglement, as Schrodinger noted, isn't \"one\" trait but \"the\" characteristic trait of quantum mechanics; measurements on separated particles remain correlated at 99.7% accuracy.",
  "SELECT name, COUNT(*) AS total FROM orders WHERE status = 'shipped' AND created_at > '2025-01-01' GROUP BY name HAVING COUNT(*) > 5 ORDER BY total DESC;",
  "Dr. O'Neill's 2019 study (n=1,284) found a 7.3% improvement; however, p-values of <0.05 weren't replicated in 4 of 9 follow-ups, so results should be treated cautiously & skeptically."],
}
rooms, sessions = {}, {}


def err(msg): emit("error_msg", {"message": msg})
def clean_name(n): return " ".join(str(n or "").split())[:16]
def new_code():
    while True:
        c = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=5))
        if c not in rooms: return c
def blank(p):
    p.update(typed="", correct=0, errors=0, total=0, wpm=0, acc=100, progress=0, finished=False, time=None)
def new_player(name, sid, ready=False):
    p = {"id": uuid.uuid4().hex, "sid": sid, "name": name, "ready": ready, "connected": True}
    blank(p); return p
def pub(r):
    keys = ("id", "name", "ready", "connected", "wpm", "acc", "progress", "finished", "time", "correct", "errors", "total")
    return {"code": r["code"], "state": r["state"], "host": r["host"], "solo": r["solo"], "difficulty": r["difficulty"],
            "duration": r["duration"], "max": r["max"],
            "players": [{k: p[k] for k in keys} for p in r["players"].values()]}
def push(code):
    if code in rooms: socketio.emit("room_state", pub(rooms[code]), to=code)
def me():
    s = sessions.get(request.sid)
    if not s or s[0] not in rooms or s[1] not in rooms[s[0]]["players"]: return None, None
    r = rooms[s[0]]; return r, r["players"][s[1]]


def options(r, d):
    diff = d.get("difficulty");  dur = d.get("duration")
    if diff in TEXTS: r["difficulty"] = diff
    if isinstance(dur, int) and dur in DURATIONS: r["duration"] = dur
    mx = d.get("max")
    if isinstance(mx, int) and not isinstance(mx, bool): r["max"] = min(max(mx, 2, len(r["players"])), ABS_MAX)


def pick_text(r):
    """New paragraph (never the same as last time). Timed races get enough text to type until the clock ends."""
    pool = random.sample(TEXTS[r["difficulty"]], len(TEXTS[r["difficulty"]]))
    if pool[0] == r.get("last") and len(pool) > 1: pool.append(pool.pop(0))
    r["last"] = pool[0]
    if not r["duration"]: return pool[0]
    text, i = pool[0], 1
    while len(text) < r["duration"] * 12 and i < len(pool) * 3:
        text += " " + pool[i % len(pool)]; i += 1
    return text


def begin(r, same=False):
    for p in r["players"].values(): blank(p)
    text = r["text"] if same and r.get("text") else pick_text(r)
    r.update(state="racing", text=text, start=time.time() + COUNTDOWN, rid=uuid.uuid4().hex)
    socketio.emit("race_start", {"text": r["text"], "duration": r["duration"], "delta": COUNTDOWN}, to=r["code"])
    push(r["code"])
    socketio.start_background_task(timer, r["code"], r["rid"], r["duration"])


def timer(code, rid, dur):
    if dur: socketio.sleep(COUNTDOWN + dur); r = rooms.get(code)
    else: return
    if r and r["rid"] == rid and r["state"] == "racing": end_race(r)


def end_race(r):
    if r["state"] != "racing": return
    r["state"] = "done"; now = time.time()
    for p in r["players"].values():
        if not p["finished"]: p["time"] = round(min(max(now - r["start"], 0), r["duration"] or 1e9), 1)
    res = []
    for p in r["players"].values():
        res.append({"name": p["name"], "wpm": p["wpm"], "acc": p["acc"], "time": p["time"], "correct": p["correct"],
                    "errors": p["errors"], "total": p["total"], "completion": round(min(p["total"] / len(r["text"]), 1) * 100),
                    "finished": p["finished"]})
    res.sort(key=lambda x: (not x["finished"], -x["wpm"] if not x["finished"] else x["time"]))
    socketio.emit("race_finished", {"results": res, "length": len(r["text"])}, to=r["code"]); push(r["code"])


def check_all_done(r):
    live = [p for p in r["players"].values() if p["connected"]]
    if r["state"] == "racing" and (not live or all(p["finished"] for p in live)): end_race(r)


def remove(r, pid):
    p = r["players"].pop(pid, None)
    if not p: return
    sessions.pop(p["sid"], None)
    if not r["players"]: rooms.pop(r["code"], None); return
    if r["host"] == pid: r["host"] = next(iter(r["players"]))
    if r["solo"]: rooms.pop(r["code"], None); return
    push(r["code"]); check_all_done(r)


def grace_drop(code, pid):
    socketio.sleep(GRACE); r = rooms.get(code)
    if r and pid in r["players"] and not r["players"][pid]["connected"]:
        name = r["players"][pid]["name"]; remove(r, pid)
        socketio.emit("notice", {"message": f"{name} left the room"}, to=code)


def joined(r, p, ev="room_joined"):
    sio_join(r["code"]); sessions[request.sid] = (r["code"], p["id"])
    emit(ev, {"code": r["code"], "pid": p["id"]}); push(r["code"])


@app.route("/")
def index(): return render_template("index.html")


@socketio.on("create_room")
def on_create(d):
    name = clean_name((d or {}).get("name"))
    if not name: return err("Enter a username first")
    solo = bool(d.get("solo")); code = new_code(); p = new_player(name, request.sid, True)
    r = rooms[code] = {"code": code, "players": {p["id"]: p}, "host": p["id"], "state": "lobby", "solo": solo,
                       "difficulty": "medium", "duration": 0, "max": DEFAULT_MAX, "text": "", "start": 0, "rid": ""}
    options(r, d); joined(r, p)
    if solo: begin(r)


@socketio.on("join_room")
def on_join(d):
    d = d or {}; name = clean_name(d.get("name")); code = "".join(ch for ch in str(d.get("code", "")) if ch.isalnum()).upper()
    if not name: return err("Enter a username first")
    r = rooms.get(code)
    if not r: return err("Invalid room code. Check the code, or ask the host to create a new room (rooms reset when the server restarts).")
    if r["solo"]: return err("That code belongs to a solo practice room")
    if len(r["players"]) >= r["max"]: return err("Room is Full")
    if r["state"] != "lobby": return err("A race is already in progress")
    if any(x["name"].lower() == name.lower() for x in r["players"].values()): return err("That username is taken in this room")
    p = new_player(name, request.sid); r["players"][p["id"]] = p; joined(r, p)
    emit("notice", {"message": f"{name} joined"}, to=code)


@socketio.on("rejoin")
def on_rejoin(d):
    d = d or {}; r = rooms.get(str(d.get("code", ""))); p = r and r["players"].get(str(d.get("pid", "")))
    if not p: return emit("room_gone")
    sessions.pop(p["sid"], None); p.update(sid=request.sid, connected=True); joined(r, p, "room_rejoined")
    emit("notice", {"message": f"{p['name']} reconnected"}, to=r["code"])
    if r["state"] == "racing":
        emit("race_start", {"text": r["text"], "duration": r["duration"], "delta": r["start"] - time.time(), "typed": p["typed"]})
    elif r["state"] == "done": emit("to_results_hint")


@socketio.on("leave_room")
def on_leave():
    r, p = me()
    if not r: return
    code, name = r["code"], p["name"]; sio_leave(code); remove(r, p["id"]); emit("left")
    socketio.emit("notice", {"message": f"{name} left the room"}, to=code)


@socketio.on("player_ready")
def on_ready():
    r, p = me()
    if r and r["state"] == "lobby": p["ready"] = not p["ready"]; push(r["code"])


@socketio.on("set_options")
def on_opts(d):
    r, p = me()
    if r and r["state"] == "lobby" and r["host"] == p["id"] and isinstance(d, dict): options(r, d); push(r["code"])


@socketio.on("start_race")
def on_start():
    r, p = me()
    if not r or r["host"] != p["id"] or r["state"] != "lobby": return
    if any(x["connected"] and not x["ready"] and x["id"] != p["id"] for x in r["players"].values()):
        return err("Everyone must be ready first")
    begin(r)


@socketio.on("race_again")
def on_again(d=None):
    r, p = me(); d = d if isinstance(d, dict) else {}
    if not r or r["host"] != p["id"]: return
    if r["state"] == "done" or (r["state"] == "racing" and r["solo"]):
        options(r, d); begin(r, same=bool(d.get("same")))


@socketio.on("back_to_lobby")
def on_back():
    r, p = me()
    if not r or r["state"] != "done": return
    r["state"] = "lobby"
    for x in r["players"].values(): blank(x); x["ready"] = x["id"] == r["host"]
    socketio.emit("to_lobby", to=r["code"]); push(r["code"])


@socketio.on("typing_update")
def on_typing(d):
    r, p = me(); now = time.time()
    if not r or r["state"] != "racing" or p["finished"] or now < r["start"] - 0.3: return
    typed = (d or {}).get("typed")
    if not isinstance(typed, str): return
    el = max(now - r["start"], 0.001)
    if r["duration"] and el > r["duration"] + 1: return
    text = r["text"]; typed = typed[:len(text)]
    correct = sum(a == b for a, b in zip(typed, text)); total = len(typed)
    p.update(typed=typed, correct=correct, total=total, errors=total - correct,
             wpm=round(total / 5 / (el / 60)) if total else 0, acc=round(correct / total * 100) if total else 100,
             progress=round(total / len(text) * 100))
    if total >= len(text):
        p.update(finished=True, time=round(el, 1))
        socketio.emit("player_finished", {"name": p["name"], "wpm": p["wpm"], "acc": p["acc"], "time": p["time"]}, to=r["code"])
        push(r["code"]); check_all_done(r)
    else: push(r["code"])


@socketio.on("disconnect")
def on_disc():
    s = sessions.get(request.sid)
    if not s or s[0] not in rooms or s[1] not in rooms[s[0]]["players"]: return
    r = rooms[s[0]]; p = r["players"][s[1]]
    if p["sid"] != request.sid: return
    p["connected"] = False
    socketio.emit("notice", {"message": f"{p['name']} disconnected", "kind": "warn"}, to=r["code"])
    push(r["code"]); check_all_done(r); socketio.start_background_task(grace_drop, r["code"], p["id"])


def ensure_client():
    """Best effort: save the official Socket.IO browser client locally (the page also has a built-in fallback)."""
    import os, urllib.request
    path = os.path.join(app.static_folder, "socket.io.min.js")
    if os.path.exists(path): return
    for u in ("https://cdn.socket.io/4.7.5/socket.io.min.js", "https://cdn.jsdelivr.net/npm/socket.io-client@4.7.5/dist/socket.io.min.js"):
        try:
            data = urllib.request.urlopen(u, timeout=6).read()
            if len(data) > 10000: open(path, "wb").write(data); print("Downloaded Socket.IO client"); return
        except Exception: pass
    print("Could not download Socket.IO client; using built-in client instead.")


if __name__ == "__main__":
    if not os.environ.get("PORT"): ensure_client()
    print("Open http://127.0.0.1:5000  (friends: http://<your-ip>:5000)")
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), allow_unsafe_werkzeug=True)
