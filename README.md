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

- http://127.0.0.1:8000/

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
- GET /jobs/{job_id}
- GET /jobs/{job_id}/chapters/{chapter_slug}/pdf

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

- Repository en mémoire (pas de base persistante encore)
- Pas encore de workers Celery/Redis
- Adaptateur fourni pour mangas-origines.fr
- Certaines pages peuvent etre bloquees par Cloudflare sans cookie de session valide
- Pas encore de retries avancés ni rate-limiter centralisé

## Prochaine itération

- Ajouter stockage SQL (jobs + historique)
- Ajouter file de tâches Celery + Redis
- Ajouter retries/backoff et classification erreurs
- Ajouter tests unitaires et intégration
