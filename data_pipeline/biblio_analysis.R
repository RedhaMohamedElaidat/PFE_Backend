library(bibliometrix)
library(jsonlite)

# 📥 Lire CSV
M <- read.csv("C:/Users/ridae/PFE/Backend/outputs/algeria_last_15_years_bibliometrix.csv",
              fileEncoding = "UTF-8",
              stringsAsFactors = FALSE)

# Ajouter DB
M$DB <- "scopus"

# Analyse
results <- biblioAnalysis(M, sep=";")

# Résumé
S <- summary(results, k = 20, pause = FALSE)

# 📤 Export JSON
output <- list(
  annual_production = S$AnnualProduction,
  top_authors = S$MostProdAuthors,
  top_papers = S$MostCitedPapers
)

write_json(output, "C:/Users/ridae/PFE/Backend/outputs/results.json", pretty = TRUE)