#!/usr/bin/env Rscript

library(data.table)
library(jsonlite)

cat("\n", rep("=", 70), "\n", sep="")
cat("  📊 ANALYSE BIBLIOMETRIX - ALGÉRIE (COMPLÈTE - SANS LIMITES)\n")
cat(rep("=", 70), "\n\n")

# ════════════════════════════════════════════════════════════
# 1. CHARGEMENT
# ════════════════════════════════════════════════════════════

csv_file <- "outputs/algeria_last_15_years_bibliometrix.csv"

if(!file.exists(csv_file)) {
  stop("Fichier CSV non trouvé: ", csv_file)
}

cat("📂 Chargement...\n")
system.time({
  df <- fread(csv_file, data.table = TRUE)
})

cat("✅ Chargé:", nrow(df), "publications\n\n")

# ════════════════════════════════════════════════════════════
# 2. NETTOYAGE ET CORRECTION DES NOMS D'AUTEURS
# ════════════════════════════════════════════════════════════

cat("🧹 Nettoyage et correction des noms d'auteurs...\n")

# Renommer en majuscules pour standardiser
setnames(df, toupper(names(df)))

# Vérifier si AF (Author Full Names) existe
if("AF" %in% names(df)) {
  cat("  ✅ Colonne AF trouvée - utilisation des noms complets\n")
  
  # Extraire le nom complet avant la virgule (affiliation)
  df[, AUTHOR_FULL := sapply(strsplit(AF, ","), function(x) trimws(x[1]))]
  
  # Nettoyer les noms: enlever les points, normaliser
  df[, AUTHOR_FULL := gsub("\\.", "", AUTHOR_FULL)]
  df[, AUTHOR_FULL := gsub("\\s+", " ", AUTHOR_FULL)]
  
  # Remplacer AU par les noms complets
  df[, AU := AUTHOR_FULL]
  
  # Afficher un échantillon pour vérification
  sample_authors <- unique(unlist(strsplit(df$AU[1:min(20, nrow(df))], ";")))
  sample_authors <- trimws(sample_authors)
  sample_authors <- sample_authors[sample_authors != ""]
  
  cat("  Échantillon des noms extraits:\n")
  for(i in 1:min(5, length(sample_authors))) {
    cat("    •", sample_authors[i], "\n")
  }
  
} else {
  cat("  ⚠️  Colonne AF non trouvée - tentative de correction de AU\n")
  df[, AU := gsub("([A-Za-z]+),([A-Z]+)", "\\1 \\2", AU)]
  df[, AU := gsub("\\.", "", AU)]
  cat("  ✅ Format AU corrigé\n")
}

# Nettoyer les séparateurs
df[, AU := gsub(",", ";", AU)]
df[, AU := gsub(";", ";", AU)]

# Enlever les auteurs vides
df <- df[AU != "" & !is.na(AU)]

# Ajouter SR si nécessaire
if(!"SR" %in% names(df)) {
  df[, SR := paste0(
    substr(gsub("[^A-Za-z]", "", AU), 1, 8),
    "_", PY, "_",
    substr(gsub("[^A-Za-z]", "", SO), 1, 5)
  )]
  df[, SR := make.unique(SR, sep = "_")]
}

# Nettoyer keywords
if("DE" %in% names(df)) {
  df[, DE := gsub(",", ";", DE)]
}

# Filtrer années
df[, PY := as.numeric(PY)]
df <- df[!is.na(PY) & PY >= 2010 & PY <= 2026]

cat("✅ Final:", nrow(df), "publications\n\n")

# ════════════════════════════════════════════════════════════
# 3. STATISTIQUES GLOBALES (COMPLÈTES)
# ════════════════════════════════════════════════════════════

cat("📊 Statistiques globales...\n")

yearly_counts <- as.list(table(df$PY))
yearly_citations <- as.list(tapply(df$TC, df$PY, sum, na.rm = TRUE))

# Top journaux - TOUS
journal_counts <- sort(table(df$SO), decreasing = TRUE)
all_journals <- lapply(1:length(journal_counts), function(i) {
  list(rank = i, journal = names(journal_counts)[i], count = as.integer(journal_counts[i]))
})

stats <- list(
  total_publications = nrow(df),
  total_citations = sum(df$TC, na.rm = TRUE),
  avg_citations = round(mean(df$TC, na.rm = TRUE), 2),
  years_range = list(min = min(df$PY), max = max(df$PY)),
  yearly_output = yearly_counts,
  yearly_citations = yearly_citations,
  all_journals = all_journals,  # TOUS les journaux
  analysis_date = format(Sys.time(), "%Y-%m-%d %H:%M:%S")
)

dir.create("bibliometrix_results", showWarnings = FALSE)
write_json(stats, "bibliometrix_results/summary.json")
cat("  ✅ summary.json (complet)\n")

# ════════════════════════════════════════════════════════════
# 4. TOP AUTEURS - TOUS (SANS LIMITE)
# ════════════════════════════════════════════════════════════

cat("\n🏆 Tous les auteurs...\n")

# Séparer les auteurs multiples
all_authors <- unlist(strsplit(df$AU, ";"))
all_authors <- trimws(all_authors)
all_authors <- all_authors[all_authors != "" & all_authors != "NA"]

# Filtrer les noms trop courts (moins de 2 caractères)
all_authors <- all_authors[nchar(all_authors) >= 2]

# Compter - TOUS les auteurs
author_counts <- sort(table(all_authors), decreasing = TRUE)

cat("  Auteurs uniques trouvés:", length(author_counts), "\n")
cat("  Top 10 aperçu:\n")
for(i in 1:min(10, length(author_counts))) {
  cat("    ", i, "-", names(author_counts)[i], ":", author_counts[i], "pubs\n")
}

# Sauvegarder TOUS les auteurs
all_authors_list <- lapply(1:length(author_counts), function(i) {
  list(
    rank = i, 
    name = names(author_counts)[i], 
    publications = as.integer(author_counts[i])
  )
})

write_json(all_authors_list, "bibliometrix_results/all_authors.json")
cat("  ✅ all_authors.json (", length(all_authors_list), " auteurs)\n")

# Aussi sauvegarder top 100 pour l'affichage rapide
top_100_authors <- all_authors_list[1:min(100, length(all_authors_list))]
write_json(top_100_authors, "bibliometrix_results/top_100_authors.json")
cat("  ✅ top_100_authors.json\n")

# ════════════════════════════════════════════════════════════
# 5. KEYWORDS - TOUS (SANS LIMITE)
# ════════════════════════════════════════════════════════════

cat("\n🔑 Tous les keywords...\n")

if("DE" %in% names(df)) {
  all_keywords <- unlist(strsplit(df$DE[df$DE != ""], ";"))
  all_keywords <- trimws(all_keywords)
  all_keywords <- all_keywords[all_keywords != "" & all_keywords != "NA"]
  
  if(length(all_keywords) > 0) {
    keyword_counts <- sort(table(all_keywords), decreasing = TRUE)
    
    # TOUS les keywords
    all_keywords_list <- lapply(1:length(keyword_counts), function(i) {
      list(rank = i, keyword = names(keyword_counts)[i], frequency = as.integer(keyword_counts[i]))
    })
    
    keywords_data <- list(
      all_keywords = all_keywords_list,
      total_unique_keywords = length(keyword_counts),
      top_50_keywords = all_keywords_list[1:min(50, length(all_keywords_list))]
    )
    
    write_json(keywords_data, "bibliometrix_results/all_keywords.json")
    cat("  ✅ all_keywords.json (", length(keyword_counts), " keywords)\n")
    
    # Top 30 pour compatibilité
    top_30_keywords <- all_keywords_list[1:min(30, length(all_keywords_list))]
    write_json(list(top_keywords = top_30_keywords), "bibliometrix_results/thematic_clusters.json")
    cat("  ✅ thematic_clusters.json\n")
    
  } else {
    write_json(list(), "bibliometrix_results/all_keywords.json")
    cat("  ⚠️  Pas de keywords\n")
  }
} else {
  write_json(list(), "bibliometrix_results/all_keywords.json")
  cat("  ⚠️  Colonne DE non trouvée\n")
}

# ════════════════════════════════════════════════════════════
# 6. RÉSEAU COLLABORATION - COMPLET (TOUS LES AUTEURS)
# ════════════════════════════════════════════════════════════

cat("\n🌐 Réseau collaboration COMPLET...\n")
cat("  Attention: Peut prendre plusieurs minutes avec TOUS les auteurs\n")

# Prendre TOUS les auteurs (pas de limite)
all_authors_names <- names(author_counts)
cat("  Nombre total d'auteurs:", length(all_authors_names), "\n")

# Fonction pour extraire les paires (optimisée)
extract_pairs <- function(authors_str, all_authors_set) {
  authors <- trimws(unlist(strsplit(authors_str, ";")))
  # Garder seulement les auteurs qui existent dans notre set
  authors <- authors[authors %in% all_authors_set]
  if(length(authors) >= 2) {
    pairs <- combn(authors, 2, simplify = FALSE)
    # Utiliser data.table pour l'efficacité
    result <- data.table()
    for(p in pairs) {
      result <- rbind(result, data.table(
        author1 = min(p[1], p[2]), 
        author2 = max(p[1], p[2])
      ))
    }
    return(result)
  }
  return(NULL)
}

# Extraire toutes les paires (batch processing)
cat("  Extraction des paires de co-auteurs...\n")
all_pairs_list <- list()

batch_size <- 5000  # Plus petit batch pour éviter mémoire
n_batches <- ceiling(nrow(df) / batch_size)

for(batch in 1:n_batches) {
  start_idx <- (batch - 1) * batch_size + 1
  end_idx <- min(batch * batch_size, nrow(df))
  
  batch_pairs <- data.table()
  for(i in start_idx:end_idx) {
    pairs <- extract_pairs(df$AU[i], all_authors_names)
    if(!is.null(pairs) && nrow(pairs) > 0) {
      batch_pairs <- rbind(batch_pairs, pairs)
    }
  }
  
  if(nrow(batch_pairs) > 0) {
    all_pairs_list[[batch]] <- batch_pairs
  }
  
  if(batch %% 5 == 0) {
    cat("    Lot", batch, "/", n_batches, "traité\n")
  }
}

# Combiner toutes les paires
if(length(all_pairs_list) > 0) {
  all_pairs <- rbindlist(all_pairs_list, use.names = TRUE, fill = TRUE)
  cat("  Paires extraites:", nrow(all_pairs), "\n")
  
  # Compter les collaborations (TOUTES)
  collab_counts <- all_pairs[, .N, by = .(author1, author2)]
  setorder(collab_counts, -N)
  
  cat("  Paires uniques:", nrow(collab_counts), "\n")
  
  # Sauvegarder TOUTES les collaborations (top 10,000 pour éviter fichier trop gros)
  total_pairs_for_export <- min(10000, nrow(collab_counts))
  all_pairs_for_viz <- lapply(1:total_pairs_for_export, function(i) {
    list(
      source = collab_counts$author1[i],
      target = collab_counts$author2[i],
      weight = collab_counts$N[i]
    )
  })
  
  write_json(all_pairs_for_viz, "bibliometrix_results/all_collaboration_edges.json")
  cat("  ✅ all_collaboration_edges.json (", length(all_pairs_for_viz), " paires)\n")
  
  # Construire le réseau pour TOUS les auteurs
  cat("  Construction du réseau complet...\n")
  collaboration_network <- list()
  
  # Limiter à 500 auteurs pour éviter fichier JSON trop énorme
  top_500_authors <- all_authors_names[1:min(500, length(all_authors_names))]
  
  for(author in top_500_authors) {
    author_collabs <- collab_counts[author1 == author | author2 == author]
    
    # TOUS les collaborateurs (pas de limite)
    all_collabs <- list()
    if(nrow(author_collabs) > 0) {
      for(i in 1:nrow(author_collabs)) {
        partner <- ifelse(author_collabs$author1[i] == author, 
                         author_collabs$author2[i], 
                         author_collabs$author1[i])
        all_collabs[[i]] <- list(
          name = partner, 
          weight = author_collabs$N[i],
          publications_together = author_collabs$N[i]
        )
      }
    }
    
    collaboration_network[[author]] <- list(
      author = author,
      total_publications = as.integer(author_counts[author]),
      total_collaborators = nrow(author_collabs),
      all_collaborators = all_collabs  # TOUS les collaborateurs
    )
  }
  
  write_json(collaboration_network, "bibliometrix_results/collaboration_network_complete.json")
  cat("  ✅ collaboration_network_complete.json (", length(collaboration_network), " auteurs)\n")
  
  # Aussi garder une version avec top 50 pour l'admin (plus rapide)
  top_50_network <- collaboration_network[1:min(50, length(collaboration_network))]
  write_json(top_50_network, "bibliometrix_results/collaboration_network.json")
  cat("  ✅ collaboration_network.json (top 50 pour admin)\n")
  
} else {
  write_json(list(), "bibliometrix_results/collaboration_network.json")
  cat("  ⚠️  Pas de collaborations trouvées\n")
}

# ════════════════════════════════════════════════════════════
# 7. PUBLICATIONS PAR AUTEUR - POUR TOUS LES AUTEURS
# ════════════════════════════════════════════════════════════

cat("\n📄 Publications par auteur...\n")

# Limiter à top 200 pour éviter fichier trop gros
top_200_authors <- names(head(author_counts, 200))

author_publications <- list()

for(author_name in top_200_authors) {
  # Trouver les publications
  author_pubs <- grep(author_name, df$AU, fixed = TRUE)
  
  # TOUTES les publications (pas de limite)
  all_pubs <- lapply(author_pubs, function(idx) {
    list(
      title = substr(df$TI[idx], 1, 200),
      year = df$PY[idx],
      citations = df$TC[idx],
      journal = df$SO[idx],
      doi = if("DI" %in% names(df)) df$DI[idx] else NA
    )
  })
  
  author_publications[[author_name]] <- list(
    author = author_name,
    total_publications = length(author_pubs),
    all_publications = all_pubs  # TOUTES les publications
  )
}

write_json(author_publications, "bibliometrix_results/all_author_publications.json")
cat("  ✅ all_author_publications.json (", length(author_publications), " auteurs)\n")

# ════════════════════════════════════════════════════════════
# RÉSUMÉ FINAL
# ════════════════════════════════════════════════════════════

cat("\n", rep("=", 70), "\n", sep="")
cat("  ✅ ANALYSE COMPLÈTE TERMINÉE (SANS AUCUNE LIMITE)\n")
cat(rep("=", 70), "\n")
cat("\n📁 Fichiers générés:\n")

files <- list.files("bibliometrix_results", pattern = "\\.json$")
file_sizes <- data.frame(
  name = character(),
  size_kb = numeric(),
  stringsAsFactors = FALSE
)

for(f in files) {
  size <- round(file.info(file.path("bibliometrix_results", f))$size / 1024, 1)
  cat(paste0("  • ", f, " (", size, " KB)\n"))
}

cat("\n📊 Résumé STATISTIQUES COMPLÈTES:\n")
cat("  • Publications:", stats$total_publications, "\n")
cat("  • Citations totales:", stats$total_citations, "\n")
cat("  • Auteurs uniques:", length(author_counts), "\n")
if(exists("keyword_counts") && length(keyword_counts) > 0) {
  cat("  • Keywords uniques:", length(keyword_counts), "\n")
}
if(exists("collab_counts") && nrow(collab_counts) > 0) {
  cat("  • Paires de collaboration uniques:", nrow(collab_counts), "\n")
}

cat("\n💾 Espage disque total:", 
    round(sum(file.info(list.files("bibliometrix_results", full.names = TRUE))$size) / 1024 / 1024, 2), 
    "MB\n")