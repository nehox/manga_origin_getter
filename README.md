# Manga Origine Getteur

MVP backend web qui prend une URL oeuvre, découvre tous les chapitres, récupère les images de chaque chapitre, puis génère un PDF par chapitre.

Domaines actuellement supportes:

- https://mangas-origines.fr
- https://hentai-origines.com

## Stack actuelle

- Python 3.9+
- FastAPI
- httpx + BeautifulSoup (extraction)
- Pillow (assemblage PDF)

## Lancer en local

Option rapide (recommandee):

```bash
./start-stack.sh
```

Le script:

- cree la venv si besoin
- met a jour pip/setuptools/wheel
- installe le projet en editable
- lance uvicorn

Les recuperations tournent en background: tu peux lancer plusieurs jobs sans attendre la fin du precedent.

Nombre de jobs traites en parallele (par defaut 2):

```bash
export BACKGROUND_JOB_WORKERS=3
./start-stack.sh
```

Options utiles:

```bash
./start-stack.sh --no-run
./start-stack.sh --host 0.0.0.0 --port 8080
```

1. Aller dans le dossier backend.
2. Installer les dépendances.
3. Lancer le serveur FastAPI.

Exemple:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e .
uvicorn app.main:app --reload
```

Si ton pip ne supporte pas le mode editable avec pyproject:

```bash
python -m pip install --upgrade pip setuptools wheel
pip install .
```

Ouvrir ensuite:

- http://127.0.0.1:8000/ (home Bibliotheque)
- http://127.0.0.1:8000/downloads.html (page telechargements)

## Lancer avec Docker

```bash
docker compose up -d --build
```

Ouvrir ensuite http://127.0.0.1:8000/

Volumes montes:

- `./backend/data` -> donnees persistantes (base SQLite, jobs) sur le host
- `./library` -> dossier a utiliser comme racine de bibliotheque dans le container (chemin `/library`)

Ajoute `/library` comme racine dans la page Parametres, puis copie tes mangas dans `./library` sur le host.

Variables d'environnement optionnelles (dans un fichier `.env` a la racine du repo):

```bash
MANGA_SOURCE_COOKIE=...
```

Arreter le stack:

```bash
docker compose down
```

## Acces source protege (Cloudflare)

Selon les moments, le site source peut renvoyer HTTP 403 via Cloudflare aux clients non navigants.
Le backend supporte un cookie de session optionnel:

```bash
export MANGA_SOURCE_COOKIE="cf_clearance=...; other_cookie=..."
```

Puis relancer le serveur.

## Endpoints

- GET /healthz
- POST /jobs
- GET /jobs
- GET /jobs/{job_id}
- POST /jobs/{job_id}/retry-failed
- GET /jobs/{job_id}/chapters/{chapter_slug}/pdf
- GET /settings/storage
- POST /settings/purge
- GET /library/overview
- GET /library/mangas/{manga_id}
- GET /library/roots
- POST /library/roots
- DELETE /library/roots/{root_id}
- POST /library/mangas
- PATCH /library/mangas/{manga_id}
- POST /library/mangas/{manga_id}/scan
- POST /library/mangas/{manga_id}/download-missing
- DELETE /library/mangas/{manga_id}
- POST /library/scan-all

Le bouton "Relancer les chapitres failed" dans l'interface relance uniquement les chapitres en echec du job selectionne.

Pages:

- `/` : catalogue (home Bibliotheque)
- `/add-manga.html` : ajouter un manga suivi via URL
- `/link-manga.html` : lier un dossier local deja present a une URL d'oeuvre
- `/manga-detail.html?id=...` : detail d'un manga (chapitres + statut, actions scan/telechargement)
- `/downloads.html` : jobs de recuperation ponctuels (ancienne home)
- `/settings.html` (Parametres) : gestion des racines de bibliotheque, stats de stockage, purge des donnees locales

Bibliotheque:

- persistance SQLite (`backend/data/library.db`)
- plusieurs racines de bibliotheque possibles (gerees depuis la page Parametres), chaque manga suivi est rattache a une racine
- memorisation des URLs oeuvre suivies
- detection chapitres presents/manquants/indisponibles et gaps numeriques, avec table de statut par chapitre sur la page detail
- auto-scan planifie par manga via `scan_interval_minutes`, avec telechargement auto optionnel des chapitres manquants

### POST /jobs exemple

```json
{
	"source_url": "https://mangas-origines.fr/oeuvre/demon-slave/",
	"max_concurrency": 4,
	"output_dir": "/Users/toi/Downloads/manga-pdf"
}
```

`output_dir` est optionnel. Quand il est fourni, tous les PDF du job sont ecrits dans ce dossier, sous un sous-dossier du nom de l'oeuvre.

## Limites du démarrage

- Jobs de recuperation ponctuels toujours en repository memoire (pas d'historique persistant), seule la bibliotheque est en SQLite
- Pas encore de workers Celery/Redis
- Adaptateurs fournis pour mangas-origines.fr et hentai-origines.com
- Certaines pages peuvent etre bloquees par Cloudflare sans cookie de session valide
- Pas encore de retries avancés ni rate-limiter centralisé
- Pas de suite de tests automatises

## Prochaine itération

- Ajouter stockage SQL pour les jobs (historique persistant)
- Ajouter file de tâches Celery + Redis
- Ajouter retries/backoff et classification erreurs
- Ajouter tests unitaires et intégration
