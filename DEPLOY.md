# Deployment

Automatischer Deploy auf den Hetzner-VPS per GitHub Actions
([`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)):
bei jedem Push auf `main` SSH zum Server, `git pull`, `docker compose
up -d --build`. Manueller Trigger über GitHub-UI ist ebenfalls möglich
("Actions → Deploy to Hetzner → Run workflow").

## Einmaliges Setup

### 1. Deploy-SSH-Key generieren

Auf deinem lokalen Rechner — nicht den Hauptschlüssel verwenden, sondern
ein dediziertes Schlüsselpaar nur für diesen Deploy:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/jmnews_deploy -N "" -C "jmnews-deploy"
```

Das erzeugt zwei Dateien:
- `~/.ssh/jmnews_deploy` — privater Schlüssel (geht in GitHub Secrets)
- `~/.ssh/jmnews_deploy.pub` — öffentlicher Schlüssel (geht auf den Server)

### 2. Public Key auf dem Hetzner hinterlegen

```bash
ssh root@49.13.121.191 'cat >> ~/.ssh/authorized_keys' < ~/.ssh/jmnews_deploy.pub
```

Verifizieren, dass der neue Key wirklich greift:

```bash
ssh -i ~/.ssh/jmnews_deploy root@49.13.121.191 'echo ok'
```

### 3. GitHub-Secrets eintragen

Im Repo: **Settings → Secrets and variables → Actions → New repository secret**.

| Name | Wert |
|---|---|
| `HETZNER_HOST` | `49.13.121.191` |
| `HETZNER_USER` | `root` |
| `HETZNER_SSH_KEY` | kompletter Inhalt von `~/.ssh/jmnews_deploy` (inkl. `-----BEGIN OPENSSH PRIVATE KEY-----` / `-----END …-----`) |

### 4. Erstes Setup auf dem Server (einmalig manuell)

```bash
ssh root@49.13.121.191
cd /root
git clone https://github.com/julianmlr/jmnews.git
cd jmnews
cp .env.example .env
nano .env          # ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
docker compose up -d --build
docker compose logs -f jmnews
```

Der Workflow erwartet das Repo unter `/root/jmnews`. Andernfalls den
Pfad in `.github/workflows/deploy.yml` anpassen.

`.env` ist gitignored — der Workflow lässt sie unverändert. Wenn sich
am `.env.example` etwas ändert (neue Variable nötig), trägst du das
manuell in `/root/jmnews/.env` nach.

## Updates triggern

```bash
git push origin main
```

→ Workflow startet automatisch, baut den Container neu, restartet ihn.
Status unter **Actions** im GitHub-UI sichtbar; die letzten Log-Zeilen
des jmnews-Containers stehen am Ende des Workflow-Runs.

## Manueller Trigger

GitHub → Actions → "Deploy to Hetzner" → "Run workflow" → Branch wählen
→ Run.

## Rollback

Auf dem Server:

```bash
ssh root@49.13.121.191
cd /root/jmnews
git log --oneline -10           # frühere Commits ansehen
git reset --hard <commit-sha>
docker compose up -d --build
```

## Troubleshooting

**Workflow scheitert mit "Permission denied (publickey)"**
- Public Key nicht in `/root/.ssh/authorized_keys` auf dem Server, oder
- privater Key nicht 1:1 in `HETZNER_SSH_KEY` (Zeilenumbrüche müssen
  erhalten bleiben — am besten direkt via `cat` einfügen, nicht copy-paste
  aus einem editor mit Linewrap).

**Workflow scheitert mit "Host key verification failed"**
- Sollte nicht passieren — die appleboy/ssh-action umgeht das
  standardmäßig. Falls doch: dem Workflow `fingerprint: ...` hinzufügen.

**Container startet nicht**
- `docker compose logs jmnews` direkt auf dem Server prüfen
- Häufige Ursachen: `.env` unvollständig, ANTHROPIC_API_KEY falsch,
  oder Docker hat zu wenig Speicher (`docker system df`).
