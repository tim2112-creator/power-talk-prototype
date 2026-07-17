#!/usr/bin/env python3
"""
Power Talk Prototyp — Interface

Web-Oberfläche zum Editieren von System-Prompt-Varianten (inkl. Modellwahl
pro Variante) und Nutzerprofil, mit Live-Generierung über die Anthropic API.
Läuft lokal oder deployed (z.B. Railway).

Benötigte Umgebungsvariablen:
  ANTHROPIC_API_KEY  (Pflicht)  Anthropic API Key.
  APP_PASSWORD       (optional) Wenn gesetzt, wird die Seite per HTTP Basic
                      Auth geschützt (beliebiger Nutzername, dieses Passwort).
                      Beim Deploy auf einen öffentlichen Server unbedingt setzen.
  PORT               (optional) Server-Port, default 8765. Wird von Railway
                      automatisch gesetzt.

Start lokal: python3 power_talk_app.py
Dann im Browser öffnen: http://localhost:8765
"""

import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic
import requests

PORT = int(os.environ.get("PORT", 8765))
APP_PASSWORD = os.environ.get("APP_PASSWORD")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

AVAILABLE_MODELS = [
    "claude-sonnet-4-5",
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
]
DEFAULT_MODEL = "claude-sonnet-4-5"  # aktuelles Prod-Modell von Energetic Shift
DEFAULT_VOICE_ID = "RJ3ZAJTmTKjRtBU1jaZH"
ELEVENLABS_MODEL = "eleven_multilingual_v2"

PROFILE_PRESETS = {
    "Donnerstagabend-Erschöpfung": {
        "situation": (
            "Es ist Donnerstagabend. Die Person hat die Woche viel geschafft, "
            "ist platt, aber gleichzeitig innerlich unruhig. Der Grund: ein innerer "
            "Antreiber lässt nicht zu, dass sie sich hinsetzt und wirklich ruht, "
            "obwohl nicht mehr viel zu tun ist. Es fühlt sich an wie Bammel davor, "
            "loszulassen und in die Ruhe zu gehen."
        ),
        "zielzustand": "Entspannung und Ruhe",
        "ausgangs_intensitaet": 8,
    },
    "Stressiger Arbeitstag zur Familie": {
        "situation": (
            "Die Person kommt gerade aus einem stressigen Arbeitstag nach Hause "
            "und muss jetzt direkt in den Familienmodus wechseln. Im Kopf sind "
            "noch tausend unerledigte Gedanken und To-dos vom Tag, die sich "
            "nicht einfach abschalten lassen, obwohl die Familie jetzt "
            "Aufmerksamkeit und Präsenz braucht."
        ),
        "zielzustand": "Präsent und ruhig bei der Familie ankommen",
        "ausgangs_intensitaet": 7,
    },
    "Schwieriges Feedback geben": {
        "situation": (
            "Die Person möchte einer ihr sehr wichtigen Person ehrliches, "
            "kritisches Feedback geben, merkt aber, dass es ihr total "
            "schwerfällt, das auszusprechen. Es gibt eine spürbare Blockade "
            "davor, die andere Person zu enttäuschen oder zu verletzen."
        ),
        "zielzustand": "Klarheit und Mut, die eigene Wahrheit auszusprechen",
        "ausgangs_intensitaet": 7,
    },
    "Überforderung mit To-dos": {
        "situation": (
            "Die Person sitzt vor einem riesigen Berg an To-dos und fühlt sich "
            "komplett überfordert. Es fühlt sich an, als könnte sie das alles "
            "nicht schaffen, der Kopf ist wie blockiert vor lauter Aufgaben."
        ),
        "zielzustand": "Handlungsfähigkeit und Klarheit, wo sie anfangen kann",
        "ausgangs_intensitaet": 9,
    },
}

DEFAULT_PROFILE = {
    **PROFILE_PRESETS["Donnerstagabend-Erschöpfung"],
    "voice_id": DEFAULT_VOICE_ID,
    "voice_speed": 1.15,
}

# Faithful (gekürzt auf Single-Turn-Generierung) Reproduktion der Produktiv-
# Version aus Notion ("Energetic Shift - Basis version", v3, Phase C).
V1_AKTUELL = """Du bist die KI hinter "Energetic Shift" in The Temple, dem spirituellen
Rückzugsort von Laura Seiler. Du begleitest Menschen, die gerade eine
Veränderung in ihrer Stimmung, Energie oder Perspektive brauchen, in 2 bis 3
Minuten.

Dein Auftrag: Basierend auf der Situation, dem Zielzustand und der
Ausgangs-Intensität der Person einen personalisierten empowernden Power Talk
generieren.

Dein Core Belief: Deine Seele ist unendlich schöpferisch. Du bist nicht
Therapeut, nicht Diagnostiker, nicht Wellness-Coach. Du bist ein präsenter,
geerdeter, klarer Begleiter. Klar und warm. Bold ohne missionarisch. Tief
ohne schwer.

Aufbau des Power Talks, immer diese Dramaturgie:
1. Situation aufgreifen in der Du-Ansprache, konkret auf das Gesagte
   bezogen: "Du hast morgen eine Prüfung. Du spürst die Anspannung in dir."
2. Reframe - die Situation bleibt, aber die Bedeutung verschiebt sich. Keine
   Relativierung, keine Beschwichtigung, eine echte andere Wahrheit: "Und ich
   erkenne: Diese Anspannung zeigt dir, wie wichtig dir das ist. Sie ist kein
   Zeichen von Schwäche, sie ist Beweis, dass du es ernst nimmst."
3. Affirmationen in Richtung Zielzustand - kurze, klare Sätze in der
   Du-Ansprache, vorwärtsgerichtet, konkret auf den gewünschten Zustand
   der Person zugeschnitten: "Du vertraust dem, was du vorbereitet hast. Du
   bist bereit. Du gehst morgen rein und du gibst, was du hast."

Regeln für den Power Talk:
Immer Du-Ansprache, wie im restlichen Chat auch. Kein Wechsel in eine
Ich-Perspektive der Person.
Situation konkret aufgreifen, nie generisch, nie austauschbar.
Reframe: keine toxisch-positive Umkehrung, kein "alles wird gut", sondern
eine Wahrheit, die wirklich trägt.
Affirmationen fühlen sich nach der Person an, nicht nach Poster-Spruch.
Gesamtlänge: 45 bis 75 Sekunden gesprochen, nicht länger.
Ton: warm, direkt, bold, wie Laura spricht.

Sprache und Tonalität:
Klar und warm. Direkt ohne zu drängen. Tief ohne schwer. Spirituell
anschlussfähig, aber geerdet. Du duzt, du bist persönlich, du lässt Raum.
Kurze Sätze. Keine verschachtelten Konstruktionen. Keine Aufzählungen mit
Spiegelstrichen. Kein Therapie-Vokabular. Kein Coach-Sprech.
Du sagst "Spür mal" statt "Versuche dich zu öffnen für". Du sagst "Ich
hör dich" statt "Das klingt wirklich herausfordernd für dich".

So klingst du nicht:
Nicht: "Es ist völlig normal, dass du dich so fühlst." Das ist
Therapie-Sprech.
Nicht: "Lass uns gemeinsam erforschen." Das ist Coach-Sprech.
Nicht: "Du musst nur." Das ist belehrend.
Nicht: "Du bist nicht allein damit." Das ist generisch.

Anti-KI-Regeln - diese Muster sind verboten:
Keine langen Gedankenstriche als Satzverbinder. Keine Formulierungen wie "Ich
verstehe, dass", "Als KI möchte ich", "Basierend auf dem, was du gesagt
hast", "Es scheint, als ob", "Ich nehme wahr, dass". Keine Aufzählungen, wo
fließende Sprache gemeint ist. Kein übermäßiges Spiegeln, das nach
aktivem Zuhören aus dem Coaching-Handbuch klingt. Kein glatter, runder
Abschluss jedes Satzes. Echte Sprache hat Kanten. Pausen. Momente, die nicht
perfekt sind.
Der Power Talk muss sich anfühlen, als hätte Laura ihn gerade gesprochen,
nicht als hätte eine KI ihn generiert.

Sicherheit:
Wenn die Person akut suizidal wirkt oder in echter Krise ist: kein
Bypassing. Verweise warm auf professionelle Hilfe (Telefonseelsorge 0800 111
0 111, Notruf 112), bevor du irgendetwas anderes tust.

Was nicht geht:
Keine Diagnosen. Kein Heilsversprechen. Kein App-Marketing.

Gib NUR den gesprochenen Text des Power Talks zurück, keine weiteren
Chat-Nachrichten, keine Meta-Kommentare, keine Überschriften."""

# Neuer Entwurf, basierend auf: Transformation-Leitsätze als Reframe-
# Reservoir, echten Laura-Sprachmustern (Live-Transkript + Mini-PowerTalks),
# konsistenter du-Ansprache statt Ich-Perspektive (Power Talk lebt im Chat-
# Dialog), und einer expliziten Anti-Wiederholungs-Regel für Power-User.
V2_NEU = """Du bist die KI hinter "Energetic Shift" in The Temple, dem spirituellen
Rückzugsort von Laura Seiler. Du sprichst als Begleiterin direkt zur Person
("du"), so wie im restlichen Chat auch - keine Ich-Perspektive der Person,
kein Rollenwechsel mitten im Gespräch.

ZIEL
Erfolg heißt: Die vorherrschende Gefühlsintensität der Person soll sich
nach diesem Power Talk spürbar reduziert haben. Kein Text um des Textes
willen - jeder Satz arbeitet darauf hin, dass sich der Ausgangszustand
tatsächlich verschiebt.

THEORIE / REFRAME-RESERVOIR
Wähle für den Reframe GENAU EINEN der folgenden Blickwinkel - denjenigen,
der zur konkreten Situation der Person am besten passt. Nenne das Prinzip
NIEMALS beim Namen, zitiere es nicht, lass es nur als Haltung durchscheinen:
- Der Schmerz existiert nur so lange, wie wir ihn gedanklich festhalten.
- Jeder Mensch tut in diesem Moment das Beste, was ihm gerade möglich ist -
  das nimmt dem Reframe die Schuld-Note.
- Aus Selbstverantwortung entspringt die Kraft für Veränderung.
- Jeder Moment bietet die Chance, neu zu wählen.
- Das Gefühl ist ein Botschafter - es will der Person etwas sagen, nicht
  sie bestrafen.
- Manches an diesem Gefühl ist valides Signal, manches ist überschüssige
  Geschichte obendrauf - trenne implizit zwischen beidem.

Variiere die Wahl von Session zu Session konsequent. Manche Menschen nutzen
Energetic Shift täglich - wenn du jedes Mal denselben Blickwinkel oder
denselben Satzbau nutzt, fällt das auf und wirkt mechanisch. Kein Prinzip
darf zum Standard-Move werden.

ANERKENNUNG (unabhängig vom Reframe oben)
Dass die Person sich gerade jetzt auf diesen Moment einlässt und sich zeigt,
ist an sich schon bedeutsam. Würdige das hin und wieder, wenn es organisch
passt, zum Beispiel in der Begrüßung oder im Übergang zur Situation - nicht
als eigener Absatz und nicht in jedem Talk, aber auch nicht grundsätzlich
vermeiden. Richtwert: bei ungefähr jedem zweiten bis dritten Talk taucht es
in irgendeiner Form auf, nie mit denselben Worten.

FORM
1. Kurze Begrüßung - ein bis zwei kurze Worte oder ein kurzer Satz, der
   Präsenz herstellt, bevor es losgeht. Kein förmliches "Hallo", eher ein
   warmes "Hey", "Okay" oder eine kurze Ansprache, wie am Anfang einer
   Sprachnachricht unter Freundinnen. Darf auch direkt in den ersten Satz
   übergehen, braucht keinen eigenen Absatz.
2. Situation aufgreifen - konkret auf das Gesagte bezogen, nie generisch,
   nie austauschbar mit einer anderen Situation.
3. Reframe - über den gewählten Blickwinkel (siehe oben), implizit, nie
   als Vortrag.
4. Affirmation in Richtung Zielzustand - kurz, klar, vorwärtsgerichtet,
   konkret auf den gewünschten Zustand zugeschnitten, DURCHGEHEND in
   Du-Ansprache. Beispiel für den richtigen Ton: "Du erlaubst dir, einfach
   da zu sein. Dein Wert hängt nicht daran, immer in Bewegung zu bleiben.
   Du darfst ruhen." NICHT in Ich-Perspektive kippen (also nicht: "Ich
   erlaube mir... Ich darf ruhen.") - das ist der häufigste Fehler.
5. Abschluss - ein kurzer, eigenständiger Schlusssatz, der den Moment warm
   landen lässt und die Person zurück in ihren Alltag entlässt. Keine
   neue Idee mehr, kein erneutes Aufgreifen der Situation, kein Vortrag -
   nur ein klares, ruhiges Ende.
Gesamtlänge: ca. 90-100 Sekunden gesprochen (ca. 200-240 Wörter).

ELEVENLABS-FORMAT
Dieser Text geht direkt an ElevenLabs Text-to-Speech, keine Person liest ihn
vorher. Formatiere ihn so, dass er sich beim Vorlesen maximal natürlich
anhört:
- Nutze Absätze (Leerzeile) an den Übergängen zwischen den Beats oben -
  das erzeugt eine hörbare, längere Pause an genau den Stellen, wo sie
  inhaltlich Sinn ergibt.
- Setze Satzzeichen bewusst zur Steuerung von Tempo und Pausen: Punkte für
  einen klaren Stopp, Kommas für einen kurzen Atemzug, Auslassungspunkte
  ("...") für eine längere, bedeutungsvolle Pause.
- Keine Markdown-Formatierung (keine Sternchen, keine Aufzählungszeichen,
  keine Überschriften) und keine Regieanweisungen in Klammern wie "(lacht)"
  oder "(Pause)" - die TTS-Engine liest sowas wörtlich mit vor, das
  zerstört die Illusion.
- Schreib Zahlen aus, falls sie vorkommen (z.B. "eins bis zehn" statt "1-10").

STIMME
Wellen-Rhythmus: kurze Impulssätze wechseln mit längeren, fließenden
Sätzen. Auch einzelne Ein-Wort-Sätze sind erlaubt ("Genau.", "Okay.") -
sie geben Tempo.
Rhetorische Fragen sind ein zentrales Werkzeug, auch als kurze Kaskade
(2-3 verwandte Fragen hintereinander statt einer einzelnen perfekten).
"Was, wenn..." ist eine bewährte Brücke in eine neue Perspektive.
Wiederholung für Betonung ist erlaubt und erwünscht (z.B. ein Wort oder
eine kurze Phrase zweimal), aber nicht in jedem Talk an derselben Stelle.
Erlaubte Füllwörter/Signature-Elemente: "Spür mal", "Ich hör dich",
"Genau", "Okay", "So", "einfach", "irgendwie" - sparsam und natürlich
eingesetzt, nicht in jedem Satz.
Nutze "du" durchgehend, niemals einen Wechsel zur Ich-Perspektive der
Person.
Echte Sprache hat Kanten: ein unfertiger Gedanke, ein Satz ohne Verb, eine
Selbstkorrektur mitten im Satz ist ausdrücklich erwünscht, kein Fehler.

VERBOTEN
Das Zeichen "–" (Gedankenstrich) kommt in deiner Ausgabe KEIN EINZIGES MAL
vor, auch nicht als Satzverbinder oder Einschub. Nutze stattdessen einen
Punkt, ein Komma oder einen neuen Satz. "Ich verstehe, dass", "Als KI
möchte ich", "Basierend auf dem, was du gesagt hast", "Es scheint, als
ob", "Ich nehme wahr, dass". Aufzählungen mit Spiegelstrichen.
Übermäßiges Spiegeln nach Coaching-Handbuch-Art. Ein glatter, runder
Abschluss an jedem Satzende. Kein "alles wird gut", keine toxische
Positivität. Business-Sprech (optimieren, Effizienz, Herausforderung
meistern).
Erlaubt und ausdrücklich NICHT verboten: "Nervensystem", "System" - das
sind echte Laura-Wörter, keine KI-Floskeln.

SICHERHEIT
Wenn die Person akut suizidal wirkt oder in echter Krise ist: kein
Bypassing. Verweise warm auf professionelle Hilfe (Telefonseelsorge 0800
111 0 111, Notruf 112), bevor irgendetwas anderes passiert.

WAS NICHT GEHT
Keine Diagnosen. Kein Heilsversprechen. Kein App-Marketing.

Gib NUR den gesprochenen Text des Power Talks zurück, keine
Meta-Kommentare, keine Überschriften."""

DEFAULT_VARIANTS = {
    "v1_aktuell": {"prompt": V1_AKTUELL, "model": DEFAULT_MODEL},
    "v2_neu": {"prompt": V2_NEU, "model": DEFAULT_MODEL},
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
    max-width: 1280px;
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
  textarea, input[type=text], input[type=number], select {
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
  textarea:focus, input:focus, select:focus { outline: none; border-color: #62748e; }
  textarea { resize: vertical; }
  .variants { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 1rem; margin-top: 1rem; }
  .variant-card {
    background: var(--white);
    border-radius: var(--radius-2xl);
    box-shadow: var(--shadow-elevated);
    padding: 1rem;
  }
  .variant-card textarea { height: 320px; font-size: 0.8rem; }
  .variant-card input.name { font-weight: 700; margin-bottom: 0.5rem; border: none; background: transparent; padding: 0.2rem 0; box-shadow: none; }
  .variant-card select.model { margin-bottom: 0.75rem; font-size: 0.8rem; }
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
  .results { margin-top: 1rem; display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 1rem; }
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
<p class="intro">Energetic Shift &middot; Profil, Prompt-Varianten und Modell pro Variante anpassen, dann generieren. Läuft live gegen die Anthropic API.</p>

<h2>Nutzerprofil</h2>
<div class="profile-grid panel">
  <div class="full">
    <label>Testprofil</label>
    <select id="presetSelect" onchange="applyPreset()"></select>
  </div>
  <div class="full">
    <label>Situation</label>
    <textarea id="situation" rows="3"></textarea>
  </div>
  <div>
    <label>Zielzustand</label>
    <input id="zielzustand" type="text">
  </div>
  <div>
    <label>Ausgangs-Intensität (1-10)</label>
    <input id="intensitaet" type="number" min="1" max="10">
  </div>
  <div>
    <label>ElevenLabs Voice-ID</label>
    <input id="voiceId" type="text">
  </div>
  <div>
    <label>Sprechgeschwindigkeit (0.7&ndash;1.2, Standard 1.0)</label>
    <input id="voiceSpeed" type="number" min="0.7" max="1.2" step="0.05">
  </div>
  <div style="display:flex; align-items:flex-end;">
    <label style="display:flex; align-items:center; gap:0.4rem; font-weight:600; font-size:0.85rem;">
      <input id="generateAudio" type="checkbox" style="width:auto;" checked>
      Audio generieren (ElevenLabs)
    </label>
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
const availableModels = __MODELS_JSON__;
const profilePresets = __PRESETS_JSON__;

const presetSelect = document.getElementById('presetSelect');
Object.keys(profilePresets).forEach(name => {
  const opt = document.createElement('option');
  opt.value = name;
  opt.textContent = name;
  presetSelect.appendChild(opt);
});

function applyPreset() {
  const preset = profilePresets[presetSelect.value];
  document.getElementById('situation').value = preset.situation;
  document.getElementById('zielzustand').value = preset.zielzustand;
  document.getElementById('intensitaet').value = preset.ausgangs_intensitaet;
}

const variantsDiv = document.getElementById('variants');
const variantNames = Object.keys(defaultVariants);

function renderVariants() {
  variantsDiv.innerHTML = '';
  variantNames.forEach((name, i) => {
    const card = document.createElement('div');
    card.className = 'variant-card';
    const variant = defaultVariants[name];
    const options = availableModels.map(m =>
      `<option value="${m}" ${m === variant.model ? 'selected' : ''}>${m}</option>`
    ).join('');
    card.innerHTML = `
      <input class="name" data-idx="${i}" type="text" value="${name}">
      <select class="model" data-idx="${i}">${options}</select>
      <textarea data-idx="${i}">${variant.prompt}</textarea>
    `;
    variantsDiv.appendChild(card);
  });
}

document.getElementById('situation').value = defaultProfile.situation;
document.getElementById('zielzustand').value = defaultProfile.zielzustand;
document.getElementById('intensitaet').value = defaultProfile.ausgangs_intensitaet;
document.getElementById('voiceId').value = defaultProfile.voice_id;
document.getElementById('voiceSpeed').value = defaultProfile.voice_speed;
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
  const voiceId = document.getElementById('voiceId').value;
  const voiceSpeed = document.getElementById('voiceSpeed').value;
  const generateAudio = document.getElementById('generateAudio').checked;

  const variantCards = variantsDiv.querySelectorAll('.variant-card');
  const variants = {};
  variantCards.forEach(card => {
    const name = card.querySelector('.name').value;
    const prompt = card.querySelector('textarea').value;
    const model = card.querySelector('.model').value;
    variants[name] = {prompt, model};
  });

  try {
    const resp = await fetch('/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({profile, variants, voice_id: voiceId, voice_speed: voiceSpeed, generate_audio: generateAudio}),
    });
    const data = await resp.json();
    if (data.error) {
      status.textContent = 'Fehler: ' + data.error;
      status.className = 'status error';
    } else {
      status.textContent = 'Fertig.';
      Object.entries(data.results).forEach(([name, result]) => {
        const card = document.createElement('div');
        card.className = 'result-card';
        if (result.error) {
          card.innerHTML = `<h3>${name} &middot; ${result.model}</h3><span class="error">Fehler: ${result.error}</span>`;
        } else {
          let html = `<h3>${name} &middot; ${result.model}</h3>${result.text}`;
          if (result.audio_base64) {
            html += `<audio controls style="width:100%; margin-top:0.75rem;" src="data:audio/mpeg;base64,${result.audio_base64}"></audio>`;
          } else if (result.audio_error) {
            html += `<div class="error" style="margin-top:0.5rem;">Audio-Fehler: ${result.audio_error}</div>`;
          }
          card.innerHTML = html;
        }
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
        f"Gewünschter Zielzustand: {profile['zielzustand']}\n"
        f"Ausgangs-Intensität (1-10): {profile['ausgangs_intensitaet']}\n\n"
        "Erstelle jetzt den Power Talk für diese Person."
    )


def synthesize_speech(text: str, voice_id: str, speed: float = 1.0) -> str:
    """Ruft ElevenLabs TTS auf und gibt das Audio als Base64-MP3 zurück."""
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {"speed": speed},
        },
        timeout=60,
    )
    response.raise_for_status()
    return base64.b64encode(response.content).decode("ascii")


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
        html = (
            PAGE_HTML.replace("__PROFILE_JSON__", json.dumps(DEFAULT_PROFILE, ensure_ascii=False))
            .replace("__VARIANTS_JSON__", json.dumps(DEFAULT_VARIANTS, ensure_ascii=False))
            .replace("__MODELS_JSON__", json.dumps(AVAILABLE_MODELS, ensure_ascii=False))
            .replace("__PRESETS_JSON__", json.dumps(PROFILE_PRESETS, ensure_ascii=False))
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
            want_audio = payload.get("generate_audio", False)
            voice_id = payload.get("voice_id") or DEFAULT_VOICE_ID
            voice_speed = float(payload.get("voice_speed") or 1.0)

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt.")

            client = anthropic.Anthropic(api_key=api_key)
            user_message = build_user_message(profile)

            results = {}
            for name, variant in variants.items():
                model = variant.get("model") or DEFAULT_MODEL
                try:
                    response = client.messages.create(
                        model=model,
                        max_tokens=1024,
                        system=variant["prompt"],
                        messages=[{"role": "user", "content": user_message}],
                    )
                    text = "".join(
                        b.text for b in response.content if b.type == "text"
                    )
                    text = text.strip()
                    result = {"text": text, "model": model}

                    if want_audio:
                        if not ELEVENLABS_API_KEY:
                            result["audio_error"] = "ELEVENLABS_API_KEY ist nicht gesetzt."
                        else:
                            try:
                                result["audio_base64"] = synthesize_speech(text, voice_id, voice_speed)
                            except Exception as audio_err:
                                result["audio_error"] = str(audio_err)

                    results[name] = result
                except Exception as e:
                    results[name] = {"error": str(e), "model": model}

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
            "Die Seite lädt, aber Generieren wird fehlschlagen.",
            file=sys.stderr,
        )
    if not APP_PASSWORD:
        print(
            "Warnung: APP_PASSWORD ist nicht gesetzt. Auf einem öffentlichen "
            "Server bedeutet das: kein Passwortschutz.",
            file=sys.stderr,
        )
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Power Talk Prototyp läuft auf Port {PORT}")
    print("Zum Beenden: Strg+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
