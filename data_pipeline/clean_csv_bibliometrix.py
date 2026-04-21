#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧹 NETTOYAGE DU CSV BIBLIOMETRIX (VERSION CORRIGÉE)
Prépare le CSV pour Bibliometrix et R
"""

import pandas as pd
import numpy as np
import os
import re

print("\n" + "="*70)
print("  🧹 NETTOYAGE DU CSV BIBLIOMETRIX (VERSION CORRIGÉE)")
print("="*70 + "\n")

# ═══════════════════════════════════════════════════════════════════════════════
# 1️⃣ CHARGER LE CSV
# ═══════════════════════════════════════════════════════════════════════════════

filepath = "C:/Users/ridae/PFE/Backend/outputs/algeria_last_15_years_bibliometrix.csv"

print("📥 Chargement du CSV...")
df = pd.read_csv(filepath, low_memory=False)

print(f"✅ Chargé : {len(df)} lignes × {len(df.columns)} colonnes\n")

# ═══════════════════════════════════════════════════════════════════════════════
# 2️⃣ AJOUTER LA COLONNE MANQUANTE : DB ET DT
# ═══════════════════════════════════════════════════════════════════════════════

print("🔧 Ajout des colonnes manquantes...\n")

# Ajouter DB (Database)
if 'DB' not in df.columns:
    df['DB'] = 'Scopus'
    print(f"✅ Colonne DB ajoutée")

# Ajouter DT (Document Type)
if 'DT' not in df.columns:
    df['DT'] = 'Article'  # Défaut
    
    # Chercher des indices de type de document
    if 'TI' in df.columns:
        df.loc[df['TI'].str.contains('review', case=False, na=False), 'DT'] = 'Review'
        df.loc[df['TI'].str.contains('editorial', case=False, na=False), 'DT'] = 'Editorial'
        df.loc[df['TI'].str.contains('proceedings', case=False, na=False), 'DT'] = 'Conference Paper'
        df.loc[df['TI'].str.contains('book chapter', case=False, na=False), 'DT'] = 'Book Chapter'
    
    dt_counts = df['DT'].value_counts()
    print(f"✅ Colonne DT créée")
    for dtype, count in dt_counts.items():
        print(f"   {dtype}: {count:,}")

print()

# ═══════════════════════════════════════════════════════════════════════════════
# 3️⃣ NETTOYER LES COLONNES NUMÉRIQUES
# ═══════════════════════════════════════════════════════════════════════════════

print("🔢 Nettoyage des colonnes numériques...\n")

# PY (Publication Year) - doit être un nombre
if 'PY' in df.columns:
    df['PY'] = pd.to_numeric(df['PY'], errors='coerce')
    default_year = int(df['PY'].mode()[0]) if not df['PY'].mode().empty else 2020
    df['PY'] = df['PY'].fillna(default_year).astype(int)
    print(f"✅ PY nettoyée : {df['PY'].min()}-{df['PY'].max()}")

# TC (Times Cited) - doit être un nombre
if 'TC' in df.columns:
    df['TC'] = pd.to_numeric(df['TC'], errors='coerce').fillna(0).astype(int)
    print(f"✅ TC nettoyée : min={df['TC'].min()}, max={df['TC'].max():,}, moyenne={df['TC'].mean():.2f}")

print()

# ═══════════════════════════════════════════════════════════════════════════════
# 4️⃣ NETTOYER LES AUTEURS
# ═══════════════════════════════════════════════════════════════════════════════

print("👥 Nettoyage des auteurs...\n")

if 'AU' in df.columns:
    df['AU'] = df['AU'].fillna('Unknown')
    # Supprimer les guillemets qui peuvent causer des problèmes
    df['AU'] = df['AU'].str.replace('"', '', regex=False)
    print(f"✅ AU nettoyée")

print()

# ═══════════════════════════════════════════════════════════════════════════════
# 5️⃣ FILTRER LES JOURNAUX INVALIDES (VERSION CORRIGÉE)
# ═══════════════════════════════════════════════════════════════════════════════

print("📰 Filtrage des journaux invalides...\n")

before_count = len(df)

# Utiliser une boucle au lieu d'une regex complexe pour éviter les erreurs
invalid_journals = [
    'Zenodo',
    'Unknown Journal',
    'Unknown',
    'arXiv',
    'Arxiv',
    'SSRN',
    'ResearchGate',
    'GitHub',
    'bioRxiv',
    'medRxiv'
]

for journal in invalid_journals:
    if 'SO' in df.columns:
        # Utiliser str.contains avec regex=False pour éviter les erreurs regex
        mask = df['SO'].str.contains(journal, case=False, na=False, regex=False)
        df = df[~mask]
        removed = mask.sum()
        if removed > 0:
            print(f"   ❌ Supprimées {removed} lignes contenant '{journal}'")

after_count = len(df)
total_removed = before_count - after_count

print(f"\n✅ Total supprimé : {total_removed} lignes")
print(f"✅ Restantes : {after_count:,} lignes\n")

# ═══════════════════════════════════════════════════════════════════════════════
# 6️⃣ REMPLIR LES VALEURS MANQUANTES
# ═══════════════════════════════════════════════════════════════════════════════

print("🔨 Remplissage des valeurs manquantes...\n")

# TI (Title) - supprimer les lignes sans titre
if 'TI' in df.columns:
    before_ti = len(df)
    df = df.dropna(subset=['TI'])
    after_ti = len(df)
    if after_ti < before_ti:
        print(f"✅ TI nettoyée : {before_ti - after_ti} lignes sans titre supprimées")

# SO (Journal) - utiliser "Unknown Journal" si vide
if 'SO' in df.columns:
    df['SO'] = df['SO'].fillna('Unknown Journal')
    print(f"✅ SO remplie")

# DE, ID, AB, C1, RP, DI, PU, PI, AF - remplir avec chaînes vides
for col in ['DE', 'ID', 'AB', 'C1', 'RP', 'DI', 'PU', 'PI', 'AF']:
    if col in df.columns:
        df[col] = df[col].fillna('')

print(f"✅ Colonnes texte remplies avec chaînes vides")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# 7️⃣ RÉORGANISER LES COLONNES DANS L'ORDRE BIBLIOMETRIX
# ═══════════════════════════════════════════════════════════════════════════════

print("📐 Réorganisation des colonnes...\n")

# Ordre standard Bibliometrix
columns_order = ['AU', 'TI', 'PY', 'SO', 'TC', 'DE', 'ID', 'AB', 'C1', 'RP', 'DI', 'PU', 'PI', 'AF', 'DT', 'DB']

# Garder uniquement les colonnes qui existent
columns_order = [col for col in columns_order if col in df.columns]

# Réorganiser
df = df[columns_order]

print(f"✅ Colonnes réorganisées :")
for i, col in enumerate(columns_order, 1):
    print(f"   {i}. {col}")

print()

# ═══════════════════════════════════════════════════════════════════════════════
# 8️⃣ VÉRIFICATIONS FINALES ET DOUBLONS
# ═══════════════════════════════════════════════════════════════════════════════

print("✔️ VÉRIFICATIONS FINALES\n")

# Vérifier les doublons AVANT suppression
duplicates_before = df.duplicated(subset=['AU', 'TI', 'PY']).sum()

if duplicates_before > 0:
    print(f"🔄 Suppression des doublons...")
    df = df.drop_duplicates(subset=['AU', 'TI', 'PY'], keep='first')
    print(f"   ✅ {duplicates_before} doublons supprimés")
    print(f"   Publications restantes : {len(df):,}\n")
else:
    print(f"✅ Aucun doublon détecté\n")

# Statistiques finales
print(f"📊 STATISTIQUES FINALES :")
print(f"   Publications : {len(df):,}")
print(f"   Années : {df['PY'].min()}-{df['PY'].max()}")
print(f"   Journaux uniques : {df['SO'].nunique():,}")
print(f"   Citations totales : {df['TC'].sum():,}")
print(f"   Citations moyennes : {df['TC'].mean():.2f}")
print(f"   Valeurs TC nulles : {(df['TC'] == 0).sum():,} ({(df['TC'] == 0).sum()/len(df)*100:.1f}%)")

print()

# ═══════════════════════════════════════════════════════════════════════════════
# 9️⃣ SAUVEGARDER LE CSV NETTOYÉ
# ═══════════════════════════════════════════════════════════════════════════════

print("💾 Sauvegarde du CSV nettoyé...\n")

output_dir = "C:/Users/ridae/PFE/Backend/outputs"
output_filepath = os.path.join(output_dir, "algeria_bibliometrix_CLEANED.csv")

# Sauvegarder sans index et avec encodage UTF-8
df.to_csv(output_filepath, index=False, encoding='utf-8')

file_size_mb = os.path.getsize(output_filepath) / (1024*1024)

print(f"✅ Fichier sauvegardé :")
print(f"   Path: {output_filepath}")
print(f"   Size: {file_size_mb:.2f} MB")
print(f"   Rows: {len(df):,}")
print(f"   Columns: {len(df.columns)}")

print()

# ═══════════════════════════════════════════════════════════════════════════════
# 🔟 AFFICHER UN APERÇU
# ═══════════════════════════════════════════════════════════════════════════════

print("📋 APERÇU DES PREMIÈRES LIGNES :\n")

# Afficher les colonnes principales seulement
preview_cols = ['AU', 'TI', 'PY', 'SO', 'TC', 'DT']
print(df[preview_cols].head(3).to_string())

print("\n" + "="*70)
print("  ✅ NETTOYAGE TERMINÉ AVEC SUCCÈS!")
print("="*70 + "\n")

print("✨ Le CSV nettoyé est prêt pour Bibliometrix !\n")
print("📝 Utilise ce fichier dans R :\n")
print(f"   filepath <- \"{output_filepath}\"")
print(f"   data <- convert2df(filepath, dbsource = \"scopus\", format = \"csv\")\n")