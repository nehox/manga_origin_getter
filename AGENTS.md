# Workflow de refactoring - Manga Origine Getteur

## Regles partagees

1. WORKFLOW_STATE.md est le fichier de handoff officiel.
2. Chaque agent lit WORKFLOW_STATE.md avant de commencer et met a jour sa section apres avoir termine.
3. Ne jamais modifier le code d'un autre agent sans coordonner via WORKFLOW_STATE.md.
4. Les agents s'arretent proprement si une tache prealable n'est pas complete.

## Ordre d'execution

1. Nettoyeur → supprime setup.py, JobPaths, code mort
2. Refactorer → cree utils.py, refactorise main.py, library_service.py, library_store.py
   Frontender → extrait CSS/JS partage (en parallele avec Refactorer)
3. Testeur → ajoute pytest et les tests (apres Refactorer et Frontender)
