# -*- coding: utf-8 -*-
"""
Contrôle du template avant de le pousser (même rôle que ceux de DDNet et Mumble).

    python verifier.py

Unciv n'a pas de fichier de réglages : tout passe par la ligne de commande de
UncivServer.jar. Ce qui casse en silence n'est donc pas une regex de config,
mais un {{Réglage}} mal orthographié dans la ligne de commande, un drapeau que
le serveur ne connaît pas, ou un motif de console qui ne reconnaît pas la
ligne « prêt ». Le script teste :

1. tous les JSON se parsent ;
2. le .kvp ne référence que des fichiers présents, et le port principal existe ;
3. chaque {{Réglage}} utilisé est défini, et chaque réglage défini sert ;
4. les choix proposés pour -auth / -chat / -Identify sont des drapeaux que
   UncivServer 4.22.8 accepte (relevés dans son --help le 10 oct. 2026) ;
5. la ligne de commande, réglages par défaut, est exactement celle qui a
   tourné dans le conteneur d'essai ;
6. logback.xml est un XML valide, au niveau INFO, au nom passé à Java ;
7. les regex de console reconnaissent de vraies lignes du serveur ;
8. le .kvp contient tout le bloc Console.* / Limits.*.
"""
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ICI = os.path.dirname(os.path.abspath(__file__))
NOM = 'unciv'
soucis = []


def lire_json(nom):
    with io.open(os.path.join(ICI, nom), encoding='utf-8') as f:
        return json.load(f)


def py(motif):
    # AMP est en C# : (?<nom>...) ; Python veut (?P<nom>...)
    return re.compile(motif.replace('(?<', '(?P<'))


# ── 1. JSON ──────────────────────────────────────────────────────────────────
data = {}
for nom in ('manifest.json', NOM + 'config.json', NOM + 'metaconfig.json',
            NOM + 'ports.json', NOM + 'updates.json'):
    try:
        data[nom] = lire_json(nom)
        print('ok   %-22s JSON valide' % nom)
    except Exception as e:
        soucis.append('%s : JSON invalide (%s)' % (nom, e))
if soucis:
    print('\n'.join('NON  ' + s for s in soucis))
    sys.exit(1)

kvp = io.open(os.path.join(ICI, NOM + '.kvp'), encoding='utf-8').read()
cles = dict(l.split('=', 1) for l in kvp.splitlines() if '=' in l)
config = data[NOM + 'config.json']
updates = data[NOM + 'updates.json']
ports = data[NOM + 'ports.json']

# ── 2. fichiers inclus, port principal ───────────────────────────────────────
for ref in re.findall(r'@IncludeJson\[([^\]]+)\]', kvp):
    if os.path.isfile(os.path.join(ICI, ref)):
        print('ok   @IncludeJson         %s' % ref)
    else:
        soucis.append('@IncludeJson[%s] : fichier absent' % ref)
for cle in ('Meta.ConfigManifest', 'Meta.MetaConfigManifest'):
    if not os.path.isfile(os.path.join(ICI, cles.get(cle, '').strip() or '?')):
        soucis.append('%s pointe sur un fichier absent' % cle)
refs = {p['Ref'] for p in ports}
if cles.get('App.PrimaryApplicationPortRef') not in refs:
    soucis.append('PrimaryApplicationPortRef ne correspond à aucun port')
for r in re.findall(r'\$(\w+)', cles.get('App.CommandLineArgs', '') + cles.get('Meta.EndpointURIFormat', '')):
    if r not in refs:
        soucis.append('{{$%s}} : aucun port ne porte ce Ref' % r)
print('ok   ports                %s' % ', '.join('%s %s/%s' % (p['Ref'], p['Port'], p['Protocol']) for p in ports))

# ── 3. réglages utilisés <-> réglages définis ────────────────────────────────
definis = {c['FieldName'] for c in config}
texte_utilise = cles['App.CommandLineArgs'] + json.dumps(updates)
utilises = set(re.findall(r'\{\{([A-Za-z]\w*)\}\}', texte_utilise))
for u in sorted(utilises - definis):
    soucis.append('{{%s}} utilisé mais défini nulle part dans %sconfig.json' % (u, NOM))
for d in sorted(definis - utilises):
    soucis.append('réglage %s défini mais jamais utilisé : il ne servirait à rien' % d)
if not (utilises ^ definis):
    print('ok   réglages             %d définis, tous utilisés' % len(definis))
noms = [c['FieldName'] for c in config]
if len(noms) != len(set(noms)):
    soucis.append('réglages en double')

# ── 4. drapeaux reconnus par le serveur ──────────────────────────────────────
# Relevé de `java -jar UncivServer.jar --help` (4.22.8) :
#   -a, -auth / -no-auth   -c, -chat / -no-chat   -i, -Identify / -no-Identify
DRAPEAUX = {
    'UncivAuth': {'-auth', '-no-auth'},
    'UncivChat': {'-chat', '-no-chat'},
    'UncivIdentify': {'-Identify', '-no-Identify'},
}
par_nom = {c['FieldName']: c for c in config}
for champ, permis in DRAPEAUX.items():
    c = par_nom.get(champ)
    if not c:
        soucis.append('réglage %s absent' % champ)
        continue
    valeurs = set(c['EnumValues'])
    if valeurs != permis:
        soucis.append('%s : choix %s, le serveur attend %s' % (champ, sorted(valeurs), sorted(permis)))
    elif c['DefaultValue'] not in permis:
        soucis.append('%s : valeur par défaut inconnue du serveur' % champ)
    else:
        print('ok   drapeau              %-14s défaut %s' % (champ, c['DefaultValue']))
if par_nom.get('UncivIdentify', {}).get('DefaultValue') != '-no-Identify':
    soucis.append('UncivIdentify doit rester à -no-Identify par défaut (IP = donnée personnelle)')

# ── 5. ligne de commande par défaut = celle de l'essai ───────────────────────
ligne = cles['App.CommandLineArgs']
for c in config:
    ligne = ligne.replace('{{%s}}' % c['FieldName'], c.get('DefaultValue', ''))
for p in ports:
    ligne = ligne.replace('{{$%s}}' % p['Ref'], str(p['Port']))
ligne = ' '.join(ligne.split())
# Essai du 10/10 fait avec -p 8080 ; défaut passé à 8180 le 11/10 (8080 = port web d'AMP sur le dédié).
ESSAI = ('-Xmx512m -Dlogback.configurationFile=logback.xml -jar UncivServer.jar '
         '-p 8180 -f "MultiplayerFiles" -auth -chat -no-Identify')
if ligne != ESSAI:
    soucis.append('ligne de commande par défaut différente de celle testée :\n       %s\n       %s' % (ligne, ESSAI))
else:
    print('ok   ligne de commande    identique à l’essai du 10/10')

# ── 6. téléchargements et logback.xml ────────────────────────────────────────
gh = [e for e in updates if e['UpdateSource'] == 'GithubRelease']
if not gh or gh[0]['UpdateSourceArgs'] != 'yairm210/Unciv' or gh[0]['UpdateSourceData'] != 'UncivServer.jar':
    soucis.append('étape GithubRelease : dépôt ou nom de fichier inattendu')
elif ' -jar %s ' % gh[0]['UpdateSourceData'] not in ' %s ' % cles['App.CommandLineArgs']:
    soucis.append('le .jar téléchargé n’est pas celui que lance la ligne de commande')
else:
    print('ok   GithubRelease        yairm210/Unciv -> UncivServer.jar')
dossier = cles['App.BaseDirectory'].strip('./')
java = [e for e in updates if e['UpdateSource'] == 'Executable' and 'temurin' in e['UpdateSourceArgs'].lower()]
if not java or not java[0]['UpdateSourceArgs'].startswith('-c "cd %s && ' % dossier):
    soucis.append('l’étape Java ne se place pas dans ./%s/' % dossier)
elif cles['App.ExecutableLinux'] != 'java/bin/java':
    soucis.append('App.ExecutableLinux devrait être java/bin/java (installé par l’étape Java)')
else:
    print('ok   Java                 Temurin {{JavaVersion}} dans ./%s/java' % dossier)

lb = [e for e in updates if e['UpdateSource'] == 'CreateFile' and e['UpdateSourceArgs'].endswith('logback.xml')]
if not lb:
    soucis.append('aucune étape CreateFile pour logback.xml')
else:
    if lb[0].get('OverwriteExistingFiles') is not False:
        soucis.append('logback.xml ne doit pas être écrasé à chaque Update')
    try:
        racine = ET.fromstring(lb[0]['UpdateSourceData'].encode('utf-8'))
        niveau = racine.find('root').get('level')
        if niveau != 'INFO':
            soucis.append('logback.xml : niveau %s au lieu de INFO' % niveau)
        else:
            print('ok   logback.xml          XML valide, niveau INFO')
    except Exception as e:
        soucis.append('logback.xml : XML invalide (%s)' % e)
    if '-Dlogback.configurationFile=logback.xml' not in cles['App.CommandLineArgs']:
        soucis.append('Java ne reçoit pas -Dlogback.configurationFile=logback.xml')

# Les mots de passe des joueurs (server.auth) ne sont écrits QUE dans le
# crochet d'arrêt de la JVM : un arrêt brutal les perd. SIGTERM le déclenche
# (vérifié dans le conteneur d'essai).
if cles.get('App.ExitMethod') != 'SIGTERM':
    soucis.append('App.ExitMethod doit être SIGTERM, sinon server.auth n’est pas enregistré')

# ── 7. regex de console sur de vraies lignes (UncivServer 4.22.8, 10/10) ─────
pret = py(cles['Console.AppReadyRegex'])
jeter = py(cles['Console.ThrowawayMessageRegex'])
ESSAIS = [
    (pret, 'Server running on http://localhost:8080! Press Ctrl+C to stop', True),
    # port 80 : le serveur n'écrit pas « :80 » (portStr vide dans UncivServer.kt)
    (pret, 'Server running on http://localhost! Press Ctrl+C to stop', True),
    (pret, 'Starting UncivServer for /srv/unciv/MultiplayerFiles on http://localhost:8080', False),
    (pret, '2026-10-10 14:49:10 INFO  Responding at http://0.0.0.0:8080', False),
    (jeter, '14:46:27.919 [main] DEBUG io.netty.util.internal.logging.InternalLoggerFactory -- Using SLF4J as the default logging framework', True),
    (jeter, '14:46:28.617 [eventLoopGroupProxy-4-1] INFO io.ktor.server.Application -- Receiving file: 0b3e6a52-8a1d-4f62-9b7a-3c1e2d4f5a6b', False),
    (jeter, '2026-10-10 14:49:10 INFO  Received auth password set from localhost', False),
    (jeter, 'Server running on http://localhost:8080! Press Ctrl+C to stop', False),
]
for motif, l, attendu in ESSAIS:
    if bool(motif.search(l)) != attendu:
        soucis.append('%s %s : %s' % ('AppReady' if motif is pret else 'Throwaway',
                                      'devrait reconnaître' if attendu else 'ne devrait pas reconnaître', l))
print('ok   console              %d lignes réelles testées' % len(ESSAIS))

# ── 8. kvp complet ───────────────────────────────────────────────────────────
ATTENDUES = ['App.SupportsUniversalSleep', 'App.WakeupMode', 'App.ApplicationReadyMode', 'Console.FilterMatchRegex', 'Console.FilterMatchReplacement', 'Console.ThrowawayMessageRegex', 'Console.AppReadyRegex', 'Console.UserJoinRegex', 'Console.UserLeaveRegex', 'Console.UserChatRegex', 'Console.UpdateAvailableRegex', 'Console.PreConnectRegex', 'Console.ConnectIPRegex', 'Console.MetricsRegex', 'Console.HideFromConsoleRegex', 'Console.SuppressLogAtStart', 'Console.UserActions', 'Limits.SleepMode', 'Limits.SleepOnStart', 'Limits.SleepDelayMinutes', 'Limits.DozeDelay', 'Limits.AutoRetryCount', 'Limits.SleepStartThresholdSeconds']
absentes = [c for c in ATTENDUES if c not in cles]
if absentes:
    soucis.append('clés absentes du .kvp : ' + ', '.join(absentes))
else:
    print('ok   kvp complet          les %d clés Console/Limits sont là' % len(ATTENDUES))
if cles.get('App.ApplicationReadyMode') == 'RegexMatch' and not cles.get('Console.AppReadyRegex'):
    soucis.append('RegexMatch sans AppReadyRegex')

print()
if soucis:
    print('%d problème(s) :' % len(soucis))
    print('\n'.join('  NON  ' + s for s in soucis))
    sys.exit(1)
print('Tout est bon.')
