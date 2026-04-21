# 1. Supprimer la base de données
Remove-Item db.sqlite3 -Force -ErrorAction SilentlyContinue

# 2. Supprimer les dossiers migrations
Remove-Item users\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item publication\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item citation\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item journal\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item keywords\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item coAuthor\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item laboratory\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item institution\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item team\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item chatbot\migrations -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item data_pipeline\migrations -Recurse -Force -ErrorAction SilentlyContinue

# 3. Recréer les dossiers migrations
New-Item -Path users\migrations -ItemType Directory -Force | Out-Null
New-Item -Path users\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path publication\migrations -ItemType Directory -Force | Out-Null
New-Item -Path publication\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path citation\migrations -ItemType Directory -Force | Out-Null
New-Item -Path citation\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path journal\migrations -ItemType Directory -Force | Out-Null
New-Item -Path journal\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path keywords\migrations -ItemType Directory -Force | Out-Null
New-Item -Path keywords\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path coAuthor\migrations -ItemType Directory -Force | Out-Null
New-Item -Path coAuthor\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path laboratory\migrations -ItemType Directory -Force | Out-Null
New-Item -Path laboratory\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path institution\migrations -ItemType Directory -Force | Out-Null
New-Item -Path institution\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path team\migrations -ItemType Directory -Force | Out-Null
New-Item -Path team\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path chatbot\migrations -ItemType Directory -Force | Out-Null
New-Item -Path chatbot\migrations\__init__.py -ItemType File -Force | Out-Null

New-Item -Path data_pipeline\migrations -ItemType Directory -Force | Out-Null
New-Item -Path data_pipeline\migrations\__init__.py -ItemType File -Force | Out-Null

# 4. Créer et appliquer les migrations
python manage.py makemigrations
python manage.py migrate

# 5. Créer le superutilisateur
python manage.py createsuperuser

python manage.py runserver

admin
admin@gmail.com
15aout2004

& c:\Users\ridae\libratech\venv\Scripts\Activate.ps1  