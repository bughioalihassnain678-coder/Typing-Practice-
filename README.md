# Typing Race

Real-time multiplayer typing practice for up to 3 friends. Python 3 + Flask + Flask-SocketIO on the server, vanilla HTML/CSS/JS on the client.

## 1. Install
```bash
cd typing-race
python -m venv venv                # optional
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Start the server
```bash
python app.py
```
Open http://127.0.0.1:5000

## 3. Create a room
Enter a username, choose Multiplayer Race, pick difficulty and time, then click **Create Room**. You become the host and get a 5-character code (for example `A7K92`). Use **Copy code** to share it.

## 4. Friends join
Each friend opens the site, enters a username and the code, and clicks **Join Room**. Non-host players press **Ready**. The host presses **Start Race** once everyone is ready (the host counts as ready automatically).

## 5. Test all 3 players on one computer
Open three browser windows (use a normal window plus two private/incognito windows, or three different browsers). Create the room in window 1, join with the code in windows 2 and 3. A fourth join attempt shows "Room is Full".

## 6. Play from other computers on the same Wi-Fi
The server already listens on all interfaces (`host="0.0.0.0"`). Find the host PC's local IP:
- Windows: `ipconfig` (IPv4 Address)
- macOS: `ipconfig getifaddr en0`
- Linux: `hostname -I`

Friends open `http://<host-ip>:5000` (for example `http://192.168.1.25:5000`). If it does not load, allow Python/port 5000 through the host's firewall.

## How it works
- All room and player state lives on the server. Events go only to the room's Socket.IO channel.
- Clients send what they have typed; the **server** compares it with the paragraph and computes WPM (typed chars / 5 / minutes), accuracy (correct / typed), errors, progress and finish time. Clients cannot submit their own results.
- Everyone in a room gets the same random paragraph (20 paragraphs, 5 per difficulty).
- Disconnects are announced ("Ali disconnected"). Refreshing or reconnecting within 30 seconds restores your seat (session kept in `sessionStorage`); after that you are removed.
- Events: `create_room`, `join_room`, `rejoin`, `leave_room`, `player_ready`, `set_options`, `start_race`, `typing_update`, `player_finished`, `race_finished`, `race_again`, `back_to_lobby`, `disconnect`.
- Themes (15) and your username are saved in `localStorage`.
- Solo Practice is a one-player room, so it uses the same server-side scoring.

## If buttons show "io is not defined"
The browser could not download the Socket.IO client. Download https://cdn.socket.io/4.7.5/socket.io.min.js, save it as `static/socket.io.min.js`, restart `python app.py`. The page tries that local file first.

## Player limit
The host picks the maximum number of players (2 to 20) when creating the room and can change it in the lobby (never below the current player count).

## Putting it online (GitHub)
GitHub Pages only hosts static files. It cannot run Python/Flask, so rooms and live multiplayer will not work from Pages alone. You need the Python server running somewhere, then everyone opens the same site.

**Option A (simplest): host everything on Render, Railway or similar.**
1. Push this whole folder to a GitHub repo (it already has `Procfile` and `gunicorn` in requirements).
2. On render.com create a Web Service from the repo. Build command: `pip install -r requirements.txt`. Start command: `gunicorn -w 1 --threads 100 app:app`.
3. Share the URL Render gives you. Everyone opens that same URL and uses the room code.

**Option B: page on GitHub Pages, server on Render.**
1. Deploy the server as in option A.
2. Open `github-pages/index.html`, set `const BACKEND_URL = "https://your-app.onrender.com";` and put that file as `index.html` in your Pages repo.

Notes: keep `-w 1` (rooms live in server memory, so only one worker). Free hosts may sleep after inactivity (first load can take about a minute) and rooms are lost when the server restarts. "Invalid room code" almost always means the friends are connected to a different server than the host (for example each opened a page pointing at their own computer), or the room was already gone.
