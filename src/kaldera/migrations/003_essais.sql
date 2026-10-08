-- Ingestion : nombre de prises d'une tâche ; au-delà de ESSAIS_MAX, échec (revue SP3a).
ALTER TABLE file_ingestion ADD COLUMN essais int NOT NULL DEFAULT 0;
