# jmnews

Personalisierter News-Aggregator für JM. Sammelt täglich aus 11 deutschen
Berlin-/Brandenburg-Quellen (RSS + HTML-Scraping), filtert via Claude Haiku
gegen JMs Profil, generiert mit Claude Sonnet ein priorisiertes Briefing und
schickt es per Telegram.

## Architektur

```
Quellen (11)          Filter             Briefing          Delivery
─────────────         ──────             ────────          ────────
5x RSS         ┐
                ├──► Haiku 4.5    ──► Sonnet 4.6   ──► Telegram (HTML)
6x Scrape     ┘    (Pre-Filter)       (Markdown)        Fallback: Datei
                       ▲
                       │
                  jm_profile.md
                  (cached)
```

Storage: SQLite, dedupliziert per stabiler URL-Hash-ID, archiviert
Briefings, purge nach 30 Tagen.

## Quellen

**RSS** — Berlin Presseportal (aggregiert über 10 Senatsverwaltungen +
Bezirksämter), Tagesspiegel Berlin, Berliner Zeitung, taz Berlin, rbb24.

**HTML-Scraping** — IBB, ILB Brandenburg, BSFZ Bescheinigungsstelle
Forschungszulage, DaKS Berlin, NbF Brandenburg, Brandenburg Vorschriften
(bravors).

## Voraussetzungen

- Ubuntu 24.04 (Hetzner-VPS oder lokal)
- Docker + Docker Compose Plugin
- Anthropic API-Key (kostenpflichtig)
- Telegram Bot Token + Chat-ID

## VPS Setup

### 1. Docker installieren

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# neu einloggen, damit die Gruppenmitgliedschaft greift
```

### 2. Repo klonen

```bash
git clone https://github.com/julianmlr/jmnews.git
cd jmnews
```

### 3. `.env` befüllen

```bash
cp .env.example .env
$EDITOR .env
```

Mindestens setzen: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`. Alle weiteren Werte haben sinnvolle Defaults
(siehe `.env.example`).

### 4. Telegram-Bot einrichten

1. In Telegram zu `@BotFather` schreiben → `/newbot` → Namen wählen.
   Notiere das Bot-Token (Format `123456789:ABC-DEF…`).
2. Den Bot in deinem Chat einmal anschreiben (irgendwas, z.B. `/start`).
3. Chat-ID ermitteln:
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | jq '.result[].message.chat.id'
   ```
   Die zurückgegebene Zahl in `TELEGRAM_CHAT_ID` eintragen.

### 5. Starten

**Option A — Daemon (empfohlen, einfach):**

```bash
docker compose up -d --build
```

Läuft im Hintergrund, triggert die Pipeline täglich um 06:45 Berlin
(konfigurierbar via `JMNEWS_COLLECT_HOUR`/`MINUTE`).

**Option B — System-Cron (per Spec, geringerer Speicher-Footprint):**

```bash
docker compose build
crontab -e
# folgende Zeile einfügen:
0 6 * * * cd /home/USERNAME/jmnews && docker compose run --rm jmnews run-once >> data/logs/cron.log 2>&1
```

### 6. Logs prüfen

```bash
# Daemon
docker compose logs -f jmnews

# Letzte rotierende Logdatei
tail -f data/logs/jmnews.log

# Letztes Briefing (falls Telegram aus war, liegt es als Markdown hier)
ls -la data/briefings/
```

## Lokale Entwicklung

```bash
make install      # venv anlegen + Deps installieren
make test         # pytest
make lint         # ruff
make run-once     # einmaliger Pipeline-Run
make run-daemon   # APScheduler-Daemon im Vordergrund
```

## CLI

```bash
jmnews run-once     # einmalige End-to-End-Pipeline
jmnews run-daemon   # APScheduler-Daemon (blockierend)
jmnews version
```

## Konfiguration

Alles über Umgebungsvariablen (siehe `.env.example`):

| Variable | Default | Zweck |
|---|---|---|
| `ANTHROPIC_API_KEY` | _required_ | Anthropic API Key |
| `JMNEWS_FILTER_MODEL` | `claude-haiku-4-5-20251001` | Pre-Filter-Modell |
| `JMNEWS_BRIEFING_MODEL` | `claude-sonnet-4-6` | Briefing-Generator |
| `TELEGRAM_BOT_TOKEN` | _required_ | Bot-Token vom BotFather |
| `TELEGRAM_CHAT_ID` | _required_ | Eigene Chat-ID |
| `JMNEWS_LOOKBACK_HOURS` | `24` | Wie weit zurück Quellen scrapen |
| `JMNEWS_FILTER_BATCH_SIZE` | `15` | Items pro Haiku-Call |
| `JMNEWS_PURGE_DAYS` | `30` | DB-Items älter als X Tage löschen |
| `JMNEWS_TIMEZONE` | `Europe/Berlin` | Scheduler-Zeitzone |
| `JMNEWS_COLLECT_HOUR` / `_MINUTE` | `6` / `45` | Daemon-Trigger |

## JM-Profil anpassen

`jm_profile.md` ist die Single Source of Truth für Filter und Briefing.
Wird via Docker als Read-Only-Volume gemountet — Änderungen wirken
ohne Rebuild beim nächsten Run.

```bash
$EDITOR jm_profile.md
# nächste Pipeline lädt automatisch neu
```

## Troubleshooting

- **Telegram liefert nicht** → Briefing landet in `data/briefings/<datum>.md`.
  Häufige Ursachen: Bot ist nicht in eurem Chat, falsche `TELEGRAM_CHAT_ID`,
  Bot-Token revoked.
- **Eine Quelle wirft 403/Cloudflare** → andere Quellen laufen weiter; im
  Log siehst du, welche fehlgeschlagen ist. Selektoren in `src/jmnews/sources/`
  ggf. anpassen.
- **Filter-API-Fehler** → 3 Retries mit Exponential Backoff (2s/4s/8s).
  Nach 3 Fails bleibt der Batch als „unfiltered" in der DB und wird beim
  nächsten Run erneut versucht.

## Lizenz

Privates Projekt — keine Lizenz.
