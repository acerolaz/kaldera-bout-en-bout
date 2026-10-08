-- Ingestion (SP3a). Écarts au schéma 2.6 bis, consignés au journal :
-- soumise_le = signal « dossier complet » ; reference = demande de la tâche (verrou ①) ;
-- pris_le = reprise des tâches bloquées.
ALTER TABLE demandes ADD COLUMN soumise_le timestamptz;
ALTER TABLE file_ingestion ADD COLUMN reference text REFERENCES demandes;
ALTER TABLE file_ingestion ADD COLUMN pris_le timestamptz;
CREATE INDEX file_en_cours ON file_ingestion (pris_le) WHERE statut = 'en_cours';
