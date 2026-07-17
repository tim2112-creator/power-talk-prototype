#!/usr/bin/env python3
"""
Power Talk Prototyp — Interface

Web-Oberflaeche zum Editieren von System-Prompt-Varianten und Nutzerprofil,
mit Live-Generierung ueber die Anthropic API. Laeuft lokal oder deployed
(z.B. Railway).

Benoetigte Umgebungsvariablen:
  ANTHROPIC_API_KEY  (Pflicht)  Anthropic API Key.
  APP_PASSWORD       (optional) Wenn gesetzt, wird die Seite per HTTP Basic
                      Auth geschuetzt (beliebiger Nutzername, dieses Passwort).
                      Beim Deploy auf einen oeffentlichen Server unbedingt setzen.
  PORT               (optional) Server-Port, default 8765. Wird von Railway
                      automatisch gesetzt.

Start lokal: python3 power_talk_app.py
Dann im Browser oeffnen: http://localhost:8765
"""

import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic

MODEL = "claude-sonnet-4-5"
PORT = int(os.environ.get("PORT", 8765))
APP_PASSWORD = os.environ.get("APP_PASSWORD")

DEFAULT_PROFILE = {
    "situation": (
        "Es ist Donnerstagabend. Die Person hat die Woche viel geschafft, "
        "ist platt, aber gleichzeitig innerlich unruhig. Der Grund: ein innerer "
        "Antreiber laesst nicht zu, dass sie sich hinsetzt und wirklich ruht, "
        "obwohl nicht mehr viel zu tun ist. Es fuehlt sich an wie Bammel davor, "
        "loszulassen und in die Ruhe zu gehen."
    ),
    "zielzustand": "Entspannung und Ruhe",
    "ausgangs_intensitaet": 8,
}

BASE_RULES = """Du bist die KI hinter "Energetic Shift" in The Temple, einem spirituellen
Rueckzugsort von Laura Seiler. Du erstellst einen Power Talk als gesprochene
Nachricht in Ich-Perspektive der Person.

Dramaturgie (immer in dieser Reihenfolge):
1. Situation aufgreifen, in Ich-Perspektive, konkret auf das Gesagte bezogen.
2. Reframe: die Situation bleibt, aber die Bedeutung verschiebt sich. Keine
   Relativierung, keine Beschwichtigung, eine echte andere Wahrheit.
3. Affirmationen in Richtung Zielzustand: kurze, klare Saetze in
   Ich-Perspektive, vorwaertsgerichtet, konkret auf den gewuenschten Zustand.

Regeln:
- Immer Ich-Perspektive.
- Situation konkret aufgreifen, nie generisch, nie austauschbar.
- Kein "alles wird gut", sondern eine Wahrheit, die wirklich traegt.
- Ton: warm, direkt, bold, wie Laura spricht.
- Gesamtlaenge: 45-75 Sekunden gesprochen (ca. 90-170 Woerter).
- Verboten: lange Gedankenstriche als Satzverbinder, "Ich verstehe, dass",
  "Als KI moechte ich", "Basierend auf dem, was du gesagt hast",
  "Es scheint, als ob", "Ich nehme wahr, dass", Aufzaehlungen mit
  Spiegelstrichen, Therapie- oder Coach-Vokabular (auch keine Woerter wie
  "Nervensystem", "System", "Modus", "Trigger").
- Gib NUR den gesprochenen Text zurueck, keine Meta-Kommentare, keine
  Ueberschriften.
"""

DEFAULT_VARIANTS = {
    "A_geschaerft": BASE_RULES + """
Zusaetzlich: Schreibe kurze Saetze. Vermeide glatte Uebergaenge zwischen den
drei Teilen. Erlaube dir gelegentlich einen Satz ohne Verb oder einen
abgebrochenen Gedanken, wenn es die Sprache echter macht.
""",
    "B_embodiment": BASE_RULES + """
Zusaetzlich: Greif die koerperlichen/emotionalen Formulierungen der Person
so woertlich wie moeglich auf (ihre eigenen Worte fuer den Zustand), statt
sie zu paraphrasieren oder durch Synonyme zu ersetzen. Der Reframe soll sich
direkt auf genau dieses Koerpergefuehl beziehen.
""",
    "C_rhythmus": BASE_RULES + """
Zusaetzlich: Schreibe in kurzen Zeilen statt vollstaendigen Fliesstext-
Absaetzen. Nutze bewusste Brueche und Auslassungspunkte ("...") als
Sprechpausen-Marker an Stellen, an denen eine echte Pause die Wirkung
verstaerkt. Vermeide vollstaendige, runde Saetze durchgehend.
""",
}

PAGE_HTML = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Power Talk Prototyp</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --beige: #F5EEE8;
    --white: #ffffff;
    --stone-300: #d6d3d1;
    --stone-400: #a6a09b;
    --stone-500: #79716b;
    --stone-800: #292524;
    --slate-700: #314158;
    --slate-800: #1d293d;
    --amber-600: #e17100;
    --radius-sm: 4px;
    --radius-lg: 8px;
    --radius-2xl: 16px;
    --radius-full: 9999px;
    --shadow-sm: 0 1px 2px rgba(29,41,61,0.08), 0 1px 1px rgba(29,41,61,0.04);
    --shadow-elevated: 0 4px 16px rgba(29,41,61,0.10), inset 0 1px 0 rgba(255,255,255,0.6);
  }
  * { box-sizing: border-box; }
  body {
    font-family: 'Inter', -apple-system, sans-serif;
    background: var(--beige);
    color: var(--stone-800);
    max-width: 1160px;
    margin: 0 auto;
    padding: 2.5rem 1.5rem 4rem;
  }
  h1 {
    font-family: Georgia, 'Times New Roman', serif;
    letter-spacing: 0.8px;
    font-size: 2.25rem;
    font-weight: 400;
    color: var(--slate-800);
    margin-bottom: 0.25rem;
  }
  p.intro { color: var(--stone-500); font-size: 0.95rem; margin-top: 0; margin-bottom: 2rem; }
  h2 {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--stone-500);
    margin: 2.5rem 0 0.75rem;
  }
  .panel {
    background: rgba(255,255,255,0.6);
    border-radius: var(--radius-2xl);
    box-shadow: var(--shadow-elevated);
    padding: 1.5rem;
  }
  .profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  .profile-grid .full { grid-column: 1 / -1; }
  label { display: block; font-weight: 600; font-size: 0.75rem; color: var(--stone-800); margin-bottom: 0.35rem; }
  textarea, input[type=text], input[type=number] {
    width: 100%;
    font-family: inherit;
    font-size: 0.9rem;
    color: var(--stone-800);
    padding: 0.6rem 0.75rem;
    border: 1px solid var(--stone-300);
    border-radius: var(--radius-lg);
    background: rgba(255,255,255,0.7);
    box-shadow: inset 0 1px 2px rgba(41,37,36,0.05);
  }
  textarea:focus, input:focus { outline: none; border-color: var(--slate-500, #62748e); }
  textarea { resize: vertical; }
  .variants { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-top: 1rem; }
  .variant-card {
    background: var(--white);
    border-radius: var(--radius-2xl);
    box-shadow: var(--shadow-elevated);
    padding: 1rem;
  }
  .variant-card textarea { height: 220px; font-size: 0.8rem; }
  .variant-card input.name { font-weight: 700; margin-bottom: 0.5rem; border: none; background: transparent; padding: 0.2rem 0; box-shadow: none; }
  button {
    margin-top: 1.75rem;
    padding: 0.7rem 1.75rem;
    font-size: 0.9rem;
    font-weight: 600;
    border-radius: var(--radius-full);
    border: none;
    background: var(--slate-700);
    color: white;
    box-shadow: var(--shadow-sm);
    cursor: pointer;
  }
  button:disabled { background: var(--stone-400); cursor: wait; }
  .results { margin-top: 1rem; display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
  .result-card {
    background: var(--white);
    border-radius: var(--radius-2xl);
    box-shadow: var(--shadow-elevated);
    padding: 1rem;
    white-space: pre-wrap;
    font-size: 0.9rem;
    line-height: 1.5;
  }
  .result-card h3 { margin-top: 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--stone-500); }
  .status { margin-top: 1rem; font-size: 0.85rem; color: var(--stone-500); }
  .error { color: var(--amber-600); }
</style>
</head>
<body>
<h1>Power Talk Prototyp</h1>
<p class="intro">Energetic Shift &middot; Profil und Prompt-Varianten anpassen, dann generieren. Laeuft live gegen die Anthropic API.</p>

<h2>Nutzerprofil</h2>
<div class="profile-grid panel">
  <div class="full">
    <label>Situation</label>
    <textarea id="situation" rows="3"></textarea>
  </div>
  <div>
    <label>Zielzustand</label>
    <input id="zielzustand" type="text">
  </div>
  <div>
    <label>Ausgangs-Intensitaet (1-10)</label>
    <input id="intensitaet" type="number" min="1" max="10">
  </div>
</div>

<h2>Prompt-Varianten</h2>
<div class="variants" id="variants"></div>

<button id="generateBtn" onclick="generate()">Generieren</button>
<div class="status" id="status"></div>

<h2>Outputs</h2>
<div class="results" id="results"></div>

<script>
const defaultProfile = __PROFILE_JSON__;
const defaultVariants = __VARIANTS_JSON__;

const variantsDiv = document.getElementById('variants');
const variantNames = Object.keys(defaultVariants);

function renderVariants() {
  variantsDiv.innerHTML = '';
  variantNames.forEach((name, i) => {
    const card = document.createElement('div');
    card.className = 'variant-card';
    card.innerHTML = `
      <input class="name" data-idx="${i}" type="text" value="${name}">
      <textarea data-idx="${i}">${defaultVariants[name]}</textarea>
    `;
    variantsDiv.appendChild(card);
  });
}

document.getElementById('situation').value = defaultProfile.situation;
document.getElementById('zielzustand').value = defaultProfile.zielzustand;
document.getElementById('intensitaet').value = defaultProfile.ausgangs_intensitaet;
renderVariants();

async function generate() {
  const btn = document.getElementById('generateBtn');
  const status = document.getElementById('status');
  const resultsDiv = document.getElementById('results');
  btn.disabled = true;
  status.textContent = 'Generiere... (kann ein paar Sekunden dauern)';
  status.className = 'status';
  resultsDiv.innerHTML = '';

  const profile = {
    situation: document.getElementById('situation').value,
    zielzustand: document.getElementById('zielzustand').value,
    ausgangs_intensitaet: document.getElementById('intensitaet').value,
  };

  const variantInputs = variantsDiv.querySelectorAll('.variant-card');
  const variants = {};
  variantInputs.forEach(card => {
    const name = card.querySelector('.name').value;
    const prompt = card.querySelector('textarea').value;
    variants[name] = prompt;
  });

  try {
    const resp = await fetch('/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({profile, variants}),
    });
    const data = await resp.json();
    if (data.error) {
      status.textContent = 'Fehler: ' + data.error;
      status.className = 'status error';
    } else {
      status.textContent = 'Fertig.';
      Object.entries(data.results).forEach(([name, text]) => {
        const card = document.createElement('div');
        card.className = 'result-card';
        card.innerHTML = `<h3>${name}</h3>${text}`;
        resultsDiv.appendChild(card);
      });
    }
  } catch (e) {
    status.textContent = 'Fehler: ' + e;
    status.className = 'status error';
  }
  btn.disabled = false;
}
</script>
</body>
</html>
"""


def build_user_message(profile: dict) -> str:
    return (
        f"Situation der Person: {profile['situation']}\n"
        f"Gewuenschter Zielzustand: {profile['zielzustand']}\n"
        f"Ausgangs-Intensitaet (1-10): {profile['ausgangs_intensitaet']}\n\n"
        "Erstelle jetzt den Power Talk fuer diese Person."
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # weniger Terminal-Rauschen

    def _authorized(self):
        if not APP_PASSWORD:
            return True
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth[len("Basic "):]).decode("utf-8")
            _, _, password = decoded.partition(":")
        except Exception:
            return False
        return password == APP_PASSWORD

    def _require_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Power Talk Prototyp"')
        self.end_headers()

    def do_GET(self):
        if not self._authorized():
            self._require_auth()
            return
        if self.path != "/":
            self.send_response(404)
            self.end_headers()
            return
        html = PAGE_HTML.replace(
            "__PROFILE_JSON__", json.dumps(DEFAULT_PROFILE)
        ).replace(
            "__VARIANTS_JSON__", json.dumps(DEFAULT_VARIANTS)
        )
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._authorized():
            self._require_auth()
            return
        if self.path != "/generate":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
            profile = payload["profile"]
            variants = payload["variants"]

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt.")

            client = anthropic.Anthropic(api_key=api_key)
            user_message = build_user_message(profile)

            results = {}
            for name, system_prompt in variants.items():
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                text = "".join(
                    b.text for b in response.content if b.type == "text"
                )
                results[name] = text.strip()

            response_body = json.dumps({"results": results}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        except Exception as e:
            error_body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error_body)))
            self.end_headers()
            self.wfile.write(error_body)


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "Warnung: ANTHROPIC_API_KEY ist nicht gesetzt. "
            "Die Seite laedt, aber Generieren wird fehlschlagen.",
            file=sys.stderr,
        )
    if not APP_PASSWORD:
        print(
            "Warnung: APP_PASSWORD ist nicht gesetzt. Auf einem oeffentlichen "
            "Server bedeutet das: kein Passwortschutz.",
            file=sys.stderr,
        )
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Power Talk Prototyp laeuft auf Port {PORT}")
    print("Zum Beenden: Strg+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
