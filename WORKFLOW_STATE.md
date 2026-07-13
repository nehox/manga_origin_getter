# WORKFLOW STATE

## Plan global

Refactoring du projet Manga Origine Getteur pour eliminer les incoherences et ameliorer la qualite du code.

## Phases

### Phase 1 : Nettoyeur
- [x] Supprimer backend/setup.py (vide, redondant avec pyproject.toml)
- [x] Supprimer le modele orphelin JobPaths dans models.py

### Phase 2 : Refactorer
- [x] Creer backend/app/services/utils.py avec utc_now(), to_iso(), utcnow_iso(), build_job_view()
- [x] Mettre a jour library_service.py pour utiliser utils.py
- [x] Mettre a jour library_store.py pour utiliser utils.py
- [x] Mettre a jour main.py pour utiliser build_job_view()

### Phase 3 : Frontender
- [x] Creer backend/app/static/css/style.css
- [x] Creer backend/app/static/js/app.js
- [x] Mettre a jour les 6 HTML pour utiliser les fichiers partages

### Phase 4 : Testeur
- [x] Ajouter pytest en dev-dependencies
- [x] Creer les tests

## Statut

Phase 1-4 terminees. Toutes les phases du refactoring sont completes.
