# AMPTemplates-Unciv — Unciv multiplayer server for AMP

**AMP Generic Module** template to host the official multiplayer server of
**Unciv** (the open-source Civilization V remake, `yairm210/Unciv`) on Linux.
Written for TeamKit on 10 Oct. 2026. CubeCoders has no Unciv template.

> Résumé en français à la fin du fichier.

## What this server is (and is not)

Unciv multiplayer is **turn-based file exchange over HTTP**. The server stores
one file per game (plus a `_Preview` file); each client uploads the game after
its turn and polls for the others'. There is no persistent game connection.

Consequences for AMP:

- **No player list.** AMP shows `0` users all the time, and that is correct:
  there is no join/leave line to read. `App.MaxUsers=0`, as in CubeCoders'
  non-game templates (MariaDB, Node, code-server). Activity shows up in the
  console instead (`Receiving file: <game id>`, `File requested: <game id>_Preview`).
- **One TCP port** (8080 by default). Chat uses the same port (WebSocket `/chat`).
- Opening `http://IP:port/` in a browser gives **404 — that is normal**, there
  is no page at `/`. The health route is `/isalive`.

## How it installs

| Update stage | What it does |
|---|---|
| `GithubRelease` `yairm210/Unciv` → **`UncivServer.jar`** | exact asset name, checked in release 4.22.8 (8 Oct. 2026, 22.8 MB). Empty *Server version* = latest release |
| Java download | **Eclipse Temurin** into `./unciv/java/`, copied verbatim from CubeCoders' Mindustry template (only `cd mindustry` → `cd unciv`) |
| `CreateFile` `logback.xml` | never overwritten (see below) |

Container image: `cubecoders/ampbase:debian` (has `wget` and `jq`, which the
Java stage needs — checked). Container is supported, not required.

Command line built by AMP (defaults):

```
java/bin/java -Xmx512m -Dlogback.configurationFile=logback.xml -jar UncivServer.jar -p 8080 -f "MultiplayerFiles" -auth -chat -no-Identify
```

This exact line was run in a throwaway container on 10 Oct. 2026 (see
`FAISABILITE.md`); `verifier.py` checks that the template still produces it.

## Server options — where each one comes from

All read in `server/src/com/unciv/app/server/UncivServer.kt` (tag 4.22.8) and
confirmed by `java -jar UncivServer.jar --help`:

```
  -p, -port=<int>               Server port
  -f, -folder=<text>            Multiplayer file's folder
  -a, -auth / -no-auth          Enable Authentication
  -c, -chat / -no-chat          Enable Authentication      (sic: upstream typo, it is the chat)
  -i, -Identify / -no-Identify  Display each operation archive request IP ...
```

Note the **single dash** (`-auth`, not `--auth`) and that **auth and chat are
ON by default**, Identify is off. Defaults: port `8080`, folder `MultiplayerFiles`.

| AMP setting (French UI) | Flag | Default |
|---|---|---|
| Port HTTP du serveur (Network tab) | `-p` | 8080/TCP |
| Authentification des joueurs | `-auth` / `-no-auth` | `-auth` |
| Chat en partie | `-chat` / `-no-chat` | `-chat` |
| Afficher l'adresse IP des joueurs | `-Identify` / `-no-Identify` | `-no-Identify` (an IP is personal data) |
| Dossier des parties | `-f` | `MultiplayerFiles` |
| Version du serveur | GitHub release tag | latest |
| Version de Java | Temurin 21 or 25 | 21 |
| Mémoire maximale de Java (Mo) | `-Xmx` | 512 |
| Paramètres Java supplémentaires | before `-jar` | empty |

### What authentication really does

From the source: with `-auth`, a player may register a password for their
user ID (`PUT /auth`, 6 characters minimum). From then on, uploads with that
user ID need the password. A user ID without a password is still accepted.
With `-no-auth`, `/auth` does not exist (404, tested) and anyone who knows a
user ID and a game ID can upload that game.

**Chat needs auth**: the `/chat` WebSocket rejects any user ID that has no
password in `server.auth` — so with `-no-auth`, chat cannot work.

### Three things to know about `server.auth`

1. It lives in the **server folder** (working directory), not in the games
   folder, format `userId:password`, **passwords in plain text**.
2. It is written **only when the JVM shuts down** (shutdown hook). That is
   why `App.ExitMethod=SIGTERM`: tested, SIGTERM triggers the hook and the
   file is written. A hard kill loses the passwords set since the last start.
3. Upstream bug, reproduced: a password containing **`:`** works until the
   next restart, then is rejected (the file is split on `:`). Tell players
   not to use `:` in their password.

## Why `logback.xml`

`UncivServer.jar` ships logback but no configuration, so logback falls back
to **DEBUG**: 52 Netty lines at every start (measured). The template drops a
`logback.xml` at INFO level, with the date in front of each line. If someone
deletes it, `Console.ThrowawayMessageRegex` still discards the DEBUG lines.

## Console

| What AMP learns | Real line |
|---|---|
| server ready (`AppReadyRegex`) | `Server running on http://localhost:8080! Press Ctrl+C to stop` |

On port 80 the server prints no `:80` (source: `portStr` is empty), the regex
accepts both. The line is printed right after Netty starts listening.

## How a player connects

1. In Unciv: **Options → Multiplayer → Server address**. The field is
   pre-filled with `https://`: replace it with **`http://IP:port`** (the URL
   must start with `http://` or `https://`, `MultiplayerTab.kt`).
2. **Check connection** → *Success!*
3. If authentication is on: type a password (6+ characters) and **Set password**.
4. Everyone in a game must use **the same server address** (the address is
   stored in the game). Creating and joining a game: `docs/Other/Multiplayer.md`
   (copy user ID, start a new game with *Online multiplayer*, share the game ID).

### Is HTTPS needed for Android? No.

`android/AndroidManifest.xml` sets `android:usesCleartextTraffic="true"`, with
the upstream comment *"Cleartext traffic permission solely so users can host
their own server without setting up https"*. There is no
`networkSecurityConfig` overriding it. Desktop (Java) has no such restriction.
So plain `http://IP:port` is accepted by the Android client. (Verified in the
manifest and source; not tested on a real phone.)

HTTPS is still **worth it** for privacy: in HTTP the password travels in
clear (Basic auth) on every upload. TeamKit can put nginx in front
(`https://unciv.example`); the client then switches the chat to `wss://`
(`ChatWebSocket.kt`), so nginx must forward the WebSocket upgrade on `/chat`.

## Resources (measured)

| | |
|---|---|
| RAM, idle | ~120 MB resident (measured 97–122 MB across runs, Java 21 and 25) |
| Disk | jar 22 MB + Temurin JDK 346 MB, plus the games |
| Start | ~1 s to the ready line |
| Max game file | 32 MB (constant in the source) |

Games are **never deleted** by the server, even finished ones.

## Backups

`App.SmartExcludeExemptions=["*.xml","*.auth"]` keeps `logback.xml` and
`server.auth` in AMP backups. The games (files without extension, created by
the server, not by an update) are normal data. Check one backup after the
first games to be sure the games folder is in it.

## Before pushing

```
python verifier.py
```

Must print `Tout est bon.`: JSON, included files, every `{{Setting}}` used is
defined and every defined setting is used, auth/chat/identify choices are
real server flags, default command line identical to the tested one,
`logback.xml` valid, console regexes tested on real lines, complete `.kvp`.

## Install in AMP

ADS → Configuration → Instance Deployment → **Configuration Repositories**:
add `hydrocut/AMPTemplates-Unciv:main`, save, **Fetch latest**.
Then Create Instance → **Unciv (TeamKit)** → **Update** → **Start**.

## Sources

- `server/src/com/unciv/app/server/UncivServer.kt` (tag 4.22.8): options, routes, `server.auth`, logs
- `docs/Other/Multiplayer.md`, section *Hosting a Multiplayer server* (there is no separate `Hosting-a-Multiplayer-server.md`)
- `android/AndroidManifest.xml`: cleartext HTTP allowed
- `core/src/com/unciv/ui/popups/options/MultiplayerTab.kt`, `core/src/com/unciv/logic/multiplayer/storage/MultiplayerServer.kt`, `core/src/com/unciv/logic/multiplayer/chat/ChatWebSocket.kt`: client side
- `android/assets/jsons/translations/French.properties`: French menu labels
- CubeCoders `mindustry.kvp` / `mindustryupdates.json`: GithubRelease + Temurin pattern

## Credits

Unciv is free software (MPL-2.0) by Yair Morgenstern and contributors. This
repository only contains the template; the server is downloaded from Unciv's
GitHub releases at Update time.

---

## Résumé en français

Template AMP pour le **serveur multijoueur officiel d'Unciv** (`UncivServer.jar`,
releases GitHub). Le serveur est un simple **serveur HTTP de fichiers de parties** :
un seul port TCP (8080), pas de connexion permanente, donc **pas de liste de
joueurs dans AMP** (toujours 0, c'est normal).

- **Se connecter** : dans Unciv, Options → Multijoueur → « Adresse du serveur » :
  effacer le `https://` proposé et taper **`http://IP:port`**, puis « Vérifier la
  connexion » → « Succès ! ». Tous les joueurs d'une partie mettent la même adresse.
- **HTTPS pas obligatoire**, même sur Android : le jeu autorise le HTTP en clair
  (`usesCleartextTraffic="true"` dans son manifeste, exprès pour l'auto-hébergement).
  Mais le mot de passe passe en clair : un nginx en HTTPS devant reste conseillé
  (en laissant passer le WebSocket `/chat`).
- **Réglages en français dans AMP** : port, authentification (activée par défaut),
  chat, IP dans la console (non par défaut), dossier des parties, version, Java, mémoire.
- **Mots de passe** : stockés en clair dans `server.auth`, enregistrés seulement à
  l'arrêt propre (d'où l'arrêt par SIGTERM). Pas de `:` dans un mot de passe (bug du jeu).
- **Testé en vrai** le 10 oct. 2026 dans un conteneur jetable : démarrage en 1 s,
  ~120 Mo de RAM, dépôt et lecture de partie, mots de passe, redémarrage.
- Avant de pousser : `python verifier.py` doit répondre « Tout est bon. ».
